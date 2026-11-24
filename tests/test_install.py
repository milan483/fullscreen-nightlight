import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install


class Interrupted(BaseException):
    """Simulate a process disappearing without normal exception recovery."""


class Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.data = self.base / "data"
        self.config = self.base / "config"
        self.manifest = self.data / install.ID / install.MANIFEST
        env = patch.dict(os.environ, XDG_DATA_HOME=str(self.data),
                         XDG_CONFIG_HOME=str(self.config))
        env.start()
        self.addCleanup(env.stop)
        self.files = install.payload()
        self.p, self.q = list(self.files)[:2]

    def apply(self, **kwargs):
        install.apply(self.files, **kwargs)

    def state(self):
        return json.loads(self.manifest.read_text())

    def tree(self):
        return {str(p.relative_to(self.base)): (p.lstat().st_mode, p.read_bytes()
                if p.is_file() and not p.is_symlink() else None)
                for p in self.base.rglob("*")}

    def assert_clean(self):
        self.assertIsNone(self.state()["transaction"])
        self.assertFalse(list(self.base.rglob("." + install.ID + "-*")))

    def test_install_repeat_uninstall(self):
        self.apply()
        tree = self.tree()
        self.assertEqual(len(self.state()["owned"]), len(self.files))
        self.apply()
        self.assertEqual(tree, self.tree())
        self.apply(uninstall=True)
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assertEqual(self.state()["owned"], {})
        tree = self.tree()
        self.apply(uninstall=True)
        self.assertEqual(tree, self.tree())
        self.assert_clean()

    def test_conflict(self):
        self.q.parent.mkdir(parents=True)
        self.q.write_bytes(b"other")
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertFalse(self.p.exists())
        self.assertEqual(self.q.read_bytes(), b"other")
        self.apply(uninstall=True)
        self.assertEqual(self.q.read_bytes(), b"other")

    def test_symlink_conflict(self):
        self.p.parent.mkdir(parents=True)
        self.p.symlink_to(self.base / "missing")
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertTrue(self.p.is_symlink())

    def test_nested_ancestor_symlink(self):
        outside = self.base / "outside"
        outside.mkdir()
        self.data.mkdir()
        (self.data / "kwin").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.apply()
        self.assertFalse(self.p.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_dry_run(self):
        self.apply(dry=True)
        self.apply(dry=True, uninstall=True)
        self.assertEqual(self.tree(), {})
        self.apply()
        tree = self.tree()
        self.apply(dry=True, uninstall=True)
        self.assertEqual(tree, self.tree())

    def test_external_edit_preserved(self):
        self.apply()
        self.p.write_bytes(b"edited")
        tree = self.tree()
        for uninstall in (False, True):
            with self.assertRaises(RuntimeError):
                self.apply(uninstall=uninstall)
            self.assertEqual(tree, self.tree())

    def test_identical_replacement_not_owned(self):
        self.apply()
        replacement = self.p.with_name("replacement")
        replacement.write_bytes(self.files[self.p])
        replacement.chmod(0o644)
        replacement.replace(self.p)
        with self.assertRaises(RuntimeError):
            self.apply(uninstall=True)
        self.assertEqual(self.p.read_bytes(), self.files[self.p])

    def test_mode_change_preserved(self):
        self.apply()
        self.p.chmod(0o600)
        with self.assertRaises(RuntimeError):
            self.apply(uninstall=True)
        self.assertEqual(self.p.stat().st_mode & 0o777, 0o600)

    def test_missing_owned_file(self):
        self.apply()
        self.p.unlink()
        self.apply()
        self.assertEqual(self.p.read_bytes(), self.files[self.p])
        self.p.unlink()
        self.apply(uninstall=True)
        self.assertEqual(self.state()["owned"], {})

    def test_legacy_uninstall_without_manifest(self):
        self.p.parent.mkdir(parents=True)
        self.p.write_bytes(self.files[self.p])
        tree = self.tree()
        self.apply(uninstall=True)
        self.assertEqual(tree, self.tree())

    def test_unowned_upgrade_conflict(self):
        self.p.parent.mkdir(parents=True)
        self.p.write_bytes(self.files[self.p])
        self.apply()
        upgraded = dict(self.files)
        upgraded[self.p] += b"new"
        tree = self.tree()
        with self.assertRaises(RuntimeError):
            install.apply(upgraded)
        self.assertEqual(tree, self.tree())

    def test_malformed_manifests(self):
        self.apply()
        state = self.state()
        cases = [b"{", b'{"version":1,"version":1}', b"[]",
                 json.dumps(dict(state, version=True)).encode(),
                 json.dumps(dict(state, roots=["/wrong", str(self.config)])).encode(),
                 json.dumps(dict(state, owned={"../../escape": next(iter(state["owned"].values()))})).encode(),
                 json.dumps(dict(state, owned={"helper": {"sha256": "bad"}})).encode(),
                 json.dumps(dict(state, transaction={"id": "../escape"})).encode()]
        for malformed in cases:
            with self.subTest(malformed=malformed):
                self.manifest.write_bytes(malformed)
                tree = self.tree()
                for uninstall in (False, True):
                    with self.assertRaises(ValueError):
                        self.apply(uninstall=uninstall)
                    self.assertEqual(tree, self.tree())

    def test_manifest_symlink(self):
        self.manifest.parent.mkdir(parents=True)
        outside = self.base / "outside"
        outside.write_text("unrelated")
        self.manifest.symlink_to(outside)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(outside.read_text(), "unrelated")

    def test_manifest_permissions(self):
        self.apply()
        self.manifest.chmod(0o644)
        with self.assertRaises(RuntimeError):
            self.apply(uninstall=True)
        self.assertTrue(self.p.exists())

    def test_invalid_xdg_paths(self):
        for value in ("relative", "/", "//tmp/path", str(self.base / ".." / "escape"),
                      str(self.base / "line\nbreak"), str(self.base / "tab\t"),
                      str(self.base / "slash\\name")):
            with self.subTest(value=value), patch.dict(os.environ, XDG_CONFIG_HOME=value):
                with self.assertRaises(ValueError):
                    install.payload()
        self.assertEqual(self.tree(), {})

    def test_changed_config_root(self):
        self.apply()
        tree = self.tree()
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.base / "different")):
            with self.assertRaises(ValueError):
                install.apply(install.payload(), uninstall=True)
        self.assertEqual(tree, self.tree())

    def test_overlapping_roots(self):
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.p)):
            with self.assertRaises(ValueError):
                install.apply(install.payload())
        self.assertEqual(self.tree(), {})

    def test_unsafe_ancestor_permissions(self):
        self.data.mkdir(mode=0o777)
        self.data.chmod(0o777)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertFalse(self.p.exists())

    def test_hardlink_and_fifo_refused(self):
        self.p.parent.mkdir(parents=True)
        outside = self.base / "outside"
        outside.write_bytes(self.files[self.p])
        os.link(outside, self.p)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.p.unlink()
        os.mkfifo(self.p)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(outside.read_bytes(), self.files[self.p])

    def test_partial_install_rollback(self):
        original = install.change_payload

        def fail(tx, paths):
            one = dict(tx, changes=dict(list(tx["changes"].items())[:1]))
            original(one, paths)
            raise OSError("injected failure")

        with patch.object(install, "change_payload", fail):
            with self.assertRaisesRegex(OSError, "injected failure"):
                self.apply()
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assertEqual(self.state()["owned"], {})
        self.assert_clean()
        self.apply()
        self.assert_clean()

    def test_partial_upgrade_rollback(self):
        self.apply()
        before = self.state()
        upgraded = {p: b"upgrade" + b for p, b in self.files.items()}
        original = install.change_payload

        def fail(tx, paths):
            original(dict(tx, changes=dict(list(tx["changes"].items())[:2])), paths)
            raise OSError("injected failure")

        with patch.object(install, "change_payload", fail):
            with self.assertRaises(OSError):
                install.apply(upgraded)
        self.assertEqual(before, self.state())
        self.assertTrue(all(p.read_bytes() == b for p, b in self.files.items()))
        self.assert_clean()

    def test_interrupted_install_and_dry_run(self):
        original = install.change_payload

        def interrupt(tx, paths):
            original(dict(tx, changes=dict(list(tx["changes"].items())[:1])), paths)
            raise Interrupted()

        with patch.object(install, "change_payload", interrupt):
            with self.assertRaises(Interrupted):
                self.apply()
        self.assertEqual(self.state()["transaction"]["phase"], "prepared")
        tree = self.tree()
        with self.assertRaises(RuntimeError):
            self.apply(dry=True)
        self.assertEqual(tree, self.tree())
        self.apply(uninstall=True)
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assert_clean()

    def test_interrupted_uninstall(self):
        self.apply()
        original = install.change_payload

        def interrupt(tx, paths):
            original(dict(tx, changes=dict(list(tx["changes"].items())[:1])), paths)
            raise Interrupted()

        with patch.object(install, "change_payload", interrupt):
            with self.assertRaises(Interrupted):
                self.apply(uninstall=True)
        self.assertFalse(self.p.exists())
        self.apply()
        self.assertTrue(all(p.read_bytes() == b for p, b in self.files.items()))
        self.assert_clean()

    def test_interrupted_preparation(self):
        original = install.prepare

        def interrupt(tx, paths, files):
            original(dict(tx, changes=dict(list(tx["changes"].items())[:1])), paths, files)
            raise Interrupted()

        with patch.object(install, "prepare", interrupt):
            with self.assertRaises(Interrupted):
                self.apply()
        self.assertEqual(self.state()["transaction"]["phase"], "preparing")
        self.apply(uninstall=True)
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assert_clean()

    def test_interrupted_committed_cleanup(self):
        with patch.object(install, "cleanup", side_effect=Interrupted):
            with self.assertRaises(Interrupted):
                self.apply()
        self.assertEqual(self.state()["transaction"]["phase"], "committed")
        self.apply()
        self.assertEqual(len(self.state()["owned"]), len(self.files))
        self.assert_clean()

    def test_recovery_conflict_preserves_external_file(self):
        original = install.change_payload

        def interrupt(tx, paths):
            original(dict(tx, changes=dict(list(tx["changes"].items())[:1])), paths)
            raise Interrupted()

        with patch.object(install, "change_payload", interrupt):
            with self.assertRaises(Interrupted):
                self.apply()
        self.p.write_bytes(b"external edit")
        tree = self.tree()
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(tree, self.tree())
        self.assertEqual(self.p.read_bytes(), b"external edit")

    def test_unrelated_config_and_files_preserved(self):
        self.config.mkdir()
        config = self.config / "kwinrc"
        config.write_bytes(b"NightLight=unchanged")
        self.p.parent.mkdir(parents=True)
        other = self.p.parent / "unrelated.txt"
        other.write_bytes(b"leave alone")
        self.apply()
        self.apply(uninstall=True)
        self.assertEqual(config.read_bytes(), b"NightLight=unchanged")
        self.assertEqual(other.read_bytes(), b"leave alone")

    def test_unexpected_payload_path(self):
        outside = self.base / "outside"
        files = dict(self.files)
        files[outside] = b"not authorized"
        with self.assertRaises(ValueError):
            install.apply(files)
        self.assertEqual(self.tree(), {})

    def test_concurrent_installer_lock(self):
        import fcntl

        self.apply()
        tree = self.tree()
        with install.directory(self.manifest.parent) as fd:
            fcntl.flock(fd, fcntl.LOCK_EX)
            for dry in (False, True):
                with self.assertRaises(BlockingIOError):
                    self.apply(dry=dry)
        self.assertEqual(tree, self.tree())

    def test_partial_preparation_failure(self):
        original = install.write_new

        def fail(fd, name, contents, mode):
            original(fd, name, contents, mode)
            raise OSError("injected preparation failure")

        with patch.object(install, "write_new", fail):
            with self.assertRaisesRegex(OSError, "injected preparation failure"):
                self.apply()
        self.assertTrue(all(not p.exists() for p in self.files))
        self.assert_clean()

    def test_actual_process_exit_between_unlink_and_link(self):
        import subprocess
        import sys

        self.apply()
        before = self.state()
        script = """
import os
import install
from unittest.mock import patch
files = {p: b'upgrade' + b for p, b in install.payload().items()}
original = os.link
def exit_before_new(src, dst, *args, **kwargs):
    if src == 'new':
        os._exit(91)
    return original(src, dst, *args, **kwargs)
with patch.object(install.os, 'link', exit_before_new):
    install.apply(files)
"""
        result = subprocess.run([sys.executable, "-c", script],
                                cwd=install.ROOT, timeout=10)
        self.assertEqual(result.returncode, 91)
        self.assertEqual(self.state()["transaction"]["phase"], "prepared")
        self.assertFalse(self.p.exists())
        self.apply()
        self.assertEqual(self.state(), before)
        self.assertTrue(all(p.read_bytes() == b for p, b in self.files.items()))
        self.assert_clean()

    def test_uninstall_failure_rollback(self):
        self.apply()
        before = self.state()
        original = install.change_payload

        def fail(tx, paths):
            original(dict(tx, changes=dict(list(tx["changes"].items())[:2])), paths)
            raise OSError("injected remove failure")

        with patch.object(install, "change_payload", fail):
            with self.assertRaises(OSError):
                self.apply(uninstall=True)
        self.assertEqual(self.state(), before)
        self.assertTrue(all(p.read_bytes() == b for p, b in self.files.items()))
        self.assert_clean()
