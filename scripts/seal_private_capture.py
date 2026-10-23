#!/usr/bin/env python3
"""Local-only private Stage73 manifest; does NOT upload data or prove remote storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile

SCHEMA = "nexium-stage73-private-capture/v1"
MAX_FILES = 64
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 96 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
LOG_RE = re.compile(r"data-root/logs/nexium-[^/]+\.log\Z")


class ArchiveRejected(ValueError):
    pass


def _digest(value, pattern):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ArchiveRejected("invalid_identity")


def _relative(value):
    if not isinstance(value, str) or not value or len(value) > 512 or "\\" in value:
        return False
    p = PurePosixPath(value)
    return (not p.is_absolute() and str(p) == value and not value.startswith("-")
            and all(x not in ("", ".", "..") for x in value.split("/")))


def _hash_file(path):
    try:
        start = path.lstat()
        if not stat.S_ISREG(start.st_mode) or start.st_nlink != 1:
            raise ArchiveRejected("unsafe_file")
        if start.st_size > MAX_FILE_BYTES:
            raise ArchiveRejected("file_limit")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != start.st_ino
                    or opened.st_dev != start.st_dev):
                raise ArchiveRejected("unsafe_file")
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(fd, "rb", closefd=False) as stream:
                while chunk := stream.read(1048576):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ArchiveRejected("file_limit")
                    digest.update(chunk)
            after = os.fstat(fd)
            if (after.st_size != size or start.st_size != size
                    or after.st_mtime_ns != start.st_mtime_ns
                    or after.st_ctime_ns != start.st_ctime_ns):
                raise ArchiveRejected("changed_file")
            return {"bytes": size, "sha256": digest.hexdigest()}
        finally:
            os.close(fd)
    except OSError as error:
        raise ArchiveRejected("unreadable_file") from error


def scan(root):
    if root.is_symlink() or not root.is_dir():
        raise ArchiveRejected("unsafe_root")
    records, size = [], 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            directory = Path(parent) / name
            if directory.is_symlink() or not stat.S_ISDIR(directory.lstat().st_mode):
                raise ArchiveRejected("unsafe_directory")
        for name in files:
            path = Path(parent) / name
            rel = path.relative_to(root).as_posix()
            if not _relative(rel) or path.is_symlink():
                raise ArchiveRejected("unsafe_file")
            record = {"path": rel, **_hash_file(path)}
            records.append(record)
            size += record["bytes"]
            if len(records) > MAX_FILES or size > MAX_TOTAL_BYTES:
                raise ArchiveRejected("capture_limit")
    records.sort(key=lambda x: x["path"])
    paths = [x["path"] for x in records]
    if (len(set(paths)) != len(paths) or "smoke_result.json" not in paths
            or sum(bool(LOG_RE.fullmatch(x)) for x in paths) != 1):
        raise ArchiveRejected("missing_capture_evidence")
    return records


def build_manifest(root, source_commit, macho_sha256, nro_sha256):
    _digest(source_commit, COMMIT_RE)
    _digest(macho_sha256, SHA256_RE)
    _digest(nro_sha256, SHA256_RE)
    records = scan(root)
    return {"schema": SCHEMA, "source_commit": source_commit,
            "native_macho_sha256": macho_sha256, "guest_nro_sha256": nro_sha256,
            "privacy": "private", "files": records, "file_count": len(records),
            "total_bytes": sum(x["bytes"] for x in records),
            "remote_verified": False}


def write_manifest(path, manifest, root):
    if root.resolve() == path.resolve() or root.resolve() in path.resolve().parents:
        raise ArchiveRejected("manifest_inside_capture")
    if not path.parent.is_dir() or path.parent.is_symlink() or path.is_symlink():
        raise ArchiveRejected("unsafe_manifest_path")
    fd, temporary = tempfile.mkstemp(prefix=".stage73-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(manifest, out, sort_keys=True, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_manifest(root, path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 24576:
        raise ArchiveRejected("unsafe_manifest")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        raise ArchiveRejected("invalid_manifest") from error
    keys = {"schema", "source_commit", "native_macho_sha256", "guest_nro_sha256",
            "privacy", "files", "file_count", "total_bytes", "remote_verified"}
    if (not isinstance(data, dict) or set(data) != keys or data["schema"] != SCHEMA
            or data["privacy"] != "private" or data["remote_verified"] is not False):
        raise ArchiveRejected("invalid_schema")
    _digest(data["source_commit"], COMMIT_RE)
    _digest(data["native_macho_sha256"], SHA256_RE)
    _digest(data["guest_nro_sha256"], SHA256_RE)
    if not isinstance(data["files"], list) or len(data["files"]) > MAX_FILES:
        raise ArchiveRejected("invalid_schema")
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise ArchiveRejected("invalid_schema")
        if not _relative(item["path"]):
            raise ArchiveRejected("invalid_path")
        _digest(item["sha256"], SHA256_RE)
        if type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_FILE_BYTES:
            raise ArchiveRejected("invalid_size")
    files = scan(root)
    if (files != data["files"] or data["file_count"] != len(files) or
            data["total_bytes"] != sum(x["bytes"] for x in files)):
        raise ArchiveRejected("capture_mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only capture integrity")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("seal", "verify"):
        command = sub.add_parser(action)
        command.add_argument("--report", type=Path, required=True)
        command.add_argument("--manifest", type=Path, required=True)
        if action == "seal":
            command.add_argument("--source-commit", required=True)
            command.add_argument("--macho-sha256", required=True)
            command.add_argument("--nro-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "seal":
            manifest = build_manifest(args.report, args.source_commit,
                                      args.macho_sha256, args.nro_sha256)
            write_manifest(args.manifest, manifest, args.report)
        verify_manifest(args.report, args.manifest)
        print("STAGE73_PRIVATE_MANIFEST_" + (
            "SEALED_LOCAL_ONLY" if args.action == "seal" else "VERIFIED_LOCAL_ONLY"))
        return 0
    except (ArchiveRejected, OSError, ValueError, TypeError):
        print("STAGE73_PRIVATE_MANIFEST_REJECTED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
