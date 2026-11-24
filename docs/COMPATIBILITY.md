# Compatibility and acceptance status

## Target

The initial alpha targets CachyOS, KDE Plasma/KWin 6.8.3, Wayland, with one physical display (DP-1, 1920x1080 at 100 Hz in the recorded test environment). XWayland 24.1.15 applications were exercised inside that Wayland session. Versions are observed test versions, not minimum requirements. Native results below were recorded at revision `27ffd5dc0085347a8b4ce028bff98dc632bd1ee4`; the subsequent installer permission fix in PR #8 and release preparation do not alter the window-detection or helper runtime logic. The final packaged revision requires automated verification; these are historical native observations, not a fresh test of every alpha change.

| Area | Status |
| --- | --- |
| Native Wayland and XWayland fullscreen / restore / minimize / focus transitions | PASS on tested session |
| Borderless classification, multiple eligible windows, desktop/activity changes, exclusion filters | PASS on tested cases |
| Full and partial cover, opaque and transparent windows | PASS for tested cases; heuristic, not pixel-level visibility |
| Output allowlist | PASS on one display; physical multi-monitor SKIPPED (second display unavailable) |
| D-Bus inhibition, helper death, lease and independent inhibitor preservation | PASS on tested cases; additional fault injection verified on private bus |
| User-local install, isolated upgrade/reinstall, conflict preservation, cleanup | PASS on tested cases; no claim of live upgrades across released versions |
| Compositor/plugin restart, suspend/resume, login persistence | SKIPPED/deferred; not certified |
| Native bus disruption | UNVERIFIED; deliberately not injected |
| Repeated performance characterization | PARTIAL/deferred (10 of 12 valid intervals) |
| Physical color convergence | UNVERIFIED; D-Bus state/timing measured instead |

Other Plasma/KWin 6 releases, other distributions, physical multi-display setups and non-Wayland Plasma sessions are unverified. Plasma 5 and non-KWin compositors are outside the intended scope. Node tests do not verify KWin bindings; private-bus tests do not certify the live user session.

## Performance evidence

Recorded controlled static-window measurements were 120 seconds each. The planned three repetitions per condition were not completed: two valid idle intervals without and with the extension, three fullscreen intervals without and with it. Invalid intervals were excluded. User deferred the remaining idle repetitions and lifecycle testing.

| Condition | Valid runs | KWin median CPU (% of one core) | Observed range |
| --- | ---: | ---: | ---: |
| Idle without extension | 2 | 2.442 | 2.400–2.483 |
| Idle with extension | 2 | 1.850 | 1.367–2.333 |
| Fullscreen without extension | 3 | 1.100 | 1.092–1.100 |
| Fullscreen with extension | 3 | 1.108 | 1.075–1.125 |

Helper CPU was approximately 0.008–0.017% of one core, RSS approximately 31 MiB; sustained intervals observed 24 refreshes per 120 seconds without redundant inhibit/release calls. Ten normal transitions had a pooled median of 122 ms and maximum of 133 ms for inhibition-state changes. These limited observations do not establish a causal overhead estimate, a gaming/FPS benchmark, a hard latency guarantee or a full performance acceptance pass.

Development evidence: [native acceptance checkpoint D](https://github.com/milan483/fullscreen-nightlight/issues/7#issuecomment-7137150882), [performance checkpoint S](https://github.com/milan483/fullscreen-nightlight/issues/7#issuecomment-7138987770), [release-readiness audit](https://github.com/milan483/fullscreen-nightlight/issues/7#issuecomment-7139387557), [installer fix #8](https://github.com/milan483/fullscreen-nightlight/pull/8). Repository evidence links may require authorized access while the repository is private.

## Known limitations

Inhibition is global. Output filters select trigger windows, not independent color temperature on each display. Borderless detection deliberately avoids treating ordinary maximized windows as fullscreen; some borderless games may not be detected. Occlusion is best effort and may misclassify windows with per-pixel transparency or changing opacity until the next refresh. Multiple output interactions, lifecycle recovery and remaining performance repetitions should be evaluated independently after installation; do not assume them supported based on the alpha designation.
