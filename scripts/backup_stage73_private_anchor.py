#!/usr/bin/env python3
"""Private, two-location Stage73 anchor recovery protocol.

Local/offline synthetic proof only. Never run the CLI in PR Actions.
Separate directories do NOT by themselves establish independent retention.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from verify_stage73_private_drive_persistence import read_independent_anchor
from archive_private_capture_drive import DriveArchiveRejected, COMMIT, RUN_ID, DRIVE_ID

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ANCHOR_MAX = 4096
REFERENCE_MAX = 2048
REFERENCE_SCHEMA = "nexium-stage73-offline-anchor-reference/v1"


def _private_bytes(path, max_bytes):
    """Read a regular, single-linked 0600 file with a stable descriptor."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or not 0 < before.st_size <= max_bytes):
                raise DriveArchiveRejected("unsafe_private_file")
            data = bytearray()
            while len(data) <= max_bytes:
                fragment = os.read(fd, max_bytes + 1 - len(data))
                if not fragment:
                    break
                data.extend(fragment)
            after = os.fstat(fd)
            if (len(data) != before.st_size
                    or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_ctime_ns != after.st_ctime_ns):
                raise DriveArchiveRejected("private_file_mutated")
            return bytes(data)
        finally:
            os.close(fd)
    except OSError as error:
        raise DriveArchiveRejected("private_file_unavailable") from error


def _identities(commit, run_id, capture_parent, receipt_parent):
    if (not isinstance(commit, str) or not COMMIT.fullmatch(commit)
            or not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id)
            or not isinstance(capture_parent, str)
            or not DRIVE_ID.fullmatch(capture_parent)
            or not isinstance(receipt_parent, str)
            or not DRIVE_ID.fullmatch(receipt_parent)
            or capture_parent == receipt_parent):
        raise DriveArchiveRejected("invalid_backup_identity")


def _separate_paths(original, backup, reference, disposable_root=None):
    paths = [Path(value) for value in (original, backup, reference)]
    canonical = [path.resolve() for path in paths]
    if (len(set(canonical)) != 3
            or len({str(item.parent) for item in canonical}) != 3):
        raise DriveArchiveRejected("not_independent_destinations")
    for path in paths:
        if (path.parent.is_symlink() or not path.parent.is_dir()
                or path.name in ("", ".", "..") or path.is_symlink()):
            raise DriveArchiveRejected("unsafe_private_parent")
    if disposable_root is not None:
        disposable = Path(disposable_root).resolve()
        # The input anchor may come from the short-lived producer session.
        # Only the backup and digest-reference destinations MUST survive
        # deletion of that producer workspace.
        if any(path == disposable or disposable in path.parents
               for path in canonical[1:]):
            raise DriveArchiveRejected("backup_inside_disposable_workspace")
    return paths


