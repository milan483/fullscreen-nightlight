# Repository guidance

## Project
Fullscreen Night Light Inhibitor is a user-local KWin 6 script plus Python Gio helper. See [architecture](docs/ARCHITECTURE.md) and [development](docs/DEVELOPMENT.md). The initial target is CachyOS/Plasma 6 Wayland; other distributions and KWin versions are not certified.

## Invariants
- Never change the user's Night Light schedule, temperature, brightness, or rendering configuration to implement inhibition.
- Own only our inhibitor cookie, on its own session-bus connection. Refresh requests must be from the current KWin owner. Expire stale leases and release on loss of the connection.
- No root, telemetry, runtime network access, or unnecessary dependencies. Installation must avoid overwriting unrelated files; do not install or activate on a live desktop without approval.
- KWin API assumptions require native verification. Node tests exercise logic, not KWin bindings. Run D-Bus tests only on a private bus.

## Development
Use `bash tests/verify.sh` from the repository root. Runtime code is in `kwin-script/` and `helper/`; installer in `install.py`. Keep existing test coverage, add relevant regression tests with behavioral changes, and document unverified native behavior. See development documentation for CI and dependencies.

## Context
Follow the applicable canonical development workflow and authorization boundaries; do not duplicate it here. Use the issue as the task specification and the draft PR as the active checkpoint. Reconcile current Git refs, actual CI evidence and unresolved native acceptance on resumption. See [issue #1](https://github.com/milan483/fullscreen-nightlight/issues/1) for onboarding. No automatic release or deployment.
