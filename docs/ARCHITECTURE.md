# Architecture

## Scope
Temporarily inhibit KDE Night Light while an eligible fullscreen window exists. KWin retains control of temperature and scheduling. Inhibition is global across outputs; an output allowlist controls triggers, not color temperature per screen.

## Components
- `kwin-script/contents/code/main.js`: window eligibility, best-effort occlusion, event coalescing (100 ms), periodic refresh (5 s). Optional comma-separated KWin script configuration keys: Outputs and ExcludedApps.
- `helper/inhibitor.py`: session-bus service org.fullscreennightlight.Inhibitor, Refresh(boolean), sender checked against current org.kde.KWin owner. A 15 s lease controls a dedicated D-Bus connection to the NightLight API. Typed unsigned cookies, 5 s retry delay, connection closure on ambiguous transitions.
- `install.py`: copies a fixed payload and generates D-Bus and systemd service files from XDG paths; no service activation or desktop configuration writes. Removal currently requires matching bytes and source version.

## Trust and failure boundaries
Only the current KWin bus owner can request refresh; same-user processes remain outside a strong security boundary. Never release another application's cookie. No network calls. The dedicated connection is intended to release the inhibitor when lost; actual KWin behavior requires native verification. On restart, heartbeat reconciles state; lease expires if script stops. Mock tests are not evidence of actual compositor behavior.

## Known limitations
Borderless detection is conservative when maximizeMode is absent; occlusion is approximate. Native window API/timer behavior, lock screen, multi-monitor transitions, plugin reload, compositor restart and login persistence remain unverified. Installer lacks an ownership manifest, upgrade mechanism, and complete ancestor-symlink defenses. The existing smoke test alone trusts an environment flag; use the private-bus verification entry point. Reliability improvements are separate from initialization.

## Origins
Standalone implementation informed by Duskwatch at 9d3818db8790f09bc8d6371b9e5e36dcce089231. Retain the upstream MIT notice in LICENSE. See [upstream](https://github.com/TroggoMan/duskwatch/tree/9d3818db8790f09bc8d6371b9e5e36dcce089231).
