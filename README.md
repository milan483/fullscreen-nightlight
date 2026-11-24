# Fullscreen Night Light Inhibitor

KWin 6 JavaScript + Python Gio session-bus helper. Native fullscreen or conservatively detected borderless fullscreen inhibits Night Light globally. No scheduler or brightness changes. Uses a separate D-Bus connection, typed uint32 cookies, a 15s lease and 5s retry/heartbeat. Outputs and ExcludedApps are comma-separated KWin script config values; empty means no restriction. Borderless detection is conservative if maximizeMode is unavailable; occlusion is best effort. No telemetry or network calls.

## Test

Run `bash tests/verify.sh` from the repository root. See [development prerequisites and CI](docs/DEVELOPMENT.md). D-Bus integration runs against a mock on a private session bus, not the desktop.

## Install (only after approval)

Run python3 install.py --dry-run, then python3 install.py. Reload user systemd units with systemctl --user daemon-reload and the session bus activation files with busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig. Enable the script in System Settings > Window Management > KWin Scripts; Apply. Verify native fullscreen, restore, minimization and helper failure. No separate service enable is necessary. The installer refuses conflicts and copies exact files, no mutable symlinks. Uninstallation requires the matching source version.

## Remove

Disable the script in System Settings first; verify unloaded and wait for the lease or stop the user service with systemctl --user stop fullscreen-nightlight.service. Then python3 install.py --uninstall; systemctl --user daemon-reload. Reload D-Bus activation files. Empty directories may remain. Do not remove files modified by the user; installer refuses mismatches.

## Limitations

Per-output color temperature is not supported by KWin's inhibitor. Native fullscreen, borderless heuristics, KDE script timer lifecycle, login persistence and performance need native acceptance testing. Not a release. See [architecture and known gaps](docs/ARCHITECTURE.md) and [initialization issue](https://github.com/milan483/fullscreen-nightlight/issues/1).


## Attribution

This standalone project was informed by [Duskwatch](https://github.com/TroggoMan/duskwatch/tree/9d3818db8790f09bc8d6371b9e5e36dcce089231). The upstream MIT copyright and license notice are retained in LICENSE.
