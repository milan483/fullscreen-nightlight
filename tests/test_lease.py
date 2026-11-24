import sys
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"helper"))
from inhibitor import Backend, CleanupError, EndpointUnavailable, GLib, Lease, RETRY
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
        self.assertEqual(self.backend.calls,[None])
    def test_refresh_expiry(self):
        self.lease.refresh(True, ":1.1")
        self.lease.tick()
        self.now+=14
        self.lease.tick()
        self.now+=1
        self.lease.tick()
        self.assertEqual(self.backend.calls,[":1.1",":1.1",None])
    def test_renew(self):
        self.lease.refresh(True, ":1.1")
        self.now+=10
        self.lease.refresh(True, ":1.1")
        self.now+=10
        self.lease.tick()
        self.assertEqual(self.backend.calls,[":1.1"])
    def test_release(self):
        self.lease.refresh(True, ":1.1")
        self.lease.refresh(False, ":1.1")
        self.lease.tick()
        self.assertEqual(self.backend.calls,[None])
    def test_invalidation_is_owner_specific(self):
        self.lease.refresh(True, ":1.2")
        self.lease.invalidate(":1.1")
        self.lease.tick()
        self.lease.invalidate(":1.2")
        self.lease.tick()
        self.assertEqual(self.backend.calls, [":1.2", None])

    def test_expired_lease_cannot_reappear(self):
        self.lease.refresh(True, ":1.1")
        self.now += 15
        self.lease.tick()
        self.assertIsNone(self.lease.owner)
        self.lease.tick()
        self.assertEqual(self.backend.calls, [None, None])


class Connection:
    def __init__(self, closed=False, fail=False):
        self.closed = closed
        self.fail = fail
        self.closes = 0

    def is_closed(self):
        return self.closed

    def close_sync(self, _):
        self.closes += 1
        if self.fail:
            raise GLib.Error("injected close failure")
        self.closed = True


class FakeBackend(Backend):
    def __init__(self, clock):
        super().__init__(None, clock)
        self.opens = 0
        self.fail_open = False

    def open(self, owner):
        self.opens += 1
        if self.fail_open:
            raise EndpointUnavailable("injected failure")
        self.conn, self.cookie, self.owner = Connection(), 42, owner

    def call(self, method, params, result):
        self.last_call = method, params.unpack(), result


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.backend = FakeBackend(lambda: self.now)

    def test_private_connection_loss_backoff_and_recovery(self):
        b = self.backend
        b.apply(":1.1")
        lost = b.conn
        lost.closed = True
        with self.assertLogs(level="WARNING") as logs:
            b.apply(":1.1")
            for _ in range(20):
                b.apply(":1.1")
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(b.opens, 1)
        self.assertIsNone(b.cookie)
        self.assertEqual(lost.closes, 0)
        self.now += RETRY
        b.apply(":1.1")
        self.assertEqual(b.opens, 2)
        self.assertIsNot(b.conn, lost)
        b.apply(None)
        self.assertEqual(b.last_call, ("uninhibit", (42,), "()"))
        self.assertIsNone(b.conn)

    def test_retry_rate_and_logging_bounded(self):
        b = self.backend
        b.fail_open = True
        with self.assertLogs(level="WARNING") as logs:
            for _ in range(4):
                for _ in range(20):
                    b.apply(":1.1")
                    b.apply(None)
                self.now += RETRY
        self.assertEqual(b.opens, 4)
        self.assertEqual(len(logs.output), 1)
        self.assertIsNone(b.conn)
        b.fail_open = False
        b.apply(":1.1")
        self.assertEqual(b.opens, 5)
        self.assertFalse(b.failing)

    def test_close_failure_retains_connection_until_process_exit(self):
        b = self.backend
        b.apply(":1.1")
        connection = b.conn
        connection.fail = True
        with self.assertRaises(CleanupError):
            b.close()
        self.assertIs(b.conn, connection)
        self.assertEqual(b.cookie, 42)
        self.assertEqual(b.owner, ":1.1")
        connection.fail = False
        b.close()
        self.assertIsNone(b.conn)

    def test_different_bus_guid_never_sends_inhibit(self):
        control = Mock()
        control.is_closed.return_value = False
        control.get_guid.return_value = "old-bus"
        private = Mock()
        private.is_closed.side_effect = [False, True]
        private.get_guid.return_value = "new-bus"
        backend = Backend(control, lambda: self.now)
        with patch.object(backend, "get_owner", return_value=":1.1"), \
             patch("inhibitor.Gio.dbus_address_get_for_bus_sync", return_value="unix:abstract=mock"), \
             patch("inhibitor.Gio.DBusConnection.new_for_address_sync", return_value=private), \
             self.assertLogs(level="WARNING"):
            backend.apply(":1.1")
        private.call_sync.assert_not_called()
        private.close_sync.assert_called_once()
        self.assertIsNone(backend.conn)
        self.assertEqual(backend.retry_at, self.now+RETRY)

    def test_no_release_on_already_closed_connection(self):
        b = self.backend
        b.apply(":1.1")
        b.conn.closed = True
        with self.assertLogs(level="WARNING"):
            b.apply(None)
        self.assertFalse(hasattr(b, "last_call"))
        self.assertIsNone(b.conn)


if __name__=="__main__": unittest.main()
