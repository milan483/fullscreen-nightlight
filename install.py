#!/usr/bin/env python3
"""Transactional, user-local installation of the fixed payload."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parent
ID = "fullscreen-nightlight"
NAME = "org.fullscreennightlight.Inhibitor"

MANIFEST = "ownership.json"
LIMIT = 16 * 1024 * 1024
MANIFEST_LIMIT = 64 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def xdg(name, fallback):
    raw = os.environ.get(name) or str(fallback)
    p = Path(raw)
    if (not p.is_absolute() or p.anchor != "/" or p == Path("/")
            or ".." in p.parts or any(ord(c) < 32 or ord(c) == 127 or c == "\\" for c in raw)):
        raise ValueError("XDG paths must be absolute, non-root, without parent references or control characters")
    return p


def roots():
    home = Path.home()
    return (xdg("XDG_DATA_HOME", home / ".local/share"),
            xdg("XDG_CONFIG_HOME", home / ".config"))


def destinations(data, conf):
    return {
        "helper": data / ID / "inhibitor.py",
        "metadata": data / "kwin/scripts" / ID / "metadata.json",
        "script": data / "kwin/scripts" / ID / "contents/code/main.js",
        "unit": conf / "systemd/user" / (ID + ".service"),
        "activation": data / "dbus-1/services" / (NAME + ".service"),
    }


def unit_quote(s):
    return '"' + s.replace("\\","\\\\").replace('"','\\"').replace("%","%%").replace("$","$$") + '"'

def payload():
    data, conf = roots()
    paths = destinations(data, conf)
    helper = paths["helper"]
    unit = ("[Unit]\nDescription=Fullscreen Night Light inhibitor\n"
        "[Service]\nType=dbus\nBusName="+NAME+"\nExecStart=/usr/bin/python3 "
        +unit_quote(str(helper))+"\nNoNewPrivileges=true\n"
        "Restart=on-failure\nRestartSec=5\n")
    dbus = ("[D-BUS Service]\nName="+NAME+"\nExec=/usr/bin/python3 "
        +shlex.quote(str(helper))+"\nSystemdService="+ID+".service\n")
    return {
        helper: (ROOT/"helper/inhibitor.py").read_bytes(),
        paths["metadata"]: (ROOT/"kwin-script/metadata.json").read_bytes(),
        paths["script"]: (ROOT/"kwin-script/contents/code/main.js").read_bytes(),
        paths["unit"]: unit.encode(),
        paths["activation"]: dbus.encode(),
    }

@contextmanager
def directory(path, create=False):
    """Walk from / with no-follow directory descriptors; never resolve symlinks."""
    fd = os.open("/", DIR_FLAGS)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    yield None
                    return
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
                child = os.open(component, DIR_FLAGS, dir_fd=fd)
            info = os.fstat(child)
            if (info.st_uid not in (0, os.geteuid()) or
                    (info.st_mode & 0o022 and not
                     (info.st_uid == 0 and info.st_mode & stat.S_ISVTX))):
                os.close(child)
                raise RuntimeError("Unsafe ancestor directory: " + component)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def private_directory(fd):
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise RuntimeError("Directory must be owned by the user and not group/world writable")


def read_at(fd, name, links=1, limit=LIMIT):
    if fd is None:
        return None, None
    def check(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or not 1 <= info.st_nlink <= links or info.st_mode & 0o7000):
            raise RuntimeError("Unsafe file (untouched): " + name)
        if info.st_mode & 0o022:
            raise RuntimeError("Group/world-writable file (untouched): " + name)

    try:
        initial = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None, None
    check(initial)
    file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
    try:
        info = os.fstat(file)
        check(info)
        if (info.st_dev, info.st_ino) != (initial.st_dev, initial.st_ino):
            raise RuntimeError("File changed while opening: " + name)
        with os.fdopen(file, "rb", closefd=False) as stream:
            contents = stream.read(limit + 1)
        if len(contents) > limit:
            raise RuntimeError("File too large: " + name)
        after = os.fstat(file)
        if (info.st_ctime_ns, info.st_mtime_ns, info.st_size) != (
                after.st_ctime_ns, after.st_mtime_ns, after.st_size):
            raise RuntimeError("File changed while reading: " + name)
        record = {"dev": info.st_dev, "ino": info.st_ino,
                  "mode": stat.S_IMODE(info.st_mode),
                  "sha256": hashlib.sha256(contents).hexdigest()}
        return record, contents
    finally:
        os.close(file)


def snapshot(path):
    with directory(path.parent) as fd:
        if fd is not None:
            private_directory(fd)
        return read_at(fd, path.name)[0]


def write_new(fd, name, contents, mode):
    file = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                   0o600, dir_fd=fd)
    with os.fdopen(file, "wb") as stream:
        stream.write(contents)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())
    os.fsync(fd)


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate manifest key")
        obj[key] = value
    return obj


def valid_record(record):
    return (type(record) is dict and set(record) == {"dev", "ino", "mode", "sha256"}
            and all(type(record[k]) is int and record[k] >= 0 for k in ("dev", "ino", "mode"))
            and record["ino"] > 0 and record["mode"] == 0o644
            and type(record["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", record["sha256"]))


def valid_ownership(owned, paths):
    return (type(owned) is dict and owned.keys() <= paths.keys()
            and all(valid_record(r) for r in owned.values())
            and len({(r["dev"], r["ino"]) for r in owned.values()}) == len(owned))


def validate(state, root_pair, paths):
    if (type(state) is not dict or set(state) != {"version", "roots", "owned", "transaction"}
            or type(state["version"]) is not int or state["version"] != 1
            or state["roots"] != [str(p) for p in root_pair]
            or not valid_ownership(state["owned"], paths)):
        raise ValueError("Invalid manifest or XDG roots changed")
    tx = state["transaction"]
    if tx is None:
        return
    if (type(tx) is not dict or set(tx) != {"id", "phase", "changes", "next"}
            or type(tx["id"]) is not str or not re.fullmatch("[0-9a-f]{32}", tx["id"])
            or tx["phase"] not in ("preparing", "prepared", "committed", "rolled-back")
            or not valid_ownership(tx["next"], paths)
            or type(tx["changes"]) is not dict or not tx["changes"]
            or not tx["changes"].keys() <= paths.keys()):
        raise ValueError("Invalid transaction")
    for key, change in tx["changes"].items():
        if (type(change) is not dict or set(change) != {"old", "new", "install"}
                or type(change["install"]) is not bool
                or (change["old"] is not None and
                    (not valid_record(change["old"]) or change["old"] != state["owned"].get(key)))
                or (change["new"] is not None and not valid_record(change["new"]))
                or (not change["install"] and change["new"] is not None)
                or (change["install"] and tx["phase"] != "preparing" and change["new"] is None)
                or (not change["install"] and change["old"] is None)):
            raise ValueError("Invalid transaction change")
        if tx["phase"] == "preparing" and change["new"] is not None:
            raise ValueError("Unprepared transaction contains a staged identity")
        if tx["next"].get(key) != change["new"]:
            raise ValueError("Inconsistent transaction ownership")
        if change["new"] is not None and change["new"] == change["old"]:
            raise ValueError("Transaction cannot reuse the old file identity")
    for key in paths.keys() - tx["changes"].keys():
        if key in tx["next"] and tx["next"][key] != state["owned"].get(key):
            raise ValueError("Transaction cannot acquire unrelated ownership")


def load_state(fd, root_pair, paths):
    record, contents = read_at(fd, MANIFEST, limit=MANIFEST_LIMIT)
    if contents is None:
        return {"version": 1, "roots": [str(p) for p in root_pair], "owned": {}, "transaction": None}
    if record["mode"] != 0o600:
        raise RuntimeError("Unsafe manifest permissions")
    try:
        state = json.loads(contents, object_pairs_hook=unique_object)
    except RecursionError as exc:
        raise ValueError("Manifest nesting too deep") from exc
    validate(state, root_pair, paths)
    return state


def save_state(fd, state):
    # Atomically publish and sync the journal/manifest before any payload mutation.
    name = ".ownership-" + uuid.uuid4().hex
    # Reserve the temporary name before the cleanup scope.
    file = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                   0o600, dir_fd=fd)
    try:
        with os.fdopen(file, "wb") as stream:
            stream.write(json.dumps(state, sort_keys=True).encode())
            stream.flush()
            os.fchmod(stream.fileno(), 0o600)
            os.fsync(stream.fileno())
        os.replace(name, MANIFEST, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(name, dir_fd=fd)
        except FileNotFoundError:
            pass


@contextmanager
def staging(path, token, key, create=False):
    name = "." + ID + "-" + token + "-" + key
    with directory(path.parent, create=create) as parent:
        if parent is None:
            yield None, None, name
            return
        private_directory(parent)
        if create:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        try:
            stage = os.open(name, DIR_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            yield parent, None, name
            return
        try:
            private_directory(stage)
            if stat.S_IMODE(os.fstat(stage).st_mode) != 0o700:
                raise RuntimeError("Unsafe staging directory")
            yield parent, stage, name
        finally:
            os.close(stage)


def cleanup(tx, paths):
    for key in tx["changes"]:
        with staging(paths[key], tx["id"], key) as (parent, stage, name):
            if stage is None:
                continue
            # Only the two fixed staging names may be removed. Never recurse.
            names = os.listdir(stage)
            if not set(names) <= {"old", "new"}:
                raise RuntimeError("Unexpected staging contents")
            for entry in names:
                read_at(stage, entry, links=2)
                os.unlink(entry, dir_fd=stage)
            os.fsync(stage)
            os.rmdir(name, dir_fd=parent)
            os.fsync(parent)


def prepare(tx, paths, files):
    for key, change in tx["changes"].items():
        path = paths[key]
        with staging(path, tx["id"], key, create=True) as (parent, stage, _):
            if read_at(parent, path.name)[0] != change["old"]:
                raise RuntimeError("File changed during preparation: " + str(path))
            if change["old"] is not None:
                os.link(path.name, "old", src_dir_fd=parent, dst_dir_fd=stage, follow_symlinks=False)
                os.fsync(stage)
                os.fsync(parent)
                if read_at(stage, "old", links=2)[0] != change["old"]:
                    raise RuntimeError("Backup changed during preparation")
            if change["install"]:
                write_new(stage, "new", files[path], 0o644)
                change["new"] = read_at(stage, "new")[0]
                tx["next"][key] = change["new"]


def change_payload(tx, paths):
    for key, change in tx["changes"].items():
        path = paths[key]
        with staging(path, tx["id"], key) as (parent, stage, _):
            if stage is None or read_at(parent, path.name, links=2)[0] != change["old"]:
                raise RuntimeError("File changed during transaction: " + str(path))
            if change["old"] is not None:
                if read_at(stage, "old", links=2)[0] != change["old"]:
                    raise RuntimeError("Backup changed")
                os.unlink(path.name, dir_fd=parent)
                os.fsync(parent)
            if change["install"]:
                if read_at(stage, "new", links=2)[0] != change["new"]:
                    raise RuntimeError("Staged file changed")
                # Atomic no-clobber creation even if another process created the name.
                os.link("new", path.name, src_dir_fd=stage, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)


def rollback(tx, paths):
    # Preflight every affected path before restoring anything. Refuse ambiguity.
    for key, change in tx["changes"].items():
        path = paths[key]
        with staging(path, tx["id"], key) as (parent, stage, _):
            if stage is None:
                raise RuntimeError("Missing transaction staging directory")
            current = read_at(parent, path.name, links=2)[0]
            if current not in (None, change["old"], change["new"]):
                raise RuntimeError("Recovery conflict (untouched): " + str(path))
            if change["old"] is not None and read_at(stage, "old", links=2)[0] != change["old"]:
                raise RuntimeError("Recovery backup changed: " + str(path))
    for key, change in reversed(list(tx["changes"].items())):
        path = paths[key]
        with staging(path, tx["id"], key) as (parent, stage, _):
            current = read_at(parent, path.name, links=2)[0]
            if current == change["old"]:
                continue
            if current is not None:
                if current != change["new"]:
                    raise RuntimeError("Recovery conflict (untouched): " + str(path))
                os.unlink(path.name, dir_fd=parent)
                os.fsync(parent)
            if change["old"] is not None:
                os.link("old", path.name, src_dir_fd=stage, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)


def recover(fd, state, paths):
    tx = state["transaction"]
    if tx is None:
        return
    if tx["phase"] == "prepared":
        rollback(tx, paths)
        tx["phase"] = "rolled-back"
        save_state(fd, state)
    # Preparing never changes payload names; committed/rolled-back only need cleanup.
    cleanup(tx, paths)
    if tx["phase"] == "committed":
        state["owned"] = tx["next"]
    state["transaction"] = None
    save_state(fd, state)


def plan(state, paths, files, uninstall):
    changes, owned = {}, dict(state["owned"])
    for key, path in paths.items():
        previous = owned.get(key)
        if uninstall and previous is None:
            continue
        current = snapshot(path)
        if previous is not None and current is not None and current != previous:
            raise RuntimeError("Owned file modified (untouched): " + str(path))
        if uninstall:
            owned.pop(key)
            if current is not None:
                changes[key] = {"old": current, "new": None, "install": False}
        else:
            digest = hashlib.sha256(files[path]).hexdigest()
            if current is not None and current["sha256"] == digest:
                continue  # Identical unowned files are never adopted.
            if current is not None and previous is None:
                raise RuntimeError("Conflict (untouched): " + str(path))
            changes[key] = {"old": current, "new": None, "install": True}
            owned.pop(key, None)
    return changes, owned


def apply(files, uninstall=False, dry=False):
    root_pair = roots()
    paths = destinations(*root_pair)
    if set(files) != set(paths.values()) or len(files) != len(paths):
        raise ValueError("Unexpected payload destinations")
    if any(type(contents) is not bytes or len(contents) > LIMIT for contents in files.values()):
        raise ValueError("Invalid or oversized payload")
    for root in root_pair:
        with directory(root) as fd:
            if fd is not None:
                private_directory(fd)
    state_dir = root_pair[0] / ID
    all_files = [*paths.values(), state_dir / MANIFEST]
    if len(set(all_files)) != len(all_files) or any(
            other != path and other.is_relative_to(path)
            for path in all_files for other in [*all_files, *root_pair, state_dir]):
        raise ValueError("Overlapping XDG destinations")
    # Validate every destination's parent, even when there is no ownership.
    for path in paths.values():
        with directory(path.parent) as fd:
            if fd is not None:
                private_directory(fd)
    with directory(state_dir, create=not dry and not uninstall) as fd:
        if fd is not None:
            private_directory(fd)
            fcntl.flock(fd, (fcntl.LOCK_SH if dry else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        state = load_state(fd, root_pair, paths)
        if state["transaction"] is not None:
            if dry:
                raise RuntimeError("Interrupted transaction; run without --dry-run to recover")
            recover(fd, state, paths)
        changes, owned = plan(state, paths, files, uninstall)
        if not uninstall:
            for key in paths.keys() - state["owned"].keys() - changes.keys():
                print("Preserve unowned file: " + str(paths[key]))
        elif not state["owned"]:
            print("No owned files to remove; unowned files left untouched.")
        if dry:
            for key, change in changes.items():
                print(("install " if change["install"] else "remove ") + str(paths[key]))
            if not changes:
                print("No payload file changes planned.")
            return
        if not changes:
            if fd is not None and owned != state["owned"]:
                state["owned"] = owned
                save_state(fd, state)
            return
        tx = {"id": uuid.uuid4().hex, "phase": "preparing", "changes": changes, "next": owned}
        state["transaction"] = tx
        save_state(fd, state)
        try:
            prepare(tx, paths, files)
            tx["phase"] = "prepared"
            save_state(fd, state)
            change_payload(tx, paths)
            tx["phase"] = "committed"
            save_state(fd, state)
        except Exception:
            # Reload the durable phase, not an in-memory phase whose write may have failed.
            recover(fd, load_state(fd, root_pair, paths), paths)
            raise
        recover(fd, state, paths)


def package_discoverable():
    """Check the user-local KWin package listing, without loading a script."""
    try:
        result = subprocess.run(
            ["kpackagetool6", "--type", "KWin/Script", "--list"],
            capture_output=True, text=True, timeout=10,
            env=dict(os.environ, LC_ALL="C"),
        )
    except (OSError, subprocess.TimeoutExpired):
        print("FAIL: KWin discovery could not be checked (kpackagetool6 unavailable or timed out)")
        return False
    return result.returncode == 0 and ID in result.stdout.splitlines()


def validate_installation(files):
    """Check installed bytes, ownership records and KWin discovery without repair."""
    root_pair = roots()
    paths = destinations(*root_pair)
    if set(files) != set(paths.values()):
        raise ValueError("Unexpected payload destinations")
    ok = True
    with directory(root_pair[0] / ID) as fd:
        if fd is not None:
            private_directory(fd)
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        state = load_state(fd, root_pair, paths)
        if state["transaction"] is not None:
            raise RuntimeError("Interrupted transaction; review installer recovery instructions")
        for key, path in paths.items():
            current = snapshot(path)
            expected = hashlib.sha256(files[path]).hexdigest()
            previous = state["owned"].get(key)
            if current is None:
                print("FAIL: missing " + key)
                ok = False
            elif current["sha256"] != expected or (previous is not None and current != previous):
                print("FAIL: modified or different version: " + key)
                ok = False
            else:
                ownership = "owned" if previous is not None else "unowned; preserved"
                print("PASS: " + key + " (" + ownership + ")")
    discovered = package_discoverable()
    print(("PASS" if discovered else "FAIL") + ": KWin package discovery")
    print("INFO: validation does not enable the script or verify live inhibition.")
    return ok and discovered


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", action="store_true",
                        help="Check installed files and KWin discovery without changes")
    args = parser.parse_args()
    if args.validate and (args.uninstall or args.dry_run):
        parser.error("--validate cannot be combined with --uninstall or --dry-run")
    try:
        if os.geteuid() == 0:
            raise RuntimeError("Run as the desktop user, not root")
        if args.validate:
            raise SystemExit(0 if validate_installation(payload()) else 1)
        apply(payload(), args.uninstall, args.dry_run)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, "Installer: " + str(exc) + "\n")
    print("No service or KWin settings changed by this command.")
