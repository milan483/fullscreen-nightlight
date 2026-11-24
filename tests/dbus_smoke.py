"""Self-contained private D-Bus integration tests; never use the ambient bus."""
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

KWIN = "org.kde.KWin"
NL = "org.kde.KWin.NightLight"
HELPER = "org.fullscreennightlight.Inhibitor"
ROOT = Path(__file__).resolve().parents[1]
DBUS = "org.freedesktop.DBus"
PATH = "/org/freedesktop/DBus"
XML = '<node><interface name="'+NL+'"><method name="inhibit"><arg type="u" direction="out"/></method><method name="uninhibit"><arg type="u" direction="in"/></method></interface></node>'
FLAGS = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION


def call(conn, dest, path, interface, method, args=None, timeout=3000):
    return conn.call_sync(dest, path, interface, method, args, None,
                          Gio.DBusCallFlags.NO_AUTO_START, timeout, None)


def name(conn, method, service):
    args = GLib.Variant("(su)", (service, 4)) if method == "RequestName" else GLib.Variant("(s)", (service,))
    return call(conn, DBUS, PATH, DBUS, method, args).unpack()[0]


class Mock:
    def __init__(self, conn):
        self.conn = conn
        self.cookies = {}
        self.calls = []
        self.serial = 0
        self.failure = None
        self.info = Gio.DBusNodeInfo.new_for_xml(XML)
        self.object = conn.register_object("/org/kde/KWin/NightLight", self.info.interfaces[0], self.method, None, None)
        conn.signal_subscribe(DBUS, DBUS, "NameOwnerChanged", PATH, None,
                              Gio.DBusSignalFlags.NONE, self.changed, None)

    def changed(self, conn, sender, path, interface, signal, args, *rest):
        n, old, new = args.unpack()
        if n.startswith(":") and not new:
            self.cookies.pop(n, None)

    def method(self, conn, sender, path, interface, method, args, invocation):
        self.calls.append((sender, method))
        if self.failure == method + "-error":
            invocation.return_dbus_error("org.example.Failure", "injected error")
            return
        if method == "inhibit":
            self.serial += 1
            self.cookies.setdefault(sender, set()).add(self.serial)
            result = GLib.Variant("(u)", (self.serial,))
        elif self.failure == "uninhibit-noop":
            # Upstream silently ignores an unrecognized sender/cookie pair.
            result = GLib.Variant("()", ())
        else:
            cookies = self.cookies.get(sender, set())
            cookies.discard(args.unpack()[0])
            if not cookies:
                self.cookies.pop(sender, None)
            result = GLib.Variant("()", ())
        if self.failure == method + "-timeout":
            # Execute the operation but do not send its reply.
            return
        invocation.return_value(result)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # No standard service directories: the test bus cannot activate real services.
        config = Path(self.temp.name)/"bus.conf"
        config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth>'
                          '<policy context="default"><allow send_destination="*"/><allow receive_sender="*"/>'
                          '<allow own="*"/></policy></busconfig>')
        self.daemon = subprocess.Popen(["dbus-daemon", "--nofork", "--print-address=1",
                                         "--config-file="+str(config)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_daemon)
        self.address = self.daemon.stdout.readline().strip()
        self.assertTrue(self.address.startswith("unix:"), self.address)
        self.connections = []
        self.addCleanup(self.close_connections)
        self.loop = GLib.MainLoop()
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.addCleanup(self.stop_loop)
        self.mock = Mock(self.connect())
        self.claim(self.mock.conn, KWIN)
        self.claim(self.mock.conn, NL)
        self.thread.start()
        self.helper = None
        self.addCleanup(self.stop_helper)
        self.start_helper()

    def stop_daemon(self):
        if self.daemon.poll() is None:
            self.daemon.terminate()
            self.daemon.wait(timeout=5)
        self.daemon.stdout.close()

    def stop_loop(self):
        self.loop.quit()
        if self.thread.is_alive():
            self.thread.join(5)

    def close_connections(self):
        for conn in reversed(self.connections):
            if not conn.is_closed():
                conn.close_sync(None)

    def connect(self):
        conn = Gio.DBusConnection.new_for_address_sync(self.address, FLAGS, None, None)
        conn.set_exit_on_close(False)
        self.connections.append(conn)
        return conn

    def claim(self, conn, service):
        self.assertEqual(name(conn, "RequestName", service), 1)

    def start_helper(self):
        self.helper = subprocess.Popen([sys.executable, str(ROOT/"helper/inhibitor.py")],
            env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": self.address})
        def ready():
            if not self.has_owner(HELPER):
                return False
            try:
                self.refresh(False)
                return True
            except GLib.Error:
                return False
        self.wait(ready)

    def stop_helper(self):
        if self.helper is not None and self.helper.poll() is None:
            self.helper.kill()
            self.helper.wait(timeout=5)

    def wait(self, predicate, timeout=8):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(.03)
        self.fail("condition not met; calls=%r cookies=%r" % (self.mock.calls, self.mock.cookies))

    def refresh(self, state, conn=None):
        call(conn or self.mock.conn, HELPER, "/Inhibitor", HELPER, "Refresh",
             GLib.Variant("(b)", (state,)))

    def test_owner_replacement_requires_fresh_heartbeat(self):
        self.refresh(True)
        self.wait(lambda: len(self.mock.cookies)==1)
        old = self.mock
        replacement = Mock(self.connect())
        name(old.conn, "ReleaseName", NL)
        name(old.conn, "ReleaseName", KWIN)
        self.claim(replacement.conn, KWIN)
        self.claim(replacement.conn, NL)
        self.wait(lambda: not old.cookies)
        time.sleep(1.5)
        self.assertEqual(replacement.calls, [], "old lease migrated to new KWin")
        with self.assertRaisesRegex(GLib.Error, "AccessDenied"):
            self.refresh(True, old.conn)
        self.refresh(True, replacement.conn)
        self.wait(lambda: len(replacement.cookies)==1)
        self.refresh(False, replacement.conn)
        self.wait(lambda: not replacement.cookies)

    def test_nightlight_name_cycle_invalidates_cookie(self):
        self.refresh(True)
        self.wait(lambda: len(self.mock.cookies)==1)
        original = next(iter(self.mock.cookies))
        name(self.mock.conn, "ReleaseName", NL)
        # Model destruction of the old interface and loss of its cookie table.
        self.mock.cookies.clear()
        self.claim(self.mock.conn, NL)
        self.wait(lambda: len(self.mock.cookies)==1)
        self.assertNotIn(original, self.mock.cookies)
        self.refresh(False)
        self.wait(lambda: not self.mock.cookies)

    def test_endpoint_owner_mismatch(self):
        name(self.mock.conn, "ReleaseName", NL)
        impostor = self.connect()
        self.claim(impostor, NL)
        self.refresh(True)
        time.sleep(1.5)
        self.assertEqual(self.mock.calls, [])
        self.assertEqual(self.mock.cookies, {})
        name(impostor, "ReleaseName", NL)
        self.claim(self.mock.conn, NL)
        self.wait(lambda: len(self.mock.cookies)==1)

    def has_owner(self, name):
        return call(self.mock.conn, DBUS, PATH, DBUS, "NameHasOwner",
                    GLib.Variant("(s)", (name,))).unpack()[0]

    def test_authorization_idempotence_and_independent_inhibitor(self):
        other = self.connect()
        unique = other.get_unique_name()
        call(other, KWIN, "/org/kde/KWin/NightLight", NL, "inhibit")
        self.wait(lambda: unique in self.mock.cookies)
        independent = self.mock.cookies[unique].copy()
        with self.assertRaisesRegex(GLib.Error, "AccessDenied"):
            self.refresh(True, other)
        self.assertEqual(self.mock.cookies, {unique: independent})
        self.refresh(True)
        self.wait(lambda: len(self.mock.cookies)==2)
        for _ in range(4):
            self.refresh(True)
        with self.assertRaisesRegex(GLib.Error, "AccessDenied"):
            self.refresh(False, other)
        self.assertEqual(len(self.mock.cookies), 2)
        self.refresh(False)
        self.wait(lambda: self.mock.cookies == {unique: independent})
        self.refresh(False)
        self.assertEqual([method for _, method in self.mock.calls],
                         ["inhibit", "inhibit", "uninhibit"])
        self.assertEqual(self.mock.cookies, {unique: independent})

    def test_acquisition_timeout_after_server_success(self):
        self.mock.failure = "inhibit-timeout"
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        first = next(iter(self.mock.cookies))
        self.wait(lambda: not self.mock.cookies)
        self.assertFalse(self.has_owner(first))
        self.mock.failure = None
        # Repeated refreshes cannot bypass backoff.
        for _ in range(4):
            self.refresh(True)
        time.sleep(1)
        self.assertEqual(len(self.mock.calls), 1)
        self.wait(lambda: bool(self.mock.cookies))
        self.assertNotIn(first, self.mock.cookies)
        self.assertEqual([method for _, method in self.mock.calls], ["inhibit", "inhibit"])
        self.refresh(False)
        self.wait(lambda: not self.mock.cookies)

    def test_acquisition_error_recovers(self):
        self.mock.failure = "inhibit-error"
        self.refresh(True)
        self.wait(lambda: len(self.mock.calls)==1)
        first = self.mock.calls[0][0]
        self.wait(lambda: not self.has_owner(first))
        self.assertFalse(self.mock.cookies)
        self.mock.failure = None
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        self.assertNotIn(first, self.mock.cookies)
        self.refresh(False)
        self.wait(lambda: not self.mock.cookies)

    def test_release_error_timeout_and_unknown_cookie(self):
        for failure in ("uninhibit-error", "uninhibit-timeout", "uninhibit-noop"):
            with self.subTest(failure=failure):
                self.mock.failure = None
                self.refresh(True)
                self.wait(lambda: bool(self.mock.cookies))
                unique = next(iter(self.mock.cookies))
                self.mock.failure = failure
                self.refresh(False)
                self.wait(lambda: not self.mock.cookies and not self.has_owner(unique))
                self.assertFalse(self.mock.cookies)

    def test_helper_death_and_restart(self):
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        first = next(iter(self.mock.cookies))
        self.stop_helper()
        self.wait(lambda: not self.mock.cookies)
        self.assertFalse(self.has_owner(first))
        self.start_helper()
        self.assertFalse(self.mock.cookies)
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        self.assertNotIn(first, self.mock.cookies)
        self.refresh(False)
        self.wait(lambda: not self.mock.cookies)

    def test_lease_expiry_and_recovery(self):
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        first = next(iter(self.mock.cookies))
        self.wait(lambda: not self.mock.cookies and not self.has_owner(first), timeout=19)
        self.assertFalse(self.has_owner(first))
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        self.assertNotIn(first, self.mock.cookies)
        self.refresh(False)
        self.wait(lambda: not self.mock.cookies)

    def test_control_bus_disconnect_fails(self):
        self.refresh(True)
        self.wait(lambda: bool(self.mock.cookies))
        self.daemon.terminate()
        self.daemon.wait(timeout=5)
        self.assertEqual(self.helper.wait(timeout=5), 1)

    def test_duplicate_helper_fails(self):
        duplicate = subprocess.Popen([sys.executable, str(ROOT/"helper/inhibitor.py")],
            env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": self.address})
        try:
            self.assertNotEqual(duplicate.wait(timeout=5), 0)
        finally:
            if duplicate.poll() is None:
                duplicate.kill()
                duplicate.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
