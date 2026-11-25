"""Build a versioned source archive from a committed Git tree, not a checkout."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "fullscreen-nightlight"
# Explicitly review additions to the distributed source. Git metadata, CI config,
# local state, ignored/untracked files and repository-only guidance are excluded.
FILES = (
    "CHANGELOG.md", "LICENSE", "README.md", "SECURITY.md", "VERSION",
    "docs/ARCHITECTURE.md", "docs/COMPATIBILITY.md", "docs/DEVELOPMENT.md",
    "docs/INSTALLER.md", "docs/TROUBLESHOOTING.md",
    "helper/inhibitor.py", "install.py",
    "kwin-script/contents/code/main.js", "kwin-script/metadata.json",
    "tests/check_install_payload.py", "tests/dbus_smoke.py", "tests/test_install.py",
    "tests/test_installer_regressions.py", "tests/test_lease.py",
    "tests/test_release.py", "tests/test_windows.js", "tests/verify.sh",
    "tools/build_release.py",
)
VERSION_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)\.[1-9][0-9]*)?"
SHA_PATTERN = r"[0-9a-f]{40}"


def git(repo, *args):
    return subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, timeout=30).stdout


def version_of(files):
    version = files["VERSION"].decode("ascii").strip()
    if not re.fullmatch(VERSION_PATTERN, version):
        raise ValueError("Unsupported release version")
    if files["VERSION"] != (version + "\n").encode("ascii"):
        raise ValueError("VERSION must contain the version and one newline")
    metadata = json.loads(files["kwin-script/metadata.json"])
    if metadata["KPlugin"]["Version"] != version:
        raise ValueError("KWin metadata version does not match VERSION")
    headings = [line for line in files["CHANGELOG.md"].decode("utf-8").splitlines()
                if line.startswith("## ")]
    if not headings or headings[0] != "## " + version:
        raise ValueError("First changelog release heading does not match VERSION")
    return version


def committed_files(repo, revision):
    if Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve() != repo.resolve():
        raise ValueError("Run from the source Git repository, not an extracted archive")
    commit = git(repo, "rev-parse", "--verify", "--end-of-options",
                 revision + "^{commit}").decode("ascii").strip()
    if not re.fullmatch(SHA_PATTERN, commit):
        raise ValueError("Expected a full SHA-1 commit ID")
    entries = {}
    for record in git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not record:
            continue
        header, path = record.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split()
        entries[path.decode("utf-8")] = (mode, kind, oid)
    # New files within these source directories require an explicit distribution
    # decision rather than silently omitting them or including unexpected files.
    prefixes = ("docs/", "helper/", "kwin-script/", "tests/", "tools/")
    unexpected = sorted(p for p in entries if p.startswith(prefixes) and p not in FILES)
    if unexpected:
        raise ValueError("Unreviewed distribution paths: " + ", ".join(unexpected))
    files = {}
    for path in FILES:
        if path not in entries:
            raise ValueError("Missing distribution path: " + path)
        mode, kind, oid = entries[path]
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("Distribution path is not a regular file: " + path)
        files[path] = git(repo, "cat-file", "blob", oid)
    return commit, files


def archive_bytes(commit, files):
    if not re.fullmatch(SHA_PATTERN, commit) or set(files) != set(FILES):
        raise ValueError("Unexpected source identity or file list")
    version = version_of(files)
    prefix = PROJECT + "-" + version
    contents = dict(files, SOURCE_COMMIT=(commit + "\n").encode("ascii"))
    output = io.BytesIO()
    # Stable order, timestamps, ownership, permissions and gzip header. The
    # source identity is included explicitly; no timestamps from the filesystem.
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0,
                       compresslevel=9) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for path, data in sorted(contents.items()):
                info = tarfile.TarInfo(prefix + "/" + path)
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    return prefix, output.getvalue(), contents


def verify_archive(data, prefix, contents):
    expected = {prefix + "/" + path: value for path, value in contents.items()}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            if (member.name not in expected or member.name in seen
                    or not member.isfile() or member.mode != 0o644
                    or member.uid != 0 or member.gid != 0 or member.mtime != 0):
                raise ValueError("Unexpected archive member: " + member.name)
            with tar.extractfile(member) as stream:
                if stream.read() != expected[member.name]:
                    raise ValueError("Archive content mismatch: " + member.name)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Archive is missing expected files")


def build(repo, revision, output_dir):
    commit, files = committed_files(repo, revision)
    prefix, data, contents = archive_bytes(commit, files)
    verify_archive(data, prefix, contents)
    # Require a new directory: never overwrite a prior candidate or checksum.
    output_dir.mkdir(mode=0o700)
    archive = output_dir / (prefix + ".tar.gz")
    archive.write_bytes(data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output_dir / "SHA256SUMS").write_text(digest + "  " + archive.name + "\n",
                                          encoding="ascii")
    print("Source commit:", commit)
    print(digest + "  " + archive.name)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="Git commit or ref to resolve")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New output directory whose parent already exists")
    args = parser.parse_args()
    try:
        build(ROOT, args.revision, args.output_dir)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, "Release build refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
