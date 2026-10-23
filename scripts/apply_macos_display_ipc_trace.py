#!/usr/bin/env python3
"""Apply a source-pinned, logging-only IPC session-correlation patch."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PINNED_UPSTREAM_COMMIT = "089562567a0a8760dfdd8420e1f57c35159a9219"
SOURCE_RELATIVE_PATH = "nexium-kernel/src/kernel/svc.rs"
EXPECTED_SOURCE_BLOB = "d3996cb1fb0871733c9d3adc9d106acdfd333273"

REQUEST_ANCHOR = (
    '    log::trace!(\n'
    '        "IPC request service=\\"{}\\" cmd={} in_data={} is_domain={}",\n'
    '        dispatch_target,\n'
    '        cmd_id,\n'
    '        ctx.cmif_in_data_len,\n'
    '        is_domain\n'
    '    );'
)
REQUEST_REPLACEMENT = (
    REQUEST_ANCHOR
    .replace("log::trace!(", "log::debug!(", 1)
    .replace("cmd={} in_data={}", "cmd={} session={:#x} in_data={}", 1)
    .replace("        cmd_id,\n", "        cmd_id,\n        session_handle,\n", 1)
)
ANCHOR = REQUEST_ANCHOR
REPLACEMENT = REQUEST_REPLACEMENT

SEEN_TYPE_ANCHOR = "static SEEN: OnceLock<Mutex<HashSet<(String, u32)>>> = OnceLock::new();"
SEEN_TYPE_REPLACEMENT = "static SEEN: OnceLock<Mutex<HashSet<(String, u32, u32)>>> = OnceLock::new();"
RESPONSE_KEY_ANCHOR = "let key = (dispatch_target.clone(), cmd_id);"
RESPONSE_KEY_REPLACEMENT = "let key = (dispatch_target.clone(), session_handle, cmd_id);"
RESPONSE_FORMAT_ANCHOR = (
    '                "IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
    'service={} cmd={} rc={:#010x} response_len={} response_first64={} in_data_first32={}",'
)
RESPONSE_FORMAT_REPLACEMENT = RESPONSE_FORMAT_ANCHOR.replace(
    "service={} cmd={}", "service={} cmd={} session={:#x}", 1
)
RESPONSE_ARGS_ANCHOR = (
    "                dispatch_target,\n"
    "                cmd_id,\n"
    "                reply_rc,"
)
RESPONSE_ARGS_REPLACEMENT = (
    "                dispatch_target,\n"
    "                cmd_id,\n"
    "                session_handle,\n"
    "                reply_rc,"
)
SUBSESSION_LOG_PATTERN = re.compile(
    r'        log::debug!\("[^"\n]* sub-session handle=\{:#x\}", sub_service, h\);'
)
BINDER_SIGNATURE_ANCHOR = (
    "fn handle_binder_transact(\n"
    "    kernel: &mut Kernel,\n"
    "    ctx: &mut ipc::IpcCtx,\n"
    "    _session_handle: u32,\n"
    ") -> Vec<u8> {"
)
BINDER_SIGNATURE_REPLACEMENT = BINDER_SIGNATURE_ANCHOR.replace(
    "_session_handle: u32", "session_handle: u32", 1
)
BINDER_ANCHOR = (
    "    log::trace!(\n"
    '        "IHOSBinderDriver.TransactParcel{} binder={} code={} in_size={} reply_size={}",\n'
    '        if cmd_id == 3 { "Auto" } else { "" },\n'
    "        binder_id,\n"
    "        code,\n"
    "        in_parcel.len(),\n"
    "        reply.len()\n"
    "    );"
)
BINDER_REPLACEMENT = (
    BINDER_ANCHOR
    .replace("log::trace!(", "log::debug!(", 1)
    .replace("binder={} code={} in_size=", "binder={} code={} session={:#x} in_size=", 1)
    .replace("        code,\n", "        code,\n        session_handle,\n", 1)
)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\x00" + data
    ).hexdigest()


def patch_scoped_ipc_request_log(
    source_root: Path,
    receipt_path: Path,
    *,
    expected_blob_sha: str = EXPECTED_SOURCE_BLOB,
) -> dict:
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

    exact_anchors = (
        (REQUEST_ANCHOR, REQUEST_REPLACEMENT),
        (SEEN_TYPE_ANCHOR, SEEN_TYPE_REPLACEMENT),
        (RESPONSE_KEY_ANCHOR, RESPONSE_KEY_REPLACEMENT),
        (RESPONSE_FORMAT_ANCHOR, RESPONSE_FORMAT_REPLACEMENT),
        (RESPONSE_ARGS_ANCHOR, RESPONSE_ARGS_REPLACEMENT),
        (BINDER_SIGNATURE_ANCHOR, BINDER_SIGNATURE_REPLACEMENT),
        (BINDER_ANCHOR, BINDER_REPLACEMENT),
    )
    for anchor, _replacement in exact_anchors:
        if text.count(anchor) != 1:
            raise ValueError("exact IPC session-correlation anchor must match once")

    subsession_matches = list(SUBSESSION_LOG_PATTERN.finditer(text))
    if len(subsession_matches) != 1:
        raise ValueError("sub-session return anchor must match exactly once")

    changed = text
    for anchor, replacement in exact_anchors:
        changed = changed.replace(anchor, replacement, 1)

    subsession_match = SUBSESSION_LOG_PATTERN.search(changed)
    if subsession_match is None:
        raise ValueError("sub-session return anchor disappeared")
    subsession_line = subsession_match.group(0)
    new_subsession_line = (
        subsession_line
        .replace(
            " sub-session handle={:#x}",
            " sub-session handle={:#x} parent_session={:#x}",
            1,
        )
        .replace(", sub_service, h);", ", sub_service, h, session_handle);", 1)
    )
    if new_subsession_line == subsession_line or "parent_session={:#x}" not in new_subsession_line:
        raise ValueError("sub-session parent correlation patch did not apply")
    changed = changed[:subsession_match.start()] + new_subsession_line + changed[subsession_match.end():]

    required_after = (
        REQUEST_REPLACEMENT,
        SEEN_TYPE_REPLACEMENT,
        RESPONSE_KEY_REPLACEMENT,
        RESPONSE_FORMAT_REPLACEMENT,
        RESPONSE_ARGS_REPLACEMENT,
        "sub-session handle={:#x} parent_session={:#x}",
        BINDER_SIGNATURE_REPLACEMENT,
        BINDER_REPLACEMENT,
    )
    if any(changed.count(marker) != 1 for marker in required_after):
        raise ValueError("patched session-correlation source failed exact post-check")

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.is_symlink():
        raise ValueError("patch receipt path is linked")
    try:
        resolved_source = source_root.resolve(strict=True)
        resolved_receipt_parent = receipt_path.parent.resolve(strict=True)
    except OSError:
        raise ValueError("patch receipt parent cannot be resolved") from None
    if resolved_source == resolved_receipt_parent or resolved_source in resolved_receipt_parent.parents:
        raise ValueError("patch receipt must be outside the upstream source tree")

    encoded = changed.encode("utf-8")
    source.write_bytes(encoded)
    patched_sha = git_blob_sha(encoded)
    result = {
        "schema": "nexium-stage73-scoped-ipc-session-correlation-patch/v2",
        "upstream_commit": PINNED_UPSTREAM_COMMIT,
        "source_relative_path": SOURCE_RELATIVE_PATH,
        "original_git_blob_sha1": original_sha,
        "patched_git_blob_sha1": patched_sha,
        "exact_log_anchor_matches": 4,
        "exact_source_transform_count": len(exact_anchors) + 1,
        "trace_to_debug_replacements": 2,
        "session_correlation_fields_added": True,
        "response_deduplication_scope": "service_session_command",
        "only_diagnostic_logging_changed": True,
        "guest_or_service_behavior_changed": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }
    receipt_path.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
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
        print("STAGE73_SCOPED_IPC_SESSION_CORRELATION_PATCH_PASS")
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        print("STAGE73_SCOPED_IPC_SESSION_CORRELATION_PATCH_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
