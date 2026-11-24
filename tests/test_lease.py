import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"helper"))
from inhibitor import Lease
class Fake:
    def __init__(self): self.calls=[]
    def apply(self, active): self.calls.append(active)
class Tests(unittest.TestCase):
    def setUp(self):
        self.now=100
        self.backend=Fake()
        self.lease=Lease(self.backend, lambda:self.now)
    def test_initial(self):
        self.lease.tick()
        self.assertEqual(self.backend.calls,[False])
    def test_refresh_expiry(self):
        self.lease.refresh(True)
        self.lease.tick()
        self.now+=14
        self.lease.tick()
        self.now+=1
        self.lease.tick()
        self.assertEqual(self.backend.calls,[True,True,False])
    def test_renew(self):
        self.lease.refresh(True)
        self.now+=10
        self.lease.refresh(True)
        self.now+=10
        self.lease.tick()
        self.assertEqual(self.backend.calls,[True])
    def test_release(self):
        self.lease.refresh(True)
        self.lease.refresh(False)
        self.lease.tick()
        self.assertEqual(self.backend.calls,[False])
if __name__=="__main__": unittest.main()
