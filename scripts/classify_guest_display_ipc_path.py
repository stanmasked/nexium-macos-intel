#!/usr/bin/env python3
"""Stage73: source-anchored fixed-category original guest display IPC diagnosis.

The trace log remains private on the disposable native Intel runner. This
module emits only booleans and one allowlisted stage category; it never emits
raw service names from a log, command numbers, paths, IPC bytes or screenshots.
A reached IPC operation is not evidence of correct display or GPU rendering.
"""
from __future__ import annotations

import json
from pathlib import Path

from observe_intel_integrated_window import read_bounded_json

MAX_LOG_BYTES = 16 * 1024 * 1024
ALLOWED_STATUSES = frozenset({
    "exited_zero_unverified", "exited_nonzero",
    "timeout_alive_unverified", "launch_failed",
})

# These are literal, allowlisted signatures from the pinned public NeXium
# service-manager/IPC/IGBP source paths. Never print matching log lines.
EVIDENCE = {
    "trace_ipc_request_observed": 'IPC request service="',
    "vi_u_service_handle_requested": "sm:GetServiceHandle name=vi:u",
    "display_service_subsession_returned": "IApplicationDisplayService sub-session handle=",
    "display_cmd_2020_request_observed": 'IPC request service="IApplicationDisplayService" cmd=2020',
    "display_cmd_2020_response_observed": "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2020",
    "display_cmd_2030_request_observed": 'IPC request service="IApplicationDisplayService" cmd=2030',
    "display_cmd_2030_response_observed": "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2030",
    "binder_subsession_returned": "IHOSBinderDriver sub-session handle=",
    "binder_cmd_0_request_observed": 'IPC request service="IHOSBinderDriver" cmd=0',
    "binder_cmd_3_request_observed": 'IPC request service="IHOSBinderDriver" cmd=3',
    "igbp_connect_observed": "IGBP::Connect binder=",
    "igbp_request_buffer_observed": "IGBP::RequestBuffer binder=",
    "igbp_dequeue_buffer_observed": "IGBP::DequeueBuffer binder=",
    "igbp_queue_buffer_observed": "IGBP::QueueBuffer",
    "nvdrv_open_observed": "nvdrv:Open path=",
    "guest_default_window_marker_observed": "OutputDebugString: STAGE67_GUEST_DEFAULT_WINDOW_OBTAINED",
    "guest_framebuffer_created_marker_observed": "OutputDebugString: STAGE67_GUEST_FRAMEBUFFER_CREATED",
}


def inspect_guest_display_ipc_path(report: Path, macho_sha: str,
                                   nro_sha: str) -> dict:
    receipt = read_bounded_json(report / "smoke_result.json")
    if receipt.get("emulator_sha256") != macho_sha or receipt.get("nro_sha256") != nro_sha:
        raise ValueError("display IPC receipt binary/NRO mismatch")
    if receipt.get("status") not in ALLOWED_STATUSES or receipt.get("gameplay_verified") is not False:
        raise ValueError("display IPC receipt status untrusted")
    log_dir = report / "data-root" / "logs"
    paths = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(paths) != 1:
        raise ValueError("original display IPC log is missing or ambiguous")
    log = paths[0]
    if log.is_symlink() or not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("original display IPC log unsafe or oversized")
    data = log.read_text(encoding="utf-8", errors="replace")
    evidence = {name: token in data for name, token in EVIDENCE.items()}
    if not evidence["trace_ipc_request_observed"]:
        stage = "trace_ipc_markers_not_observed"
    elif not evidence["vi_u_service_handle_requested"]:
        stage = "before_vi_u_service_handle_observed"
    elif not evidence["display_service_subsession_returned"]:
        stage = "vi_u_requested_display_subsession_not_observed"
    elif not (evidence["display_cmd_2020_request_observed"]
              or evidence["display_cmd_2030_request_observed"]):
        stage = "display_subsession_created_native_window_request_not_observed"
    elif not (evidence["display_cmd_2020_response_observed"]
              or evidence["display_cmd_2030_response_observed"]):
        stage = "native_window_request_response_not_observed"
    elif not evidence["binder_subsession_returned"]:
        stage = "native_window_response_binder_subsession_not_observed"
    elif not (evidence["binder_cmd_0_request_observed"]
              or evidence["binder_cmd_3_request_observed"]):
        stage = "binder_subsession_transact_not_observed"
    elif not evidence["igbp_connect_observed"]:
        stage = "binder_transact_igbp_connect_not_observed"
    elif not evidence["igbp_request_buffer_observed"]:
        stage = "igbp_connect_request_buffer_not_observed"
    elif not evidence["igbp_dequeue_buffer_observed"]:
        stage = "request_buffer_dequeue_not_observed"
    elif not evidence["igbp_queue_buffer_observed"]:
        stage = "dequeue_queue_not_observed"
    else:
        stage = "igbp_queue_observed_not_gpu_proof"
    return {
        "schema": "nexium-stage73-display-ipc-path/v1",
        "observed_stage": stage,
        "probe_process_status": receipt["status"],
        **evidence,
        "guest_framebuffer_runtime_completed": False,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }
