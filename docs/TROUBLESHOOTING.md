# Troubleshooting

Start with the [requirements and installation procedure](../README.md) and [compatibility limits](COMPATIBILITY.md). Do not use root, change Night Light settings as a workaround, or release/reset other applications' inhibitors.

## Extension does not appear

Confirm a Plasma 6 Wayland session, correct XDG roots and that installation completed without conflict. Reopen System Settings > Window Management > KWin Scripts. Enable the script and Apply. If the installer refused, consult [installer safety](INSTALLER.md); do not force installation or manually delete the ownership manifest.

## Fullscreen does not inhibit Night Light

Check that Night Light is enabled in KDE, the script is enabled, the application is actually fullscreen (or meets the conservative borderless rule), and its output and identifiers are not excluded. Check the KWin Debug Console for actual resourceClass, desktopFileName and output name; ordinary maximized windows are not necessarily eligible. The following diagnostics are read-only:

```sh
systemctl --user status fullscreen-nightlight.service
journalctl --user -u fullscreen-nightlight.service -b --no-pager -n 50
busctl --user get-property org.kde.KWin /org/kde/KWin/NightLight org.kde.KWin.NightLight inhibited
```

The aggregate inhibited property cannot identify which application owns an inhibitor. A service inactive before the first heartbeat is not necessarily a failure. Confirm D-Bus activation files and user systemd registration using the README's reload steps if installation was completed. Do not invoke the helper's Refresh method manually; it is restricted to the current KWin owner.

## Night Light remains inhibited after leaving fullscreen

Check for other eligible windows and independent inhibitors. Restore or minimize the fullscreen window. Allow the periodic refresh and lease time to elapse (15 seconds nominal, not a wall-clock guarantee). For safe rollback, disable the script, Apply and stop only this project's helper using the README removal procedure. Do not reset Night Light or restart KWin to clear unrelated cookies. If aggregate inhibition remains true it may belong to another application.

## Installer refuses or an operation was interrupted

Review the refusal and the affected path. Do not chmod or overwrite a file automatically simply because it has matching bytes. Verify its provenance, back up important data, and resolve conflicts deliberately. Re-run the installer with the original XDG roots after reviewing the [transaction recovery procedure](INSTALLER.md). If recovery refuses, retain its manifest and staging files for investigation.

## Reporting a problem

Include the version and source commit (SOURCE_COMMIT in the archive, or Git revision), Plasma/KWin version, session type, output count, observed window properties and a minimal reproduction. Include relevant sanitized service logs and the expected/actual inhibition state. Omit personal paths, window titles, tokens and unrelated logs. Report security concerns privately as described in [SECURITY.md](../SECURITY.md).
