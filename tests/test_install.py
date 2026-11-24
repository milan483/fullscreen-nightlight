import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from install import apply, unit_quote
class Tests(unittest.TestCase):
    def test_install_repeat_uninstall(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a"/"file"
            apply({p:b"test"})
            apply({p:b"test"})
            self.assertEqual(p.read_bytes(),b"test")
            apply({p:b"test"},uninstall=True)
            self.assertFalse(p.exists())
            apply({p:b"test"},uninstall=True)
    def test_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"existing"
            p.write_bytes(b"other")
            q=Path(d)/"new"
            for remove in [False,True]:
                with self.assertRaises(RuntimeError): apply({q:b"test",p:b"test"},uninstall=remove)
            self.assertFalse(q.exists())
            self.assertEqual(p.read_bytes(),b"other")
    def test_symlink_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"link"
            p.symlink_to(Path(d)/"missing")
            with self.assertRaises(RuntimeError): apply({p:b"test"})
            self.assertTrue(p.is_symlink())
    def test_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"file"
            apply({p:b"test"},dry=True)
            self.assertFalse(p.exists())
