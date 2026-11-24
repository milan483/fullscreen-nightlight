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
LEASE = 15
XML = '<node><interface name="'+NAME+'"><method name="Refresh"><arg type="b" direction="in"/></method></interface></node>'

class Lease:
    def __init__(self, backend, clock=time.monotonic):
        self.backend, self.clock = backend, clock
        self.until = 0
    def refresh(self, active):
        self.until = self.clock()+LEASE if active else 0
    def tick(self):
        self.backend.apply(self.clock() < self.until)

class Backend:
    def __init__(self, bus):
        self.bus = bus
        self.conn = self.cookie = self.owner = None
        self.retry_at = 0
    def get_owner(self):
        return self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", "GetNameOwner", GLib.Variant("(s)", (KWIN,)),
            GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    def close(self):
        conn = self.conn
        self.conn = self.cookie = self.owner = None
        if conn is not None:
            try:
                conn.close_sync(None)
            except GLib.Error:
                # Exiting guarantees loss of the connection even if closing failed.
                raise SystemExit("could not close inhibitor connection")
    def call(self, method, params, result):
        return self.conn.call_sync(self.owner, "/org/kde/KWin/NightLight", NL,
            method, params, GLib.VariantType.new(result), Gio.DBusCallFlags.NONE, 1000, None)
    def apply(self, active):
        if not active and self.conn is None:
            return
        if active and time.monotonic() < self.retry_at:
            return
        try:
            if not active:
                if self.cookie is not None:
                    self.call("uninhibit", GLib.Variant("(u)", (self.cookie,)), "()")
                self.close()
                return
            owner = self.get_owner()
            if self.conn is not None and (self.conn.is_closed() or owner != self.owner):
                self.close()
            if self.conn is None:
                address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
                flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
                self.conn = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
                self.conn.set_exit_on_close(False)
                self.owner = owner
                self.cookie = self.call("inhibit", None, "(u)").unpack()[0]
        except GLib.Error as exc:
            logging.warning("Night Light transition failed: %s", exc)
            # A timeout may hide a successful server-side acquisition.
            # Close rather than losing the cookie or acquiring duplicates.
            self.close()
            self.retry_at = time.monotonic()+5

def main():
    logging.basicConfig(level=logging.INFO)
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    backend = Backend(bus)
    lease = Lease(backend)
    loop = GLib.MainLoop()
    def tick():
        lease.tick()
        return GLib.SOURCE_CONTINUE
    def refresh(connection, sender, path, interface, method, params, invocation):
        try:
            authorized = sender == backend.get_owner()
        except GLib.Error:
            authorized = False
        if not authorized:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "Only KWin may refresh")
            return
        lease.refresh(params.unpack()[0])
        invocation.return_value(None)
        tick()
    info = Gio.DBusNodeInfo.new_for_xml(XML)
    bus.register_object("/Inhibitor", info.interfaces[0], refresh, None, None)
    Gio.bus_own_name_on_connection(bus, NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE, None, lambda *_: loop.quit())
    GLib.timeout_add_seconds(1, tick)
    try:
        loop.run()
    finally:
        backend.close()
if __name__ == "__main__":
    main()
