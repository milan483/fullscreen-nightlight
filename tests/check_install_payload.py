"""Verify the generated installation payload without touching user XDG paths."""
import configparser
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install

with tempfile.TemporaryDirectory(prefix="fullscreen-nightlight-test-") as directory:
    base = Path(directory)
    os.environ["XDG_DATA_HOME"] = str(base / "data with spaces")
    os.environ["XDG_CONFIG_HOME"] = str(base / "config")
    files = install.payload()
    assert all(path.is_relative_to(base) for path in files)
    install.apply(files)
    install.apply(files)
    assert all(path.read_bytes() == contents for path, contents in files.items())
    unit = next(path for path in files if path.parent.name == "user")
    activation = next(path for path in files if path.parent.name == "services")
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(activation.read_text())
    section = config["D-BUS Service"]
    assert section["Name"] == install.NAME
    assert section["SystemdService"] == install.ID + ".service"
    helper = next(path for path in files if path.name == "inhibitor.py")
    assert shlex.split(section["Exec"]) == ["/usr/bin/python3", str(helper)]
    # Offline systemd parser/verification; not a live user-service start.
    subprocess.run(["systemd-analyze", "verify", "--man=no", str(unit)],
                   check=True, timeout=15)
    install.apply(files, uninstall=True)
    assert all(not path.exists() for path in files)
print("PASS: custom XDG paths, complete install/reinstall/remove, offline systemd verification")
