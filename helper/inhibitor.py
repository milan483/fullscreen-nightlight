#!/usr/bin/env python3
"""Own only our own inhibitor; loss of the private bus connection releases it."""
import logging
import time
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

NAME = "org.fullscreennightlight.Inhibitor"
KWIN = "org.kde.KWin"
NL = "org.kde.KWin.NightLight"
DBUS = "org.freedesktop.DBus"
BUS_PATH = "/org/freedesktop/DBus"
LEASE = 15
RETRY = 5
XML = '<node><interface name="'+NAME+'"><method name="Refresh"><arg type="b" direction="in"/></method></interface></node>'


class Lease:
    def __init__(self, backend, clock=time.monotonic):
        self.backend, self.clock = backend, clock
        self.owner = None
        self.until = 0

    def refresh(self, active, owner):
        self.owner = owner if active else None
        self.until = self.clock()+LEASE if active else 0

    def invalidate(self, owner):
        if self.owner == owner:
            self.refresh(False, owner)

    def tick(self):
        if self.clock() >= self.until:
            self.refresh(False, self.owner)
        self.backend.apply(self.owner)


class EndpointUnavailable(Exception):
    pass


class CleanupError(RuntimeError):
    pass


class Backend:
    def __init__(self, bus, clock=time.monotonic):
        self.bus, self.clock = bus, clock
        self.conn = self.cookie = self.owner = None
        self.retry_at = 0
        self.failing = False

    def get_owner(self, name=KWIN):
        return self.bus.call_sync(DBUS, BUS_PATH, DBUS, "GetNameOwner",
            GLib.Variant("(s)", (name,)), GLib.VariantType.new("(s)"),
            Gio.DBusCallFlags.NO_AUTO_START, 1000, None).unpack()[0]

    def close(self):
        conn = self.conn
        if conn is not None and not conn.is_closed():
            try:
                conn.close_sync(None)
            except GLib.Error as exc:
                if not conn.is_closed():
                    # Do not forget a possibly live inhibitor connection. The
                    # main loop must stop with failure so process exit closes it.
                    raise CleanupError("could not close inhibitor connection") from exc
            if not conn.is_closed():
                raise CleanupError("inhibitor connection remains open")
        self.conn = self.cookie = self.owner = None

    def call(self, method, params, result):
        return self.conn.call_sync(self.owner, "/org/kde/KWin/NightLight", NL,
            method, params, GLib.VariantType.new(result),
            Gio.DBusCallFlags.NO_AUTO_START, 1000, None)

    def open(self, owner):
        # Both names must belong to the compositor that authorized the lease.
        # Send only to its unique name, never an activatable/replacement service.
        if self.get_owner() != owner or self.get_owner(NL) != owner:
            raise EndpointUnavailable("KWin/NightLight owner mismatch")
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        self.conn = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
        self.conn.set_exit_on_close(False)
        # Unique names are only unique within one bus daemon. Do not send
        # a cookie request to a reused name on a replacement session bus.
        if self.bus.is_closed() or self.conn.get_guid() != self.bus.get_guid():
            raise EndpointUnavailable("session bus changed")
        self.owner = owner
        self.cookie = self.call("inhibit", None, "(u)").unpack()[0]

    def transition_failed(self, exc):
        if not self.failing:
            logging.warning("Night Light transition failed; retrying at most every %ss: %s", RETRY, exc)
            self.failing = True
        # A timeout may hide a successful server-side acquisition/release.
        # Close before retrying; never guess a cookie or reuse this sender.
        self.close()
        self.retry_at = self.clock()+RETRY

    def apply(self, owner):
        try:
            if self.conn is not None and self.conn.is_closed():
                self.transition_failed("inhibitor connection closed")
            if owner is None:
                if self.cookie is not None:
                    self.call("uninhibit", GLib.Variant("(u)", (self.cookie,)), "()")
                self.close()
                return
            if self.conn is not None and self.owner != owner:
                self.close()
            if self.conn is not None or self.clock() < self.retry_at:
                return
            self.open(owner)
            if self.failing:
                logging.info("Night Light inhibition recovered")
                self.failing = False
            self.retry_at = 0
        except (GLib.Error, EndpointUnavailable) as exc:
            self.transition_failed(exc)


def main():
    logging.basicConfig(level=logging.INFO)
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    # A lost service/control bus must exit unsuccessfully, not silently quit
    # or rely on Gio's default SIGTERM (a clean exit under systemd).
    bus.set_exit_on_close(False)
    backend = Backend(bus)
    lease = Lease(backend)
    loop = GLib.MainLoop()
    failed = False
    acquired = False

    def acquired_name(*_):
        nonlocal acquired
        acquired = True

    def fail(message):
        nonlocal failed
        if not failed:
            logging.error("%s", message)
        failed = True
        loop.quit()

    def tick():
        if failed:
            return GLib.SOURCE_REMOVE
        try:
            lease.tick()
        except CleanupError as exc:
            fail(str(exc))
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def changed(connection, sender, path, interface, signal, params, *rest):
        name, old, new = params.unpack()
        if failed or not old or old == new:
            return
        if name == KWIN:
            lease.invalidate(old)
        # Even a NightLight name cycle with the same KWin owner invalidates
        # the cookie. Drop the entire sender, not an unverified cookie.
        if name in (KWIN, NL) and backend.owner == old:
            try:
                backend.close()
            except CleanupError as exc:
                fail(str(exc))

    def refresh(connection, sender, path, interface, method, params, invocation):
        if failed or not acquired:
            invocation.return_dbus_error(DBUS+".Error.Failed", "Helper is not serving")
            return
        try:
            authorized = sender == backend.get_owner()
        except GLib.Error:
            authorized = False
        if not authorized:
            invocation.return_dbus_error(DBUS+".Error.AccessDenied", "Only KWin may refresh")
            return
        lease.refresh(params.unpack()[0], sender)
        invocation.return_value(None)
        tick()

    info = Gio.DBusNodeInfo.new_for_xml(XML)
    registration = bus.register_object("/Inhibitor", info.interfaces[0], refresh, None, None)
    subscriptions = [
        bus.signal_subscribe(DBUS, DBUS, "NameOwnerChanged", BUS_PATH, name,
                             Gio.DBusSignalFlags.NONE, changed, None)
        for name in (KWIN, NL)
    ]
    closed = bus.connect("closed", lambda *_: fail("Control bus connection closed"))
    ownership = Gio.bus_own_name_on_connection(bus, NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
        acquired_name, lambda *_: fail("Helper service name lost or unavailable"))
    timer = GLib.timeout_add_seconds(1, tick)
    try:
        if bus.is_closed():
            fail("Control bus connection closed")
        if not failed:
            loop.run()
    finally:
        # Drop inhibition before allowing a replacement helper to claim NAME.
        # If cleanup fails, process exit drops both connections.
        backend.close()
        if GLib.MainContext.default().find_source_by_id(timer) is not None:
            GLib.source_remove(timer)
        Gio.bus_unown_name(ownership)
        for subscription in subscriptions:
            bus.signal_unsubscribe(subscription)
        bus.disconnect(closed)
        bus.unregister_object(registration)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
