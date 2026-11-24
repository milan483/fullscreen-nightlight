# Installer safety and recovery

## Supported use

Run the installer as the desktop user, not root. It writes only the five fixed payload destinations under the XDG data/config homes and its own transaction state. It does not enable KWin scripts, start or stop services, reload configuration, or change Night Light settings. Stop/disable the extension before upgrading or removing it, following the README. Do not use the installer to change live configuration during development.

Custom XDG roots must be absolute, non-root paths without parent references, control characters or backslashes. The installer rejects symlink components, unsafe directory ownership/permissions, special files, multiply linked files, and overlapping file destinations. Existing XDG roots and payload parents must be owned by the user and not group/world writable; ancestors must be owned by the user or root and not group/world writable, except root-owned sticky directories such as /tmp. Symlinked homes or XDG directories are not supported. Use local filesystems supporting hardlinks, directory fsync and flock.

## Ownership and upgrades

The version-1 JSON manifest is at the data home's fullscreen-nightlight/ownership.json (mode 0600). It binds to both XDG roots, uses a fixed allowlist of payload identifiers, and records device/inode, SHA-256 and mode of files created by the installer. Keep this manifest with the installation. It is not a cryptographic trust boundary against the desktop user.

- Reinstalling unchanged files is a no-op; an owned missing file can be recreated.
- Upgrading replaces only unchanged owned files; removal uses ownership records, not the current source bytes.
- A pre-existing identical file is left unowned only if it passes the file safety checks, even if from the old installer. A pre-existing different file is a conflict. Group/world-writable payload files (including identical unowned files) are refused during install and install dry-run. The installer does not change their permissions, contents or ownership; inspect the file and its provenance before resolving the conflict yourself. Uninstall still leaves unowned files untouched. A failed real install may leave the empty state directory used for locking, but does not install payloads or publish a new manifest on this preflight refusal. There is deliberately no automatic legacy adoption or force option: back up and review legacy files separately before moving them out of the way and installing again.
- An owned file that has been edited, replaced or chmodded causes the entire planned install/remove to refuse; unrelated files and KWin settings are left untouched. Missing owned files are forgotten on removal.
- Use the original XDG roots for uninstall/recovery. A changed config root with the same data root is rejected; a changed data root selects a different manifest and does not discover or remove the old installation. Empty directories and the empty manifest remain after removal. The retained state directory is also the lock anchor.

## Transaction lifecycle

A nonblocking advisory lock on the manifest directory serializes cooperating installers using the same data home. The manifest includes the transaction journal. Its replacement is atomic and fsynced.

1. Preflight validates the fixed paths, file identity and manifest. Publish a preparing journal.
2. Create private staging directories in the affected destination parents (same filesystem). Hardlink unchanged owned originals as backups and write/fsync complete new files. Record staged identities in the prepared journal before changing payload names.
3. Remove only validated old names and link the staged new files without clobbering an existing name. Sync directory changes. Publish the committed journal as the commit point.
4. Remove transaction staging entries and publish stable ownership. Before commit, a normal error triggers rollback; a subsequent real invocation rolls back a prepared transaction or cleans up a preparing, committed or rolled-back one before planning its requested operation.

A dry run does not create directories, files or locks on disk, change the manifest, or recover a pending transaction; it reports that recovery is required. To recover, rerun the installer with the original XDG roots, using the desired install or uninstall operation. Recovery refuses ambiguous changes, including unsafe group/world-writable files it validates, and retains the journal/staging for inspection instead of overwriting external edits. Do not manually delete the manifest or staging directories to force recovery; preserve them and investigate the conflict first.

## Boundaries

Directory-relative no-follow operations and ownership checks prevent ordinary ancestor/leaf symlink redirection. Advisory locking is only for cooperating installers. Concurrent hostile same-user edits/renames, malicious manifest fabrication, mount changes, inode reuse with identical bytes, changes limited to timestamps or extended attributes, nonlocal filesystems and hardware/filesystem failures are not fully protected. Recovery is not an atomic multi-file snapshot: readers can see intermediate states, including a brief missing file during replacement. A crash before a temporary manifest is renamed can leave an inert private .ownership-* file; empty directories may also remain. No directory tree is recursively removed. An interrupted operation with conflicting external changes may require manual recovery. Real power-loss durability and live compositor behavior have not been certified.
