import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install


class InstallerRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.data = self.base / "data"
        self.config = self.base / "config"
        env = patch.dict(os.environ, XDG_DATA_HOME=str(self.data),
                         XDG_CONFIG_HOME=str(self.config))
        env.start()
        self.addCleanup(env.stop)

    def test_ancestor_symlink(self):
        outside = self.base / "outside"
        outside.mkdir()
        self.data.symlink_to(outside, target_is_directory=True)
        with self.assertRaises((RuntimeError, OSError, ValueError)):
            install.apply(install.payload())
        self.assertEqual(list(outside.iterdir()), [])

    def test_identical_preexisting_file_is_not_owned(self):
        files = install.payload()
        path, content = next(iter(files.items()))
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        install.apply(files)
        install.apply(files, uninstall=True)
        self.assertEqual(path.read_bytes(), content)
        self.assertTrue(all(not p.exists() for p in files if p != path))

    def test_upgrade_owned_file(self):
        files = install.payload()
        install.apply(files)
        path = next(iter(files))
        upgraded = dict(files)
        upgraded[path] += b"\n# upgrade\n"
        install.apply(upgraded)
        self.assertEqual(path.read_bytes(), upgraded[path])
        install.apply(files, uninstall=True)
        self.assertFalse(path.exists())

    def test_parent_reference_rejected(self):
        with patch.dict(os.environ, XDG_DATA_HOME=str(self.data / ".." / "escape")):
            with self.assertRaises(ValueError):
                install.payload()
