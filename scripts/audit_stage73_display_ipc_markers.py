#!/usr/bin/env python3
"""Audit Stage73 classifier markers against the exact pinned public svc.rs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from apply_macos_display_ipc_trace import (
    EXPECTED_SOURCE_BLOB,
    PINNED_UPSTREAM_COMMIT,
    git_blob_sha,
)
from classify_guest_display_ipc_path import EVIDENCE

MAX_SOURCE_BYTES = 2 * 1024 * 1024

# Exact source templates from the pinned public kernel. These are audited
# before any diagnostic report is interpreted; no source lines are printed.
SOURCE_TEMPLATES = {
    "ipc_request": r'IPC request service=\"{}\" cmd={} in_data={} is_domain={}',
    "ipc_response": "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service={} cmd={} rc={:#010x} response_len={} response_first64={} in_data_first32={}",
    "vi_service_manager_handler": "SM::GetServiceHandle '{}' data_off={:#x}",
    "subsession_handle": "{} sub-session handle={:#x}",
    "igbp_connect": "IGBP::Connect binder={} api={} {}x{}",
    "igbp_request_buffer": "IGBP::RequestBuffer binder={} slot={}",
    "igbp_dequeue_retry": "IGBP::DequeueBuffer binder={}: request cannot be re-issued, polling in-SVC",
    "igbp_dequeue_timeout": "IGBP::DequeueBuffer timed out waiting for a released slot binder={} (free={} deq={} queued={})",
    "igbp_queue_buffer_info": "IGBP::QueueBuffer binder={} swap_interval={} (was {:?})",
    "nvdrv_open": "nvdrv:Open path='{}' (sb={:?})",
}

EXPECTED_LEVELS = {
    "ipc_request": "trace",
    "ipc_response": "debug",
    "vi_service_manager_handler": "debug",
    "subsession_handle": "debug",
    "igbp_connect": "debug",
    "igbp_request_buffer": "debug",
    "igbp_dequeue_retry": "debug",
    "igbp_dequeue_timeout": "error",
    "igbp_queue_buffer_info": "info",
    "nvdrv_open": "debug",
}

RENDERED_EVIDENCE = {
    "vi_u_service_handle_requested": "SM::GetServiceHandle 'vi:u'",
    "display_service_subsession_returned": "IApplicationDisplayService sub-session handle=",
    "binder_subsession_returned": "IHOSBinderDriver sub-session handle=",
    "igbp_connect_observed": "IGBP::Connect binder=",
    "igbp_request_buffer_observed": "IGBP::RequestBuffer binder=",
    "igbp_dequeue_retry_marker_observed": "request cannot be re-issued, polling in-SVC",
    "igbp_dequeue_timeout_marker_observed": "IGBP::DequeueBuffer timed out waiting for a released slot",
    "igbp_queue_buffer_observed": "IGBP::QueueBuffer",
    "nvdrv_open_observed": "nvdrv:Open path=",
}


def log_level_for(source: str, template: str) -> str | None:
    index = source.find(template)
    if index < 0:
        return None
    start = source.rfind("log::", 0, index)
    if start < 0:
        return None
    match = re.match(r'log::(trace|debug|info|warn|error)!\(\s*"', source[start:index])
    return match.group(1) if match else None


def audit_source(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("pinned source missing, linked or oversized")
    raw = path.read_bytes()
    if git_blob_sha(raw) != EXPECTED_SOURCE_BLOB:
        raise ValueError("pinned svc.rs Git blob differs")
    try:
        source = raw.decode("utf-8")
    except UnicodeError:
        raise ValueError("pinned svc.rs is not UTF-8") from None

    levels = {}
    for name, template in SOURCE_TEMPLATES.items():
        if source.count(template) != 1:
            raise ValueError("pinned source log template is missing or ambiguous")
        level = log_level_for(source, template)
        if level != EXPECTED_LEVELS[name]:
            raise ValueError("pinned source log level differs from classifier assumptions")
        levels[name] = level

    # Successful dequeue uses TRACE and therefore is not expected at DEBUG.
    # The classifier only treats the DEBUG retry or ERROR timeout as positive
    # evidence; absence of either is not interpreted as a missing dequeue.
    normal_dequeue_trace = re.search(
        r'log::trace!\(\s*"IGBP::DequeueBuffer binder=\{\}\s+.{1,3}\s+slot=\{\}',
        source,
    )
    if normal_dequeue_trace is None:
        raise ValueError("normal dequeue-success TRACE marker changed")

    for name, expected in RENDERED_EVIDENCE.items():
        if EVIDENCE.get(name) != expected:
            raise ValueError("classifier rendered marker does not match pinned source format")

    return {
        "schema": "nexium-stage73-source-marker-audit/v1",
        "pinned_upstream_commit": PINNED_UPSTREAM_COMMIT,
        "source_git_blob_sha1": EXPECTED_SOURCE_BLOB,
        "source_templates_verified": len(SOURCE_TEMPLATES),
        "source_log_levels_verified": True,
        "normal_dequeue_success_is_trace_only": True,
        "vi_u_handler_marker_matches_source": True,
        "raw_source_printed": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit_source(args.source)
        print(json.dumps(report, sort_keys=True))
        print("STAGE73_SOURCE_MARKER_AUDIT_PASS")
        return 0
    except (OSError, ValueError, UnicodeError, TypeError):
        print("STAGE73_SOURCE_MARKER_AUDIT_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
