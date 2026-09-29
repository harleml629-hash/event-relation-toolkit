"""Archive verification and isolated destination tests with artificial files."""

import copy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from tools import build_release as release
from tools import prepare_public_repo as preparation


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture_directory.cleanup)
        cls.archive = Path(cls.fixture_directory.name) / "reviewed.zip"
        release.build(release.ROOT, cls.archive)
        cls.digest = hashlib.sha256(cls.archive.read_bytes()).hexdigest()
        with zipfile.ZipFile(cls.archive) as archive:
            cls.members = [(copy.copy(info), archive.read(info)) for info in archive.infolist()]

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.private_root = self.base / "private_workspace"
        self.private_root.mkdir()
        self.destination = self.base / "public_copy"

    def modified_archive(self, transform):
        members = [(copy.copy(info), content) for info, content in self.members]
        members = transform(members)
        archive = self.base / "modified.zip"
        with warnings.catch_warnings(), zipfile.ZipFile(archive, "w") as output:
            warnings.simplefilter("ignore", UserWarning)
            for info, content in members:
                output.writestr(info, content)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def reject_modified(self, transform):
        archive, digest = self.modified_archive(transform)
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare(archive, self.destination, self.private_root, digest)
        self.assertFalse(self.destination.exists())

    def test_verified_archive_unpacks_exactly_without_git(self):
        count = preparation.prepare(self.archive, self.destination, self.private_root, self.digest)
        expected = preparation.checked_members(self.archive, self.digest)
        self.assertEqual(count, len(release.RELEASE_FILES) + 1)
        self.assertEqual(set(expected), set(release.RELEASE_FILES) | {"RELEASE_MANIFEST.json"})
        actual = {path.relative_to(self.destination).as_posix(): path.read_bytes()
                  for path in self.destination.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        self.assertFalse((self.destination / ".git").exists())

    def test_expected_archive_hash_is_required_and_validated(self):
        for digest in (None, "", "0" * 63, "g" * 64, "0" * 64):
            with self.subTest(digest_type=type(digest).__name__), self.assertRaises(preparation.PreparationError):
                preparation.prepare(self.archive, self.destination, self.private_root, digest)
            self.assertFalse(self.destination.exists())

    def test_existing_destination_is_preserved(self):
        self.destination.mkdir()
        marker = self.destination / "keep.txt"
        marker.write_text("generated keep marker", encoding="utf-8")
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, self.destination, self.private_root, self.digest)
        self.assertEqual(marker.read_text(encoding="utf-8"), "generated keep marker")
        self.assertEqual(list(self.destination.iterdir()), [marker])

    def test_private_workspace_destination_is_rejected(self):
        target = self.private_root / "public_copy"
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, target, self.private_root, self.digest)
        self.assertFalse(target.exists())

    def test_source_destination_is_rejected(self):
        source = self.base / "source"
        source.mkdir()
        target = source / "public_copy"
        with patch.object(preparation, "SOURCE_ROOT", source), self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, target, self.private_root, self.digest)
        self.assertFalse(target.exists())

    def test_destination_under_git_ancestor_is_rejected(self):
        parent = self.base / "existing_repository"
        parent.mkdir()
        (parent / ".git").mkdir()
        target = parent / "public_copy"
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, target, self.private_root, self.digest)
        self.assertFalse(target.exists())

    def test_destination_under_git_worktree_file_is_rejected(self):
        parent = self.base / "existing_worktree"
        parent.mkdir()
        (parent / ".git").write_text("generated marker", encoding="utf-8")
        target = parent / "public_copy"
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, target, self.private_root, self.digest)
        self.assertFalse(target.exists())

    def test_destination_parent_must_exist(self):
        target = self.base / "missing_parent" / "public_copy"
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, target, self.private_root, self.digest)
        self.assertFalse(target.parent.exists())

    def test_destination_reparse_component_is_rejected(self):
        parent = self.base / "generated_reparse_parent"
        parent.mkdir()
        target = parent / "public_copy"
        original = preparation.is_link
        with patch.object(preparation, "is_link", side_effect=lambda path: Path(path) == parent or original(path)), \
                self.assertRaises(preparation.PreparationError):
            preparation.prepare(self.archive, target, self.private_root, self.digest)
        self.assertFalse(target.exists())

    def test_archive_reparse_component_is_rejected(self):
        original = preparation.is_link
        with patch.object(preparation, "is_link", side_effect=lambda path: Path(path) == self.archive or original(path)), \
                self.assertRaises(preparation.PreparationError):
            preparation.checked_members(self.archive, self.digest)

    def test_archive_hash_detects_changed_bytes(self):
        changed = self.base / "changed.zip"
        changed.write_bytes(self.archive.read_bytes() + b"generated trailing canary")
        with self.assertRaises(preparation.PreparationError):
            preparation.checked_members(changed, self.digest)

    def test_member_tamper_is_detected_with_matching_archive_hash(self):
        def mutate(members):
            info, content = members[0]
            members[0] = info, content + b"generated change"
            return members
        self.reject_modified(mutate)

    def test_missing_member_is_rejected(self):
        self.reject_modified(lambda members: members[1:])

    def test_duplicate_member_is_rejected(self):
        self.reject_modified(lambda members: members + [members[0]])

    def test_manifest_hash_tamper_is_rejected(self):
        def mutate(members):
            result = []
            for info, content in members:
                if info.filename.endswith("/RELEASE_MANIFEST.json"):
                    manifest = json.loads(content)
                    manifest["files"][0]["sha256"] = "0" * 64
                    content = json.dumps(manifest).encode("utf-8")
                result.append((info, content))
            return result
        self.reject_modified(mutate)

    def test_duplicate_manifest_key_cannot_hide_discarded_content(self):
        def mutate(members):
            result = []
            for info, content in members:
                if info.filename.endswith("/RELEASE_MANIFEST.json"):
                    changed = b'{"scope":"generated_discarded_canary",' + content.lstrip()[1:]
                    self.assertEqual(json.loads(changed), json.loads(content))
                    content = changed
                result.append((info, content))
            return result
        self.reject_modified(mutate)

    def test_added_file_is_rejected_even_with_updated_manifest(self):
        def mutate(members):
            relative = "generated_extra.txt"
            data = b"generated canary"
            result = []
            for info, content in members:
                if info.filename.endswith("/RELEASE_MANIFEST.json"):
                    manifest = json.loads(content)
                    manifest["files"].append({"path": relative, "bytes": len(data),
                                              "sha256": hashlib.sha256(data).hexdigest()})
                    content = json.dumps(manifest).encode("utf-8")
                result.append((info, content))
            info = zipfile.ZipInfo(release.ARCHIVE_PREFIX + relative)
            info.external_attr = 0o100644 << 16
            result.append((info, data))
            return result
        self.reject_modified(mutate)

    def test_unsafe_and_windows_member_names_are_rejected(self):
        names = (
            "../escape.txt", "/absolute.txt", "event-relation-toolkit/../escape.txt",
            "event-relation-toolkit\\escape.txt", "event-relation-toolkit//extra.txt",
            "event-relation-toolkit/CON", "event-relation-toolkit/name:stream",
            "event-relation-toolkit/trailing. ", "event-relation-toolkit/./extra.txt",
            "R" + ":" + "/escape.txt",
        )
        for name in names:
            with self.subTest(name_index=names.index(name)):
                def mutate(members):
                    info, content = members[0]
                    info.filename = name
                    members[0] = info, content
                    return members
                self.reject_modified(mutate)

    def test_symlink_archive_member_is_rejected(self):
        def mutate(members):
            info, _ = members[0]
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            members[0] = info, b"generated_link_target"
            return members
        self.reject_modified(mutate)

    def test_directory_archive_member_is_rejected(self):
        def mutate(members):
            info = zipfile.ZipInfo(release.ARCHIVE_PREFIX + "extra/")
            members.append((info, b""))
            return members
        self.reject_modified(mutate)

    def test_entry_and_total_size_limits_are_enforced(self):
        for limit in ("MAX_FILE_BYTES", "MAX_TOTAL_BYTES"):
            with self.subTest(limit=limit), patch.object(preparation, limit, 1), self.assertRaises(preparation.PreparationError):
                preparation.prepare(self.archive, self.destination, self.private_root, self.digest)
            self.assertFalse(self.destination.exists())

    def test_declared_oversized_members_are_rejected_before_reading(self):
        for size in (preparation.MAX_FILE_BYTES + 1, preparation.MAX_TOTAL_BYTES + 1):
            infos = [copy.copy(info) for info, _ in self.members]
            infos[0].file_size = size
            with self.subTest(size=size), patch.object(preparation.zipfile, "ZipFile") as mock_zip:
                archive = mock_zip.return_value.__enter__.return_value
                archive.infolist.return_value = infos
                archive.comment = b""
                archive.read.side_effect = AssertionError("member data read before declared size check")
                with self.assertRaises(preparation.PreparationError):
                    preparation.checked_members(self.archive, self.digest)
                archive.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
