"""Release metadata, committed-source packaging and archive safety checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from tools import build_release as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.files = {path: (release.ROOT / path).read_bytes() for path in release.FILES}

    def test_version_consistency(self):
        version = release.version_of(self.files)
        for path, value in (
            ("VERSION", b"../escape\n"),
            ("VERSION", b"0.1.0-alpha.01\n"),
            ("kwin-script/metadata.json", json.dumps({"KPlugin": {"Version": "9.9.9"}}).encode()),
            ("CHANGELOG.md", b"# Changelog\n\n## 9.9.9\n"),
        ):
            with self.subTest(path=path, value=value):
                with self.assertRaises(ValueError):
                    release.version_of(dict(self.files, **{path: value}))
        self.assertTrue(version)

    def test_reproducible_archive_and_source_identity(self):
        commit = "a" * 40
        prefix, data, contents = release.archive_bytes(commit, self.files)
        other_prefix, other_data, _ = release.archive_bytes(commit, dict(reversed(list(self.files.items()))))
        self.assertEqual((prefix, data), (other_prefix, other_data))
        self.assertEqual(contents["SOURCE_COMMIT"], (commit + "\n").encode())
        self.assertEqual(set(contents), set(release.FILES) | {"SOURCE_COMMIT"})
        release.verify_archive(data, prefix, contents)
        with self.assertRaises(ValueError):
            release.verify_archive(data, prefix, dict(contents, VERSION=b"wrong\n"))
        with self.assertRaises(ValueError):
            release.archive_bytes("not-a-commit", self.files)
        with self.assertRaises(ValueError):
            release.archive_bytes(commit, dict(self.files, extra=b"unexpected"))

    def test_archive_member_validation(self):
        for name, kind in (("../escape", tarfile.REGTYPE),
                           ("project/file", tarfile.SYMTYPE),
                           ("project/file", tarfile.LNKTYPE),
                           ("project/file", tarfile.DIRTYPE)):
            with self.subTest(name=name, kind=kind):
                output = io.BytesIO()
                with tarfile.open(fileobj=output, mode="w:gz") as tar:
                    info = tarfile.TarInfo(name)
                    info.mode = 0o644
                    info.type = kind
                    tar.addfile(info)
                with self.assertRaises(ValueError):
                    release.verify_archive(output.getvalue(), "project", {"file": b""})

    def test_duplicate_or_missing_archive_members(self):
        for count in (0, 2):
            with self.subTest(count=count):
                output = io.BytesIO()
                with tarfile.open(fileobj=output, mode="w:gz") as tar:
                    for _ in range(count):
                        info = tarfile.TarInfo("project/file")
                        info.mode = 0o644
                        tar.addfile(info)
                with self.assertRaises(ValueError):
                    release.verify_archive(output.getvalue(), "project", {"file": b""})

    def test_committed_sources_only_and_refusal(self):
        # Create a disposable local repository; no remotes, hooks or credentials.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            repo.mkdir()
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(repo), "-c", "user.name=Fixture",
                     "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null",
                     *args], env=env, stderr=subprocess.DEVNULL, timeout=15)

            git("init", "--initial-branch=main", "--template=")
            for path, value in self.files.items():
                dest = repo / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(value)
            (repo / ".env").write_text("synthetic tracked secret")
            git("add", ".")
            git("commit", "-m", "fixture")
            commit = git("rev-parse", "HEAD").decode().strip()
            (repo / "README.md").write_text("uncommitted change")
            (repo / "local-secret.txt").write_text("synthetic untracked secret")

            archive = release.build(repo, commit, base / "first")
            again = release.build(repo, commit, base / "second")
            self.assertEqual(archive.read_bytes(), again.read_bytes())
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual((archive.parent / "SHA256SUMS").read_text(),
                             digest + "  " + archive.name + "\n")
            prefix = archive.name.removesuffix(".tar.gz")
            with tarfile.open(archive, "r:gz") as tar:
                self.assertEqual(set(tar.getnames()),
                                 {prefix + "/" + p for p in release.FILES + ("SOURCE_COMMIT",)})
                self.assertEqual(tar.extractfile(prefix + "/README.md").read(), self.files["README.md"])
                self.assertEqual(tar.extractfile(prefix + "/SOURCE_COMMIT").read(),
                                 (commit + "\n").encode())
            with self.assertRaises(FileExistsError):
                release.build(repo, commit, archive.parent)
            self.assertEqual(archive.read_bytes(), again.read_bytes())
            # A committed unexpected source path cannot be silently omitted.
            (repo / "docs" / "unexpected.md").write_text("fixture")
            git("add", "docs/unexpected.md")
            git("commit", "-m", "unexpected")
            with self.assertRaisesRegex(ValueError, "Unreviewed distribution paths"):
                release.build(repo, "HEAD", base / "unexpected")
            self.assertFalse((base / "unexpected").exists())
            git("rm", "docs/unexpected.md")
            git("rm", "helper/inhibitor.py")
            git("commit", "-m", "missing")
            with self.assertRaisesRegex(ValueError, "Missing distribution path"):
                release.build(repo, "HEAD", base / "missing")
            self.assertFalse((base / "missing").exists())
            (repo / "helper").mkdir(exist_ok=True)
            (repo / "helper/inhibitor.py").symlink_to("../README.md")
            git("add", "helper/inhibitor.py")
            git("commit", "-m", "symlink")
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                release.build(repo, "HEAD", base / "symlink")
            self.assertFalse((base / "symlink").exists())
