"""Build a deterministic text-only ZIP from a reviewed file allowlist."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PREFIX = "event-relation-toolkit/"
RELEASE_FILES = (
    ".gitattributes", ".gitignore", ".python-version", "LICENSE_NOTICE.md",
    "README.md", "README.zh-CN.md", "CONTRIBUTING.md",
    ".github/PULL_REQUEST_TEMPLATE.md", "pyproject.toml", "settings.demo.json",
    "event_relations/__init__.py", "event_relations/__main__.py",
    "event_relations/analysis.py", "event_relations/cli.py",
    "event_relations/demo.py", "event_relations/model.py",
    "docs/METHODS.md", "docs/PRIVACY.md", "docs/PUBLISHING.md",
    "examples/synthetic_events.json", "examples/expected_summary.json",
    "tests/test_analysis.py", "tests/test_validation.py", "tests/test_release.py",
    "tests/test_prepare.py", "tools/build_release.py", "tools/prepare_public_repo.py",
)
FORBIDDEN_NAMES = {"private_data", "local_runs"}
IGNORED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", "build", "dist"}
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
PATTERNS = {
    "machine-specific drive path": re.compile(r"\b[A-Za-z]:[\\/][A-Za-z0-9_]"),
    "personal Unix path": re.compile(r"/(?:Users|home|mnt|media)/[A-Za-z0-9_]"),
    "UNC path": re.compile(r"\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_]"),
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "credential-like token": re.compile(r"(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}"),
    "private key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


class ReleaseError(ValueError):
    pass


def strict_json(content):
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ReleaseError("JSON contains duplicate object keys")
            value[key] = item
        return value

    def invalid_number(_):
        raise ReleaseError("JSON contains a nonfinite number")

    return json.loads(content, object_pairs_hook=unique_object, parse_constant=invalid_number)


def manifest_bytes(contents):
    manifest = {
        "schema_version": 1,
        "scope": "text-only independent synthetic demonstration",
        "files": [{"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                  for name, content in sorted(contents.items())],
    }
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def scan_text(content):
    if len(content) > MAX_FILE_BYTES:
        raise ReleaseError("A release entry exceeds the text-only size limit")
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ReleaseError("Release entries must be UTF-8 text") from exc
    if "\x00" in text:
        raise ReleaseError("Release entry contains a null byte")
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            raise ReleaseError(f"Content scan found a possible {label}; no matched value was logged")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def check_file(root, relative):
    path = root / relative
    for item in (path, *list(path.parents)[:len(Path(relative).parts) - 1]):
        if is_link(item):
            raise ReleaseError("A release entry or its parent is a link/reparse point")
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ReleaseError("A release entry is missing, not a regular file, or too large")
    return scan_text(path.read_bytes())


def inventory(root):
    found = set()

    def visit(directory, excluded=False):
        for path in directory.iterdir():
            # Check even empty directories and names under excluded trees. Never
            # read private file contents or echo their names into a build log.
            if path.name.casefold() in FORBIDDEN_NAMES:
                raise ReleaseError("A forbidden local-data entry exists; release stopped before packaging")
            if is_link(path):
                raise ReleaseError("Unexpected link/reparse point in release tree")
            if path.is_dir():
                visit(path, excluded or path.name.casefold() in IGNORED_DIRECTORIES)
            elif path.is_file():
                if not excluded:
                    found.add(path.relative_to(root).as_posix())
            else:
                raise ReleaseError("Unexpected nonregular entry in release tree")

    visit(root)
    if found - {"RELEASE_MANIFEST.json"} != set(RELEASE_FILES):
        raise ReleaseError("File inventory differs from the reviewed allowlist; review additions and missing files")


def collect(root):
    root = Path(root)
    if is_link(root):
        raise ReleaseError("Release root cannot be a link/reparse point")
    inventory(root)
    contents = {name: check_file(root, name) for name in sorted(RELEASE_FILES)}
    if sum(map(len, contents.values())) > MAX_TOTAL_BYTES:
        raise ReleaseError("Release exceeds the total text-only size limit")
    sys.path.insert(0, str(ROOT))
    from event_relations.analysis import analyze
    from event_relations.demo import generate_demo
    from event_relations.model import Policy, parse_dataset
    example = strict_json(contents["examples/synthetic_events.json"])
    if example != generate_demo():
        raise ReleaseError("Example is not the exact procedural synthetic fixture")
    policy = Policy.parse(strict_json(contents["settings.demo.json"]))
    if strict_json(contents["examples/expected_summary.json"]) != analyze(parse_dataset(example), policy):
        raise ReleaseError("Expected summary does not match the procedural fixture")
    return contents


def build(root, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ReleaseError("Output exists; choose a new archive filename")
    contents = collect(root)
    contents["RELEASE_MANIFEST.json"] = manifest_bytes(contents)
    if sum(map(len, contents.values())) > MAX_TOTAL_BYTES:
        raise ReleaseError("Release including its manifest exceeds the total text-only size limit")
    with output.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in sorted(contents.items()):
                entry = zipfile.ZipInfo(ARCHIVE_PREFIX + name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, content)
    return len(contents)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            print(f"Release check passed for {len(collect(ROOT))} allowlisted text files.")
        else:
            print(f"Created text-only release with {build(ROOT, args.output)} entries, including its hash manifest.")
        return 0
    except (ReleaseError, OSError, ValueError, RecursionError) as exc:
        print(str(exc) if isinstance(exc, ReleaseError) else "Release failed; check the local files and output permissions.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
