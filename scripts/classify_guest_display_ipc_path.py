#!/usr/bin/env python3
"""Stage73: source-anchored fixed-category original guest display IPC diagnosis.

The private DEBUG log remains on the disposable native Intel runner. This
module emits only booleans and allowlisted stage categories; it never emits
raw service names from a log, command numbers, paths, IPC bytes or screenshots.
A reached IPC operation is not evidence of correct display or GPU rendering.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from observe_intel_integrated_window import read_bounded_json

MAX_LOG_BYTES = 16 * 1024 * 1024
ALLOWED_STATUSES = frozenset({
    "exited_zero_unverified", "exited_nonzero",
    "timeout_alive_unverified", "launch_failed",
})

# These are literal, allowlisted signatures from the pinned public NeXium
# service-manager/IPC/IGBP source paths. Never print matching log lines.
IPC_REQUEST_PATTERNS = (
    ("service_manager", re.compile(r'IPC request service="sm:" cmd=(\d+)')),
    ("vi_u", re.compile(r'IPC request service="vi:u" cmd=(\d+)')),
    ("display_service", re.compile(r'IPC request service="IApplicationDisplayService" cmd=(\d+)')),
    ("binder", re.compile(r'IPC request service="IHOSBinderDriver" cmd=(\d+)')),
    ("nvdrv", re.compile(r'IPC request service="nvdrv(?::[ast])?" cmd=(\d+)')),
)
IPC_RESPONSE_PATTERN = re.compile(
    r"IPC FIRST-OCCURRENCE response \(compare with RustSwitch\) "
    r"service=(sm:|vi:u|IApplicationDisplayService|IHOSBinderDriver|nvdrv(?::[ast])?) cmd=(\d+)"
)


def last_ipc_request_summary(data: str) -> dict:
    requests = []
    responses = []
    for line_no, line in enumerate(data.splitlines()):
        for service_kind, pattern in IPC_REQUEST_PATTERNS:
            match = pattern.search(line)
            if match:
                requests.append((line_no, service_kind, int(match.group(1))))
        match = IPC_RESPONSE_PATTERN.search(line)
        if match:
            responses.append((line_no, match.group(1), int(match.group(2))))
    if not requests:
        return {
            "last_ipc_request_stage": "no_allowlisted_ipc_request_observed",
            "last_ipc_request_response_after_request": None,
            "last_ipc_request_same_response_seen_before": False,
        }
    request_line, kind, command = requests[-1]
    service_name = {
        "service_manager": "sm:",
        "vi_u": "vi:u",
        "display_service": "IApplicationDisplayService",
        "binder": "IHOSBinderDriver",
        "nvdrv": None,
    }[kind]
    def same_service(response_service: str) -> bool:
        if kind == "nvdrv":
            return response_service == "nvdrv" or response_service in ("nvdrv:a", "nvdrv:s", "nvdrv:t")
        return response_service == service_name
    matching = [(line_no, service, cmd) for line_no, service, cmd in responses
                if same_service(service) and cmd == command]
    response_after = any(line_no > request_line for line_no, _, _ in matching)
    response_before = any(line_no < request_line for line_no, _, _ in matching)
    if kind == "display_service" and command in (2020, 2030):
        stage = "native_window_layer_request_last_observed"
    else:
        stage = {
            "service_manager": "service_manager_request_last_observed",
            "vi_u": "vi_u_request_last_observed",
            "display_service": "display_service_request_last_observed",
            "binder": "binder_transaction_request_last_observed",
            "nvdrv": "nvdrv_request_last_observed",
        }[kind]
    return {
        "last_ipc_request_stage": stage,
        "last_ipc_request_response_after_request": response_after,
        "last_ipc_request_same_response_seen_before": response_before,
    }


EVIDENCE = {
    "ipc_request_marker_observed": 'IPC request service="',
    "vi_u_service_handle_requested": "SM::GetServiceHandle 'vi:u'",
    "vi_u_ipc_request_observed": 'IPC request service="vi:u" cmd=',
    "display_service_subsession_returned": "IApplicationDisplayService sub-session handle=",
    "display_binder_session_cmd_100_request_observed": 'IPC request service="IApplicationDisplayService" cmd=100',
    "display_binder_session_cmd_103_request_observed": 'IPC request service="IApplicationDisplayService" cmd=103',
    "display_cmd_2020_request_observed": 'IPC request service="IApplicationDisplayService" cmd=2020',
    "display_cmd_2020_response_observed": "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2020",
    "display_cmd_2030_request_observed": 'IPC request service="IApplicationDisplayService" cmd=2030',
    "display_cmd_2030_response_observed": "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2030",
    "binder_subsession_returned": "IHOSBinderDriver sub-session handle=",
    "binder_cmd_0_request_observed": 'IPC request service="IHOSBinderDriver" cmd=0',
    "binder_cmd_3_request_observed": 'IPC request service="IHOSBinderDriver" cmd=3',
    "igbp_connect_observed": "IGBP::Connect binder=",
    "igbp_request_buffer_observed": "IGBP::RequestBuffer binder=",
    "igbp_dequeue_retry_marker_observed": "request cannot be re-issued, polling in-SVC",
    "igbp_dequeue_timeout_marker_observed": "IGBP::DequeueBuffer timed out waiting for a released slot",
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
    if log_dir.is_symlink():
        raise ValueError("original display IPC log directory unsafe")
    paths = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(paths) != 1:
        raise ValueError("original display IPC log is missing or ambiguous")
    log = paths[0]
    if log.is_symlink() or not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("original display IPC log unsafe or oversized")
    data = log.read_text(encoding="utf-8", errors="replace")
    evidence = {name: token in data for name, token in EVIDENCE.items()}
    # The Binder-session and native-window requests are independent branches after
    # IApplicationDisplayService creation. Either may occur first; both must be
    # complete before the first Binder transaction can be attributed to this path.
    def after(marker: str, position: int) -> int | None:
        found = data.find(marker, position + 1)
        return found if found >= 0 else None

    def regex_after(pattern: re.Pattern[str], position: int) -> re.Match[str] | None:
        return pattern.search(data, position + 1)

    if not evidence["ipc_request_marker_observed"]:
        stage = "ipc_request_markers_not_observed"
    else:
        sm_request = data.find('IPC request service="sm:" cmd=')
        if sm_request < 0:
            stage = "service_manager_request_not_observed"
        else:
            vi_handle = after("SM::GetServiceHandle 'vi:u'", sm_request)
            if vi_handle is None:
                stage = "before_vi_u_service_handle_observed"
            else:
                vi_request = after('IPC request service="vi:u" cmd=', vi_handle)
                if vi_request is None:
                    stage = "vi_u_handle_created_ipc_request_not_observed"
                else:
                    display_subsession = after(
                        "IApplicationDisplayService sub-session handle=", vi_request
                    )
                    if display_subsession is None:
                        stage = "vi_u_ipc_request_display_subsession_not_observed"
                    else:
                        binder_session_request_pattern = re.compile(
                            r'IPC request service="IApplicationDisplayService" cmd=(100|103)\b'
                        )
                        binder_session_request = regex_after(
                            binder_session_request_pattern, display_subsession
                        )
                        binder_subsession = (
                            after(
                                "IHOSBinderDriver sub-session handle=",
                                binder_session_request.start(),
                            )
                            if binder_session_request is not None else None
                        )

                        native_window_request_pattern = re.compile(
                            r'IPC request service="IApplicationDisplayService" cmd=(2020|2030)\b'
                        )
                        native_window_request = regex_after(
                            native_window_request_pattern, display_subsession
                        )
                        native_window_response = None
                        if native_window_request is not None:
                            native_window_cmd = native_window_request.group(1)
                            native_window_response_pattern = re.compile(
                                r"IPC FIRST-OCCURRENCE response \(compare with RustSwitch\) "
                                r"service=IApplicationDisplayService cmd="
                                + re.escape(native_window_cmd)
                                + r"\b"
                            )
                            native_window_response = regex_after(
                                native_window_response_pattern,
                                native_window_request.start(),
                            )

                        pending_branches = []
                        if binder_session_request is not None and binder_subsession is None:
                            pending_branches.append((
                                binder_session_request.start(),
                                "display_service_binder_subsession_not_observed",
                            ))
                        if native_window_request is not None and native_window_response is None:
                            pending_branches.append((
                                native_window_request.start(),
                                "native_window_request_response_not_observed",
                            ))

                        if pending_branches:
                            stage = max(pending_branches)[1]
                        elif binder_session_request is None and native_window_request is None:
                            stage = "display_subsession_binder_or_native_window_request_not_observed"
                        elif binder_session_request is None:
                            stage = "display_subsession_binder_session_request_not_observed"
                        elif binder_subsession is None:
                            stage = "display_service_binder_subsession_not_observed"
                        elif native_window_request is None:
                            stage = "binder_subsession_created_native_window_request_not_observed"
                        elif native_window_response is None:
                            stage = "native_window_request_response_not_observed"
                        else:
                            ready_after = max(binder_subsession, native_window_response.start())
                            binder_transaction_pattern = re.compile(
                                r'IPC request service="IHOSBinderDriver" cmd=(0|3)\b'
                            )
                            binder_transaction = regex_after(
                                binder_transaction_pattern, ready_after
                            )
                            if binder_transaction is None:
                                stage = "display_and_native_window_ready_binder_transact_not_observed"
                            else:
                                connect = after(
                                    "IGBP::Connect binder=", binder_transaction.start()
                                )
                                if connect is None:
                                    stage = "binder_transact_igbp_connect_not_observed"
                                else:
                                    request_buffer = after(
                                        "IGBP::RequestBuffer binder=", connect
                                    )
                                    if request_buffer is None:
                                        stage = "igbp_connect_request_buffer_not_observed"
                                    else:
                                        operation_markers = (
                                            "IGBP::QueueBuffer",
                                            "request cannot be re-issued, polling in-SVC",
                                            "IGBP::DequeueBuffer timed out waiting for a released slot",
                                        )
                                        later_operations = []
                                        for marker in operation_markers:
                                            offset = request_buffer + 1
                                            while True:
                                                found = data.find(marker, offset)
                                                if found < 0:
                                                    break
                                                later_operations.append((found, marker))
                                                offset = found + len(marker)
                                        if not later_operations:
                                            stage = (
                                                "igbp_request_buffer_observed_later_buffer_operations_"
                                                "unverified_at_debug_level"
                                            )
                                        else:
                                            _, last_marker = max(later_operations)
                                            if last_marker == "IGBP::QueueBuffer":
                                                stage = "igbp_queue_observed_not_gpu_proof"
                                            else:
                                                stage = "igbp_dequeue_retry_or_timeout_observed"
    return {
        "schema": "nexium-stage73-display-ipc-path/v1",
        "observed_stage": stage,
        "probe_process_status": receipt["status"],
        **last_ipc_request_summary(data),
        **evidence,
        "guest_framebuffer_runtime_completed": False,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }
