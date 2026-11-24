# Development and verification

Run from the repository or extracted source directory. Initial target: CachyOS, Plasma/KWin 6.8.3, Python 3.14.10, PyGObject 3.58.1, Node 26.13.1 (observed development host). These are observed versions, not minimum requirements.

## Setup

Use system Python with Gio bindings, GLib, D-Bus utilities, systemd-analyze, Bash, coreutils, Git, tar and Node.js for development. On Arch/CachyOS the relevant packages include python, python-gobject, glib2, dbus, systemd, bash, coreutils, git, tar and nodejs. No pip/npm dependencies. Check package availability first; package changes require separate approval on the host.

## Verification

```sh
bash tests/verify.sh
```

The entry point validates JS syntax/classification, Python unit tests, version consistency and package metadata, private D-Bus mock integration (self-created daemon with no system service directories; name changes, lease expiry, timeouts, authorization, independent cookies, helper death, bus loss), installer ownership/path/conflict/rollback/recovery regressions (including abrupt subprocess exit), and install/reinstall/remove in temporary XDG directories with generated systemd unit verification. Packaging tests exercise deterministic bytes, committed-source selection, version mismatch, missing/unsafe paths, archive members and checksum generation using disposable fixtures. It never enables the extension. Use PYTHON=/usr/bin/python3 when the default Python lacks system Gio bindings.

Native compositor acceptance is separate; see [compatibility and acceptance status](COMPATIBILITY.md) for the tested revision, historical results and explicitly deferred criteria. Mock integration does not exercise real KWin or the user systemd manager. Do not run actual installation or repeat native tests without approval.

## Release candidates

The canonical release version is in VERSION; KWin metadata and the first release heading in CHANGELOG.md must match. Initial version: 0.1.0-alpha.1. The builder reads a selected Git commit (not local edits) and produces a source archive with an explicit file allowlist, regular files, a single versioned top-level directory and SOURCE_COMMIT. It verifies each archive member against the selected commit; archive entries have stable order, zero timestamps/ownership, normalized 0644 file mode, and deterministic gzip headers. For the same commit and Python/zlib toolchain, repeated builds are byte-identical. Cross-toolchain bitwise reproducibility is not guaranteed. Invoke scripts with Bash/Python, not as executables. New distributed files require an explicit change to the allowlist.

From the repository, choose a new output directory whose parent exists:

```sh
mkdir -p dist
python3 tools/build_release.py --revision HEAD --output-dir dist/candidate
(cd dist/candidate && sha256sum -c SHA256SUMS)
```

The output directory must not already exist; if interrupted, inspect it and choose a new directory. The resulting files are `fullscreen-nightlight-<version>.tar.gz` and `SHA256SUMS`. The archive excludes Git metadata, repository-only files, local state, ignored/untracked files and build outputs. The source archive includes the tests and packaging code but no Git history; it can be installed/tested without Git checkout (Git itself is needed for packaging fixture tests). Do not rebuild from the extracted archive.

Before any release, verify the final merged commit and its exact CI candidate, not a PR merge ref. Download the retained GitHub Actions artifact for the successful push run on that commit into a fresh directory. Verify SHA256SUMS, inspect the archive member list, extract to a fresh directory, confirm SOURCE_COMMIT equals the selected revision, and run the full suite in an isolated environment if independently verifying. The workflow tests the extracted candidate and retains the same archive and checksum after tests; it does not create a tag or GitHub release. Preserve the tested bytes for any authorized release. Checksums are not signatures.

## CI

One Ubuntu 24.04 job runs on pull requests and pushes to main, with read-only contents permissions, checkout and artifact-upload actions pinned to verified immutable SHAs, no persisted checkout credentials, cancellation of superseded runs and job/test timeouts. Ubuntu packages are resolved from the runner's distribution repositories (not bit-for-bit pinned). The job builds a candidate from GITHUB_SHA (synthetic merge commit for PRs, exact main commit for pushes), checks the checksum, extracts it, checks SOURCE_COMMIT, runs the existing full verification suite from that extracted source, rechecks the original archive checksum and retains both original files as an internal CI artifact for 14 days. Failed checks prevent artifact upload. This verifies portable logic, package contents and service-file syntax, not Arch packaging or a live KWin compositor.

No publish/deploy/release workflow. Merging, tagging, release publication and repository visibility changes are separately authorized; the initial alpha is not a promise of wider compatibility.

## Changes

Use issue specifications and dedicated task branches/worktrees; draft PR descriptions link the issue, describe scope and checks, report evidence by revision, and track limitations. Preserve other work. No mandatory separate issue template for this small project.

## Troubleshooting

See [troubleshooting](TROUBLESHOOTING.md) and [installer safety](INSTALLER.md). Record actual CI links and native results in the relevant PR, not as timeless claims in this file.
