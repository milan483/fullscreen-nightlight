# Fullscreen Night Light Inhibitor

KWin 6 JavaScript + Python Gio session-bus helper. Native fullscreen or conservatively detected borderless fullscreen inhibits Night Light globally. No scheduler or brightness changes. Uses a separate D-Bus connection, typed uint32 cookies, a 15s lease and 5s retry/heartbeat. Outputs and ExcludedApps are comma-separated KWin script config values; empty means no restriction. Borderless detection is conservative if maximizeMode is unavailable; occlusion is best effort. No telemetry or network calls.

## Test

Run `bash tests/verify.sh` from the repository root. See [development prerequisites and CI](docs/DEVELOPMENT.md). D-Bus integration runs against a mock on a private session bus, not the desktop.

## Install (only after approval)

Run python3 install.py --dry-run, then python3 install.py. Reload user systemd units with systemctl --user daemon-reload and the session bus activation files with busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig. Enable the script in System Settings > Window Management > KWin Scripts; Apply. Verify native fullscreen, restore, minimization and helper failure. No separate service enable is necessary. The installer records files it creates in a private ownership manifest at `$XDG_DATA_HOME/fullscreen-nightlight/ownership.json` (default data home: `~/.local/share`). Disable the script and stop the helper as described below before re-running with the same XDG roots to upgrade unchanged owned files. Identical pre-existing files are not adopted; conflicting or modified owned files cause a refusal. See [installer safety and recovery](docs/INSTALLER.md).

## Remove

Disable the script in System Settings first; verify unloaded and wait for the lease or stop the user service with systemctl --user stop fullscreen-nightlight.service. Then python3 install.py --uninstall; systemctl --user daemon-reload. Reload D-Bus activation files. Only unchanged manifest-owned files are removed, regardless of the current source version. If an owned file has changed, removal refuses the whole operation and preserves it. Empty directories and an empty ownership manifest may remain. Use the same XDG roots as installation; the installer does not remove legacy untracked files.

## Limitations

Per-output color temperature is not supported by KWin's inhibitor. Native fullscreen, borderless heuristics, KDE script timer lifecycle, login persistence and performance need native acceptance testing. Not a release. See [architecture and known gaps](docs/ARCHITECTURE.md) and [initialization issue](https://github.com/milan483/fullscreen-nightlight/issues/1).


## Attribution

This standalone project was informed by [Duskwatch](https://github.com/TroggoMan/duskwatch/tree/9d3818db8790f09bc8d6371b9e5e36dcce089231). The upstream MIT copyright and license notice are retained in LICENSE.
