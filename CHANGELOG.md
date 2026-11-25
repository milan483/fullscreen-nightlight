# Changelog

## 0.1.0-alpha.1

Initial experimental alpha candidate. The version identifies the candidate; it does not imply a published release.

- Fullscreen Night Light inhibition via KWin 6 and a separate, sender-checked Gio D-Bus helper.
- Conservative borderless detection, best-effort occlusion, desktop/activity filtering, optional output and application exclusions.
- Lease expiry, retry backoff, cookie ownership isolation and recovery from ambiguous D-Bus transitions.
- User-local installer with ownership tracking, dry-run, conflict detection, staged rollback and recovery; unsafe symlinks, hardlinks and group/world-writable files rejected.
- Native single-display Wayland and XWayland application acceptance on CachyOS/Plasma 6.8.3; private-bus and installer automated checks.
- Versioned source archive, source-commit record, SHA-256 checksum and extracted-source verification in CI.

See [compatibility](docs/COMPATIBILITY.md) for deferred performance/session-lifecycle checks and unsupported or unverified environments. No KDE Store or distribution package is provided.
