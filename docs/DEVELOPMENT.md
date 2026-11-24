# Development and verification

Run from the repository root. Initial target: CachyOS, Plasma/KWin 6.8.3, Python 3.14.10, PyGObject 3.58.1, Node 26.13.1 (observed development host). These are observed versions, not minimum requirements.

## Setup
Use system Python with Gio bindings, GLib, D-Bus utilities, systemd-analyze, Bash, coreutils, and Node.js for development. On Arch/CachyOS the relevant packages include python, python-gobject, glib2, dbus, systemd, bash, coreutils and nodejs. No pip/npm dependencies. Check package availability first; package changes require separate approval on the host.

## Verification
```sh
bash tests/verify.sh
```
The entry point validates JS syntax/classification, Python unit tests, package metadata, private D-Bus mock integration, and install/reinstall/remove in temporary XDG directories with generated systemd unit verification. It never enables the extension. Use PYTHON=/usr/bin/python3 when the default Python lacks system Gio bindings. Native compositor acceptance is separate: fullscreen (Wayland/XWayland), borderless, minimize, close, activities/desktops, multiple displays, helper failure, script unload, restart and login, settings preservation, resource use. Do not run actual installation without approval.

## CI
One Ubuntu 24.04 job runs the same verification entry point on pull requests and pushes to main, with read-only contents permissions, checkout pinned to an immutable SHA, no persisted credentials, cancellation of superseded runs and job/test timeouts. Ubuntu packages are resolved from the runner's distribution repositories (not bit-for-bit pinned). This verifies portable logic and service-file syntax, not Arch packaging or a live KWin compositor. No publish/deploy/release workflow.

## Changes
Use issue specifications and dedicated task branches/worktrees; draft PR descriptions link the issue, describe scope and checks, report evidence by revision, and track limitations. Preserve other work. No mandatory separate issue template for this small project.

## Troubleshooting
Use the live D-Bus NightLight property only for authorized native verification. Never reset or unload NightLight to clear unrelated inhibitors. If installation is later approved, follow README removal steps. Record actual CI links and native results in the relevant PR, not as timeless claims in this file.
