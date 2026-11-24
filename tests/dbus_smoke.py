"""Run exclusively inside dbus-run-session, never against the real KWin."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
import gi
gi.require_version("Gio","2.0")
from gi.repository import Gio, GLib
assert os.environ.get("FULLSCREEN_TEST_BUS")=="1"
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
name="org.kde.KWin"
bus.call_sync("org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","RequestName",GLib.Variant("(su)",(name,4)),None,Gio.DBusCallFlags.NONE,1000,None)
calls=[]
fail_release=False
connections=set()
xml='<node><interface name="org.kde.KWin.NightLight"><method name="inhibit"><arg type="u" direction="out"/></method><method name="uninhibit"><arg type="u" direction="in"/></method></interface></node>'
def method(c,s,p,i,m,args,inv):
    calls.append((m,args.unpack()))
    if m=="inhibit": connections.add(s)
    elif fail_release:
        inv.return_dbus_error("org.example.Failure", "simulated release failure")
        return
    else: connections.discard(s)
    inv.return_value(GLib.Variant("(u)",(42,)) if m=="inhibit" else GLib.Variant("()",()))
info=Gio.DBusNodeInfo.new_for_xml(xml)
bus.register_object("/org/kde/KWin/NightLight",info.interfaces[0],method,None,None)
def name_changed(c,s,p,i,m,args,*rest):
    n,old,new=args.unpack()
    if not new: connections.discard(n)
bus.signal_subscribe("org.freedesktop.DBus","org.freedesktop.DBus","NameOwnerChanged",
    "/org/freedesktop/DBus",None,Gio.DBusSignalFlags.NONE,name_changed,None)
loop=GLib.MainLoop()
thread=threading.Thread(target=loop.run,daemon=True)
thread.start()
helper=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/"helper/inhibitor.py")])
dest="org.fullscreennightlight.Inhibitor"
def refresh(state, connection=bus):
    connection.call_sync(dest,"/Inhibitor",dest,"Refresh",GLib.Variant("(b)",(state,)),None,Gio.DBusCallFlags.NONE,3000,None)
def wait_for(predicate):
    end=time.monotonic()+8
    while time.monotonic()<end:
        if predicate(): return
        time.sleep(.05)
    raise AssertionError(calls)
try:
    def ready():
        try:
            refresh(False)
            return True
        except GLib.Error: return False
    wait_for(ready)
    address=Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION,None)
    other=Gio.DBusConnection.new_for_address_sync(address,Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,None)
    try:
        refresh(True,other)
        raise AssertionError("unauthorized sender accepted")
    except GLib.Error as exc:
        assert "AccessDenied" in str(exc), exc
    finally: other.close_sync(None)
    refresh(True)
    wait_for(lambda: len(calls)==1)
    refresh(True)
    refresh(False)
    wait_for(lambda: len(calls)==2)
    assert calls==[("inhibit",()),("uninhibit",(42,))], calls
    assert not connections
    refresh(True)
    wait_for(lambda: len(connections)==1)
    fail_release=True
    refresh(False)
    wait_for(lambda: not connections)
    fail_release=False
    refresh(True)
    wait_for(lambda: len(connections)==1)
    helper.terminate()
    helper.wait(timeout=5)
    wait_for(lambda: not connections)
    helper=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/"helper/inhibitor.py")])
    wait_for(ready)
    refresh(True)
    wait_for(lambda: len(connections)==1)
    refresh(False)
    wait_for(lambda: not connections)
    print("PASS: authorization, uint32 cookie, idempotent refresh, release failure cleanup, helper death and restart")
finally:
    helper.terminate()
    helper.wait(timeout=5)
    loop.quit()
