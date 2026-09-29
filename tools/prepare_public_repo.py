"""Verify a reviewed archive and prepare a separate directory; never initialize Git."""

import argparse
import hashlib
from pathlib import Path
import re
import stat
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_release import ARCHIVE_PREFIX, RELEASE_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, ReleaseError, is_link, scan_text, strict_json, manifest_bytes

SOURCE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "RELEASE_MANIFEST.json"


class PreparationError(ValueError):
    pass


def is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def checked_path(value):
    path = Path(value).absolute()
    if ".." in path.parts:
        raise PreparationError("Use a direct path without parent traversal")
    # Check before resolve so a link or Windows junction is not silently followed.
    for part in (*reversed(path.parents), path):
        if (part.exists() or part.is_symlink()) and is_link(part):
            raise PreparationError("Path components cannot be links or reparse points")
    return path.resolve()


def checked_members(archive_path, sha256):
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise PreparationError("A reviewed archive SHA-256 is required")
    archive_path = checked_path(archive_path)
    if not archive_path.is_file() or archive_path.stat().st_size > MAX_TOTAL_BYTES * 2:
        raise PreparationError("Archive is missing, nonregular, or too large")
    # Open once: verify and parse the same file descriptor.
    with archive_path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
        if digest.hexdigest() != sha256.lower():
            raise PreparationError("Archive SHA-256 does not match the reviewed value")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            required_names = {ARCHIVE_PREFIX + name for name in RELEASE_FILES}
            manifest_path = ARCHIVE_PREFIX + MANIFEST_NAME
            required_names.add(manifest_path)
            if len(names) != len(set(names)) or set(names) != required_names:
                raise PreparationError("Archive inventory differs from the reviewed allowlist")
            if archive.comment:
                raise PreparationError("Archive comments are not allowed")
            if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
                raise PreparationError("Archive exceeds the reviewed size limit")
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if (info.is_dir() or info.flag_bits & 0x1 or
                        info.file_size > MAX_FILE_BYTES or
                        info.compress_type != zipfile.ZIP_STORED or
                        mode != stat.S_IFREG or info.extra or info.comment or
                        info.date_time != (1980, 1, 1, 0, 0, 0)):
                    raise PreparationError("Archive member type, size, or metadata is unexpected")
            try:
                manifest_content = archive.read(manifest_path)
                manifest = strict_json(manifest_content.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise PreparationError("Archive manifest is invalid") from exc
            if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "scope", "files"}:
                raise PreparationError("Archive manifest has an unexpected structure")
            if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or
                    manifest["scope"] != "text-only independent synthetic demonstration" or
                    not isinstance(manifest["files"], list)):
                raise PreparationError("Archive manifest version, scope, or file list is invalid")

            contents = {}
            for record in manifest["files"]:
                if not isinstance(record, dict) or set(record) != {"path", "bytes", "sha256"}:
                    raise PreparationError("Archive manifest contains an invalid file record")
                relative = record["path"]
                if not isinstance(relative, str) or relative not in RELEASE_FILES or relative in contents:
                    raise PreparationError("Archive manifest contains an unexpected or duplicate path")
                if type(record["bytes"]) is not int or not 0 <= record["bytes"] <= MAX_FILE_BYTES:
                    raise PreparationError("Archive manifest contains an invalid byte count")
                data = archive.read(ARCHIVE_PREFIX + relative)
                if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                    raise PreparationError("Archive content does not match its manifest")
                if scan_text(data) != data:
                    raise PreparationError("Archive text is not in canonical form")
                if relative.endswith(".json"):
                    try:
                        strict_json(data)
                    except (UnicodeError, ValueError) as exc:
                        raise PreparationError("Archive JSON contains invalid or duplicate fields") from exc
                contents[relative] = data
            if set(contents) != set(RELEASE_FILES):
                raise PreparationError("Archive manifest does not cover the reviewed allowlist")
            if manifest_content != manifest_bytes(contents):
                raise PreparationError("Archive manifest is not in canonical form")
            contents[MANIFEST_NAME] = manifest_content
            return contents


def prepare(archive_path, destination, private_root, sha256):
    private_root = checked_path(private_root)
    destination = checked_path(destination)
    if not private_root.is_dir():
        raise PreparationError("The private project root must be an existing directory")
    if destination.exists() or destination.is_symlink():
        raise PreparationError("Destination must not exist; choose a new empty location")
    if not destination.parent.is_dir():
        raise PreparationError("Destination parent directory must already exist")
    for excluded in (private_root, SOURCE_ROOT.resolve()):
        if is_within(destination, excluded) or is_within(excluded, destination):
            raise PreparationError("Destination must be outside the private project and source trees")
    for ancestor in destination.parents:
        marker = ancestor / ".git"
        if marker.exists() or marker.is_symlink():
            raise PreparationError("Destination cannot inherit a parent Git repository")

    contents = checked_members(archive_path, sha256)
    # No archive code is imported or executed, and only allowlisted paths are written.
    destination.mkdir()
    for relative, data in sorted(contents.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return len(contents)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        count = prepare(args.archive, args.destination, args.private_root, args.sha256)
        print(f"Prepared a verified public directory with {count} files.")
        print("Review the new directory before initializing a fresh Git repository.")
        return 0
    except (PreparationError, ReleaseError, OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile):
        print("Preparation failed; check the reviewed hash, archive, and separate destination. Any partial directory must not be published.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