def _exclusive_0600(path, raw):
    parent = path.parent
    dirflags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory = os.open(parent, dirflags)
        try:
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=directory)
            try:
                os.fchmod(fd, 0o600)
                view = memoryview(raw)
                while view:
                    n = os.write(fd, view)
                    if n <= 0:
                        raise DriveArchiveRejected("backup_write_incomplete")
                    view = view[n:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as error:
        raise DriveArchiveRejected("backup_collision") from error
    except OSError as error:
        raise DriveArchiveRejected("backup_write_failed") from error
    if hashlib.sha256(_private_bytes(path, max(REFERENCE_MAX, ANCHOR_MAX))).digest() != hashlib.sha256(raw).digest():
        raise DriveArchiveRejected("backup_readback_failed")


def backup_offline_anchor(source, backup, reference, *,
                          source_commit, run_id, capture_parent,
                          receipt_parent, disposable_root):
    """Write two private non-overwriting copies in DIFFERENT local directories."""
    _identities(source_commit, run_id, capture_parent, receipt_parent)
    src, dst, ref = _separate_paths(
        source, backup, reference, disposable_root)
    if dst.exists() or ref.exists():
        raise DriveArchiveRejected("backup_collision")
    expected_receipt_sha = read_independent_anchor(
        src, source_commit, run_id, capture_parent, receipt_parent)
    raw = _private_bytes(src, ANCHOR_MAX)
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise DriveArchiveRejected("invalid_local_anchor") from error
    if (record.get("receipt_sha256") != expected_receipt_sha
            or record.get("source_commit") != source_commit
            or record.get("run_id") != run_id
            or record.get("capture_parent_id") != capture_parent
            or record.get("receipt_parent_id") != receipt_parent):
        raise DriveArchiveRejected("local_anchor_changed")
    digest = hashlib.sha256(raw).hexdigest()
    ref_obj = {
        "schema": REFERENCE_SCHEMA, "privacy": "private",
        "source_commit": source_commit, "run_id": run_id,
        "capture_parent_id": capture_parent, "receipt_parent_id": receipt_parent,
        "anchor_sha256": digest, "retention_verified": False,
        "guest_gpu_frames_verified": False,
    }
    reference_raw = (json.dumps(ref_obj, sort_keys=True, separators=(",", ":")) + "\n").encode()
    # A second location is a recovery aid; do not claim this is an offsite copy.
    _exclusive_0600(dst, raw)
    _exclusive_0600(ref, reference_raw)
    restored = verify_offline_anchor(
        dst, ref, source_commit=source_commit, run_id=run_id,
        capture_parent=capture_parent, receipt_parent=receipt_parent)
    if not restored["independent_copy_readback_verified"]:
        raise DriveArchiveRejected("backup_incomplete")
    return {"independent_copy_readback_verified": True,
            "remote_retention_verified": False}


def verify_offline_anchor(backup, reference, *,
                          source_commit, run_id, capture_parent,
                          receipt_parent):
    """Recover after the source tree has gone; uses a SEPARATE reference file."""
    _identities(source_commit, run_id, capture_parent, receipt_parent)
    dst, ref = Path(backup), Path(reference)
    if (dst.resolve() == ref.resolve()
            or dst.resolve().parent == ref.resolve().parent):
        raise DriveArchiveRejected("not_independent_destinations")
    raw = _private_bytes(dst, ANCHOR_MAX)
    encoded = _private_bytes(ref, REFERENCE_MAX)
    try:
        record = json.loads(encoded)
    except (UnicodeError, ValueError) as error:
        raise DriveArchiveRejected("invalid_backup_reference") from error
    fields = {"schema", "privacy", "source_commit", "run_id",
              "capture_parent_id", "receipt_parent_id", "anchor_sha256",
              "retention_verified", "guest_gpu_frames_verified"}
    if (not isinstance(record, dict) or set(record) != fields
            or record.get("schema") != REFERENCE_SCHEMA
            or record.get("privacy") != "private"
            or record.get("source_commit") != source_commit
            or record.get("run_id") != run_id
            or record.get("capture_parent_id") != capture_parent
            or record.get("receipt_parent_id") != receipt_parent
            or record.get("retention_verified") is not False
            or record.get("guest_gpu_frames_verified") is not False
            or not isinstance(record.get("anchor_sha256"), str)
            or not SHA256.fullmatch(record["anchor_sha256"])
            or record["anchor_sha256"] != hashlib.sha256(raw).hexdigest()):
        raise DriveArchiveRejected("private_anchor_recovery_mismatch")
    receipt_sha = read_independent_anchor(
        dst, source_commit, run_id, capture_parent, receipt_parent)
    if not SHA256.fullmatch(receipt_sha):
        raise DriveArchiveRejected("invalid_receipt_sha")
    return {"independent_copy_readback_verified": True,
            "remote_retention_verified": False,
            "guest_gpu_frames_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage73 offline private anchor recovery")
    parser.add_argument("action", choices=("backup", "verify"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--disposable-root", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--capture-parent", required=True)
    parser.add_argument("--receipt-parent", required=True)
    args = parser.parse_args(argv)
    try:
        if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
            raise DriveArchiveRejected("github_runner_forbidden")
        common = {
            "source_commit": args.source_commit, "run_id": args.run_id,
            "capture_parent": args.capture_parent,
            "receipt_parent": args.receipt_parent,
        }
        if args.action == "backup":
            if args.source is None or args.disposable_root is None:
                raise DriveArchiveRejected("missing_private_source")
            outcome = backup_offline_anchor(args.source, args.backup, args.reference,
                                            disposable_root=args.disposable_root, **common)
        else:
            if args.source is not None or args.disposable_root is not None:
                raise DriveArchiveRejected("unsafe_verify_args")
            outcome = verify_offline_anchor(args.backup, args.reference, **common)
        if outcome["remote_retention_verified"] is not False:
            raise DriveArchiveRejected("retention_not_proven")
        print("STAGE73_PRIVATE_ANCHOR_" +
              ("LOCAL_BACKUP_VERIFIED_RETENTION_UNVERIFIED" if args.action == "backup"
               else "LOCAL_RECOVERY_VERIFIED_RETENTION_UNVERIFIED"))
        return 0
    except (DriveArchiveRejected, OSError, ValueError, TypeError, KeyError):
        print("STAGE73_PRIVATE_ANCHOR_NOT_VERIFIED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
