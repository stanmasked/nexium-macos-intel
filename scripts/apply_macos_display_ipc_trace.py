#!/usr/bin/env python3
"""Apply a one-call, source-pinned IPC log-level change for disposable diagnosis.

Only the generic SendSyncRequest IPC request log changes from TRACE to DEBUG.
This avoids globally enabling per-SVC trace logging during the guest smoke run.
No emulator behavior or response payload is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PINNED_UPSTREAM_COMMIT = "089562567a0a8760dfdd8420e1f57c35159a9219"
SOURCE_RELATIVE_PATH = "nexium-kernel/src/kernel/svc.rs"
EXPECTED_SOURCE_BLOB = "d3996cb1fb0871733c9d3adc9d106acdfd333273"
ANCHOR = ('    log::trace!(\n'
          '        "IPC request service=\\"{}\\" cmd={} in_data={} is_domain={}",')
REPLACEMENT = ANCHOR.replace("log::trace!(", "log::debug!(", 1)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii")
                        + b"\\x00" + data).hexdigest()


def patch_scoped_ipc_request_log(source_root: Path, receipt_path: Path,
                                 *, expected_blob_sha: str = EXPECTED_SOURCE_BLOB) -> dict:
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("upstream source root is missing or linked")
    source = source_root / SOURCE_RELATIVE_PATH
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("pinned svc.rs is missing, linked or oversized")
    raw = source.read_bytes()
    original_sha = git_blob_sha(raw)
    if original_sha != expected_blob_sha:
        raise ValueError("pinned svc.rs Git blob differs")
    text = raw.decode("utf-8")
    if text.count(ANCHOR) != 1:
        raise ValueError("generic IPC request log anchor must match exactly once")
    changed = text.replace(ANCHOR, REPLACEMENT, 1)
    if changed == text or changed.count(REPLACEMENT) != 1:
        raise ValueError("scoped IPC debug patch did not apply uniquely")
    encoded = changed.encode("utf-8")
    source.write_bytes(encoded)
    patched_sha = git_blob_sha(encoded)
    result = {
        "schema": "nexium-stage73-scoped-ipc-log-patch/v1",
        "upstream_commit": PINNED_UPSTREAM_COMMIT,
        "source_relative_path": SOURCE_RELATIVE_PATH,
        "original_git_blob_sha1": original_sha,
        "patched_git_blob_sha1": patched_sha,
        "exact_log_anchor_matches": 1,
        "trace_to_debug_replacements": 1,
        "only_ipc_request_log_level_changed": True,
        "guest_or_service_behavior_changed": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\\n",
                            encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rev = subprocess.run(
            ["git", "-C", str(args.source_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if rev.returncode != 0 or rev.stdout.strip() != PINNED_UPSTREAM_COMMIT:
            raise ValueError("upstream checkout is not at exact pinned commit")
        result = patch_scoped_ipc_request_log(args.source_root, args.receipt)
        print(json.dumps(result, sort_keys=True))
        print("STAGE73_SCOPED_IPC_REQUEST_DEBUG_PATCH_PASS")
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        print("STAGE73_SCOPED_IPC_REQUEST_DEBUG_PATCH_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
