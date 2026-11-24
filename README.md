# Fullscreen Night Light Inhibitor

A user-local KWin 6 script and Python Gio helper that temporarily inhibits KDE Night Light while an eligible fullscreen window is visible. Native fullscreen and conservative borderless fullscreen detection are supported. Night Light scheduling, temperature and brightness settings are not changed.

This is an experimental alpha, targeting CachyOS with KDE Plasma 6 on Wayland. See [version](VERSION), [changelog](CHANGELOG.md) and [compatibility and known limitations](docs/COMPATIBILITY.md) before installing. It is not a general Plasma 6 compatibility guarantee. Inhibition is global across all displays, even when an output filter is configured. No telemetry or runtime network access.

## Requirements

- KDE Plasma/KWin 6 Wayland session with Night Light and a user systemd/D-Bus session.
- System Python at `/usr/bin/python3` with PyGObject (Gio/GLib); D-Bus and systemd utilities.
- On CachyOS/Arch: `python`, `python-gobject`, `glib2`, `dbus`, `systemd`. No pip packages, Node.js or root needed at runtime. See [installer safety](docs/INSTALLER.md) for supported XDG paths/filesystems.

## Install

Use the source directory or extract the versioned source archive into a fresh directory. For a distributed archive, obtain its accompanying SHA256SUMS from the trusted distribution channel and run `sha256sum -c SHA256SUMS` before extraction. The checksum detects corruption; it is not a signature. See [release verification](docs/DEVELOPMENT.md#release-candidates).

Run these commands as your desktop user from the source directory, not with sudo:

```sh
python3 install.py --dry-run
python3 install.py
systemctl --user daemon-reload
busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig
```

If dry-run reports a conflict, stop and inspect it before installing. Enable **Fullscreen Night Light Inhibitor** in System Settings > Window Management > KWin Scripts and Apply. No separate systemd service enable is required; the helper is D-Bus activated. With Night Light enabled, try a native fullscreen window, restore/minimize it and confirm that Night Light resumes according to its own schedule.

The installer creates an ownership manifest at `$XDG_DATA_HOME/fullscreen-nightlight/ownership.json` (default: `~/.local/share/fullscreen-nightlight/ownership.json`). Retain it. Safe identical pre-existing files are not adopted; conflicting files, unsafe permissions and modified owned files cause a refusal during installation. Stop/disable the extension before upgrading, then rerun installation with the same XDG roots.

## Configuration

Both optional keys are in the `Script-fullscreen-nightlight` group of `kwinrc`. Empty or absent values impose no restriction.

| Key | Meaning |
| --- | --- |
| Outputs | Comma-separated KWin output names (case-sensitive); e.g. DP-1. Limits which windows can trigger **global** inhibition. |
| ExcludedApps | Comma-separated exact resource class or desktop file identifiers (case-insensitive). Not window titles or wildcards. |

To change these keys, disable the script in System Settings and Apply first. Record the previous values (the example uses a sentinel to distinguish absent keys from empty ones); do not replace unrelated KWin settings. Example commands, with identifiers adjusted to your system:

```sh
kscreen-doctor -o
kreadconfig6 --file kwinrc --group Script-fullscreen-nightlight --key Outputs --default '<absent>'
kreadconfig6 --file kwinrc --group Script-fullscreen-nightlight --key ExcludedApps --default '<absent>'
kwriteconfig6 --notify --file kwinrc --group Script-fullscreen-nightlight --key Outputs DP-1
kwriteconfig6 --notify --file kwinrc --group Script-fullscreen-nightlight --key ExcludedApps 'example-app,org.example.Other'
```

Identify application properties using KWin's Debug Console (resourceClass and desktopFileName). Re-enable the script and Apply, then verify the intended fullscreen behavior. To reset either key to its default, disable the script and use the corresponding command, then re-enable:

```sh
kwriteconfig6 --notify --file kwinrc --group Script-fullscreen-nightlight --key Outputs --delete
kwriteconfig6 --notify --file kwinrc --group Script-fullscreen-nightlight --key ExcludedApps --delete
```

These configuration commands are optional and change only this script's keys. The installer itself does not edit KWin configuration. See [troubleshooting](docs/TROUBLESHOOTING.md) if settings do not take effect.

## Remove

Disable the script in System Settings and Apply before stopping the helper. Then run from the source directory, using the same XDG roots as installation:

```sh
systemctl --user stop fullscreen-nightlight.service
python3 install.py --uninstall
systemctl --user daemon-reload
busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig
```

Only unchanged manifest-owned files are removed. If an owned file has changed, removal refuses and preserves it. Empty directories and an empty ownership manifest may remain; legacy untracked files are not removed. Optional script configuration keys are left intact unless you explicitly remove them. See [installer safety and recovery](docs/INSTALLER.md).

## Development

Run `bash tests/verify.sh` from the source directory. D-Bus integration uses a private daemon, not the desktop. See [development and release verification](docs/DEVELOPMENT.md), [architecture](docs/ARCHITECTURE.md) and [security policy](SECURITY.md).

## Attribution

This standalone project was informed by [Duskwatch](https://github.com/TroggoMan/duskwatch/tree/9d3818db8790f09bc8d6371b9e5e36dcce089231). The upstream MIT copyright and license notice are retained in [LICENSE](LICENSE).
