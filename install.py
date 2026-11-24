#!/usr/bin/env python3
"""Copy the reviewed payload; never replace existing nonidentical files."""
import argparse
import os
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parent
ID = "fullscreen-nightlight"
NAME = "org.fullscreennightlight.Inhibitor"

def xdg(name, fallback):
    p = Path(os.environ.get(name) or fallback)
    if not p.is_absolute() or any(c in str(p) for c in "\n\r\0"):
        raise ValueError("XDG paths must be absolute and single-line")
    return p

def unit_quote(s):
    return '"' + s.replace("\\","\\\\").replace('"','\\"').replace("%","%%").replace("$","$$") + '"'

def payload():
    home = Path.home()
    data = xdg("XDG_DATA_HOME",home/".local/share")
    conf = xdg("XDG_CONFIG_HOME",home/".config")
    helper = data/ID/"inhibitor.py"
    script = data/"kwin/scripts"/ID
    service = conf/"systemd/user"/(ID+".service")
    activation = data/"dbus-1/services"/(NAME+".service")
    unit = ("[Unit]\nDescription=Fullscreen Night Light inhibitor\n"
        "[Service]\nType=dbus\nBusName="+NAME+"\nExecStart=/usr/bin/python3 "
        +unit_quote(str(helper))+"\nNoNewPrivileges=true\n"
        "Restart=on-failure\nRestartSec=5\n")
    dbus = ("[D-BUS Service]\nName="+NAME+"\nExec=/usr/bin/python3 "
        +shlex.quote(str(helper))+"\nSystemdService="+ID+".service\n")
    return {helper:(ROOT/"helper/inhibitor.py").read_bytes(),
        script/"metadata.json":(ROOT/"kwin-script/metadata.json").read_bytes(),
        script/"contents/code/main.js":(ROOT/"kwin-script/contents/code/main.js").read_bytes(),
        service:unit.encode(),activation:dbus.encode()}

def exists(p): return p.exists() or p.is_symlink()

def apply(files, uninstall=False, dry=False):
    for path, data in files.items():
        if exists(path) and (path.is_symlink() or not path.is_file() or path.read_bytes()!=data):
            raise RuntimeError("Conflict (untouched): "+str(path))
    if dry:
        for path in files: print(("remove " if uninstall else "install ")+str(path))
        return
    if uninstall:
        for path in files:
            if exists(path): path.unlink()
        return
    created=[]
    try:
        for path,data in files.items():
            if exists(path): continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("xb") as f:
                created.append(path)
                f.write(data)
            path.chmod(0o644)
    except Exception:
        for path in reversed(created): path.unlink()
        raise

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--uninstall",action="store_true")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    apply(payload(),args.uninstall,args.dry_run)
    print("No service or KWin settings changed by this command.")
