"""Release-boundary regression tests using generated canaries only."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools import build_release as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        for relative in release.RELEASE_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release.ROOT / relative, target)

    def build(self, name="release.zip"):
        output = self.base / name
        count = release.build(self.root, output)
        return output, count

    def reject(self):
        output = self.base / "rejected.zip"
        with self.assertRaises(release.ReleaseError) as caught:
            release.build(self.root, output)
        self.assertFalse(output.exists())
        return str(caught.exception)

    def test_reproducible_archive_and_fixed_metadata(self):
        first, count = self.build("first.zip")
        second, _ = self.build("second.zip")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(count, len(release.RELEASE_FILES) + 1)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.create_system, 3)
                self.assertEqual(info.external_attr >> 16, 0o100644)
                self.assertEqual(info.extra, b"")
                self.assertEqual(info.comment, b"")
            self.assertEqual(archive.comment, b"")

    def test_manifest_hashes_sizes_and_inventory(self):
        output, _ = self.build()
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read(release.ARCHIVE_PREFIX + "RELEASE_MANIFEST.json"))
            self.assertEqual({item["path"] for item in manifest["files"]}, set(release.RELEASE_FILES))
            self.assertEqual(len(manifest["files"]), len(release.RELEASE_FILES))
            for item in manifest["files"]:
                content = archive.read(release.ARCHIVE_PREFIX + item["path"])
                self.assertEqual(item["bytes"], len(content))
                self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())

    def test_extracted_release_rebuilds_identically(self):
        first, _ = self.build("first.zip")
        unpacked = self.base / "unpacked"
        with zipfile.ZipFile(first) as archive:
            # Only an archive constructed by this test is extracted here.
            archive.extractall(unpacked)
        second = self.base / "second.zip"
        release.build(unpacked / release.ARCHIVE_PREFIX.rstrip("/"), second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_unexpected_file_blocks_release_without_echoing_name(self):
        name = "generated_confidential_marker.txt"
        (self.root / name).write_text("generated canary", encoding="utf-8")
        self.assertNotIn(name, self.reject())

    def test_missing_allowlisted_file_blocks_release(self):
        (self.root / "README.md").unlink()
        self.reject()

    def test_empty_forbidden_directories_block_case_insensitively(self):
        for name in ("private_data", "PRIVATE_DATA", "local_runs", "Local_Runs"):
            with self.subTest(name=name):
                directory = self.root / name
                directory.mkdir()
                message = self.reject()
                self.assertNotIn(name, message)
                directory.rmdir()

    def test_forbidden_file_and_nested_ignored_directories_block(self):
        marker = self.root / "LOCAL_RUNS"
        marker.write_text("generated canary", encoding="utf-8")
        self.reject()
        marker.unlink()
        for ignored in sorted(release.IGNORED_DIRECTORIES):
            with self.subTest(ignored=ignored):
                nested = self.root / ignored / "nested" / "PrIvAtE_DaTa"
                nested.mkdir(parents=True)
                self.reject()
                nested.rmdir()

    def test_links_inside_ignored_directories_are_rejected(self):
        entry = self.root / "dist" / "generated_link"
        entry.parent.mkdir()
        entry.write_text("generated canary", encoding="utf-8")
        original = release.is_link
        with patch.object(release, "is_link", side_effect=lambda path: Path(path) == entry or original(path)):
            self.reject()

    def test_root_link_and_windows_reparse_attribute_are_rejected(self):
        original = release.is_link
        with patch.object(release, "is_link", side_effect=lambda path: Path(path) == self.root or original(path)):
            self.reject()
        regular_reparse = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=regular_reparse):
            self.assertTrue(release.is_link(self.root))

    def test_secret_canaries_are_rejected_without_logging_values(self):
        target = self.root / "README.md"
        original = target.read_text(encoding="utf-8")
        canaries = (
            "ghp_" + "q" * 32,
            "sample_person" + "@" + "example.invalid",
            "Q" + ":" + "/generated_private_location/entry",
            "-----BEGIN " + "PRIVATE KEY-----",
        )
        for canary in canaries:
            with self.subTest(kind=canaries.index(canary)):
                target.write_text(original + "\n" + canary, encoding="utf-8")
                self.assertNotIn(canary, self.reject())
        target.write_text(original, encoding="utf-8")

    def test_changed_synthetic_fixture_is_rejected(self):
        target = self.root / "examples/synthetic_events.json"
        content = json.loads(target.read_text(encoding="utf-8"))
        content["sessions"][0]["session_id"] = "generated_altered_session"
        target.write_text(json.dumps(content), encoding="utf-8")
        self.reject()

    def test_duplicate_fixture_key_cannot_hide_discarded_content(self):
        target = self.root / "examples/synthetic_events.json"
        original = target.read_text(encoding="utf-8")
        changed = '{"synthetic":"generated_discarded_canary",' + original.lstrip()[1:]
        self.assertEqual(json.loads(changed), json.loads(original))
        target.write_text(changed, encoding="utf-8")
        self.assertNotIn("generated_discarded_canary", self.reject())

    def test_changed_expected_summary_is_rejected(self):
        target = self.root / "examples/expected_summary.json"
        content = json.loads(target.read_text(encoding="utf-8"))
        content["sessions"][0]["interval_event_count"] += 1
        target.write_text(json.dumps(content), encoding="utf-8")
        self.reject()

    def test_binary_and_oversized_entries_are_rejected(self):
        target = self.root / "README.md"
        for content in (b"null\x00byte", b"\xff", b"x" * (release.MAX_FILE_BYTES + 1)):
            with self.subTest(length=len(content)):
                target.write_bytes(content)
                self.reject()

    def test_existing_output_is_never_overwritten(self):
        output = self.base / "release.zip"
        output.write_bytes(b"generated keep marker")
        with self.assertRaises(release.ReleaseError):
            release.build(self.root, output)
        self.assertEqual(output.read_bytes(), b"generated keep marker")

    def test_check_mode_creates_no_archive(self):
        before = set(self.base.iterdir())
        with patch.object(release, "ROOT", self.root), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(release.main(["--check"]), 0)
        self.assertEqual(set(self.base.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
