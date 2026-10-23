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
# Conservative classifier sanity cap for display-service replies, not a protocol limit.
MAX_DISPLAY_IPC_RESPONSE_BYTES = 1024 * 1024
ALLOWED_STATUSES = frozenset({
    "exited_zero_unverified", "exited_nonzero",
    "timeout_alive_unverified", "launch_failed",
})

# These are literal, allowlisted signatures from the pinned public NeXium
# service-manager/IPC/IGBP source paths. Never print matching log lines.
IPC_REQUEST_PATTERNS = (
    ("service_manager", re.compile(r'IPC request service="(sm:)" cmd=(\d+)')),
    ("vi_u", re.compile(r'IPC request service="(vi:u)" cmd=(\d+)')),
    ("display_service", re.compile(r'IPC request service="(IApplicationDisplayService)" cmd=(\d+)')),
    ("binder", re.compile(r'IPC request service="(IHOSBinderDriver)" cmd=(\d+)')),
    ("nvdrv", re.compile(r'IPC request service="(nvdrv(?::[ast])?)" cmd=(\d+)')),
)
# The pinned dispatcher maps SM command 0 to RegisterClient and command 1
# to GetServiceHandle. Only cmd=1 can anchor a vi:u handle acquisition path.
SERVICE_MANAGER_ANY_REQUEST = re.compile(
    r'IPC request service="sm:" cmd=\d+\b'
)
SERVICE_MANAGER_GET_SERVICE_HANDLE_REQUEST = re.compile(
    r'IPC request service="sm:" cmd=1\b'
)
SM_GET_SERVICE_HANDLE_EVENT = re.compile(r"SM::GetServiceHandle '([^']*)'")
IPC_RESPONSE_PATTERN = re.compile(
    r"IPC FIRST-OCCURRENCE response \(compare with RustSwitch\) "
    r"service=(sm:|vi:u|IApplicationDisplayService|IHOSBinderDriver|nvdrv(?::[ast])?) cmd=(\d+)"
)
# Correlate BufferQueue evidence by the binder ID printed by the pinned source.
# Never expose that ID in the sanitized classification result.
IGBP_CONNECT_PATTERN = re.compile(r"IGBP::Connect binder=(\d+)\b")
IGBP_REQUEST_BUFFER_PATTERN = re.compile(r"IGBP::RequestBuffer binder=(\d+)\b")
IGBP_DEQUEUE_RETRY_PATTERN = re.compile(
    r"IGBP::DequeueBuffer binder=(\d+): request cannot be re-issued, polling in-SVC"
)
IGBP_DEQUEUE_TIMEOUT_PATTERN = re.compile(
    r"IGBP::DequeueBuffer timed out waiting for a released slot binder=(\d+)\b"
)
IGBP_QUEUE_BUFFER_PATTERN = re.compile(r"IGBP::QueueBuffer binder=(\d+)\b")



def last_ipc_request_summary(data: str) -> dict:
    requests = []
    responses = []
    for line_no, line in enumerate(data.splitlines()):
        for service_kind, pattern in IPC_REQUEST_PATTERNS:
            match = pattern.search(line)
            if match:
                # Preserve the exact service endpoint. nvdrv:a, nvdrv:s and
                # nvdrv:t share a family but are not interchangeable endpoints.
                requests.append((line_no, service_kind, match.group(1),
                                 int(match.group(2))))
        match = IPC_RESPONSE_PATTERN.search(line)
        if match:
            responses.append((line_no, match.group(1), int(match.group(2))))
    if not requests:
        return {
            "last_ipc_request_stage": "no_allowlisted_ipc_request_observed",
            "last_ipc_request_response_after_request": None,
            "last_ipc_request_same_response_seen_before": False,
        }
    request_line, kind, request_service, command = requests[-1]
    matching = [(line_no, service, cmd) for line_no, service, cmd in responses
                if service == request_service and cmd == command]
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


DOWNSTREAM_IPC_EVIDENCE = (
    "display_service_subsession_returned",
    "display_binder_session_cmd_100_request_observed",
    "display_binder_session_cmd_103_request_observed",
    "display_cmd_2020_request_observed",
    "display_cmd_2030_request_observed",
    "binder_subsession_returned",
    "binder_cmd_0_request_observed",
    "binder_cmd_3_request_observed",
    "igbp_connect_observed",
    "igbp_request_buffer_observed",
    "igbp_dequeue_retry_marker_observed",
    "igbp_dequeue_timeout_marker_observed",
    "igbp_queue_buffer_observed",
)


def inspect_guest_display_ipc_path(report: Path, macho_sha: str,
                                   nro_sha: str) -> dict:
    # The report directory is part of the trust boundary too: rejecting only
    # linked child files would still allow the entire evidence root to be
    # redirected to a different directory before the receipt is read.
    if report.is_symlink() or not report.is_dir():
        raise ValueError("display IPC report directory unsafe")
    receipt = read_bounded_json(report / "smoke_result.json")
    if receipt.get("emulator_sha256") != macho_sha or receipt.get("nro_sha256") != nro_sha:
        raise ValueError("display IPC receipt binary/NRO mismatch")
    if receipt.get("status") not in ALLOWED_STATUSES or receipt.get("gameplay_verified") is not False:
        raise ValueError("display IPC receipt status untrusted")
    data_root = report / "data-root"
    log_dir = data_root / "logs"
    if data_root.is_symlink() or log_dir.is_symlink():
        raise ValueError("original display IPC log directory unsafe")
    paths = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(paths) != 1:
        raise ValueError("original display IPC log is missing or ambiguous")
    log = paths[0]
    if log.is_symlink() or not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("original display IPC log unsafe or oversized")
    data = log.read_text(encoding="utf-8", errors="replace")
    evidence = {name: token in data for name, token in EVIDENCE.items()}
    native_window_response_status = "not_observed"
    # The Binder-session and native-window requests are independent branches after
    # IApplicationDisplayService creation. Either may occur first; both must be
    # complete before the first Binder transaction can be attributed to this path.
    def after(marker: str, position: int) -> int | None:
        found = data.find(marker, position + 1)
        return found if found >= 0 else None

    def regex_after(pattern: re.Pattern[str], position: int) -> re.Match[str] | None:
        return pattern.search(data, position + 1)

    downstream_ipc_observed = any(
        evidence[name] for name in DOWNSTREAM_IPC_EVIDENCE
    )

    def iter_vi_u_handle_requests():
        # The request log contains the command but not its input bytes. Pair a
        # cmd=1 request only with the next service-manager handler event, and
        # reject it if another SM request intervenes. This conservative order
        # check avoids reusing an unrelated cmd=1 to explain a later vi:u marker.
        for request_match in SERVICE_MANAGER_GET_SERVICE_HANDLE_REQUEST.finditer(data):
            handle_match = SM_GET_SERVICE_HANDLE_EVENT.search(data, request_match.end())
            if handle_match is None or handle_match.group(1) != "vi:u":
                continue
            next_request = SERVICE_MANAGER_ANY_REQUEST.search(data, request_match.end())
            if next_request is not None and next_request.start() < handle_match.start():
                continue
            yield request_match.start(), handle_match.start()

    def find_expected_ancestry() -> tuple[int, int, int, int] | None:
        # Logs can contain unrelated or repeated service-manager requests.
        # Search for a complete ordered chain rather than binding to the first
        # global sm: request. This still does not claim thread-level correlation.
        for sm_request, vi_handle in iter_vi_u_handle_requests():
            vi_request = after('IPC request service="vi:u" cmd=', vi_handle)
            if vi_request is None:
                continue
            display_subsession = after(
                "IApplicationDisplayService sub-session handle=", vi_request
            )
            if display_subsession is not None:
                return sm_request, vi_handle, vi_request, display_subsession
        return None

    ancestry = find_expected_ancestry()
    sequence_inconsistent = downstream_ipc_observed and ancestry is None
    if sequence_inconsistent:
        # The response signature can exist in the log without a validated
        # request ancestry. Report it as present but unattributed, not absent.
        if (evidence["display_cmd_2020_response_observed"]
                or evidence["display_cmd_2030_response_observed"]):
            native_window_response_status = "observed_but_unattributed"
        # Downstream markers exist, but the required ordered vi:u ancestry
        # cannot be established. Do not misreport this as an early stop.
        stage = "ipc_sequence_inconsistent_or_cross_path"
    elif not evidence["ipc_request_marker_observed"]:
        stage = "ipc_request_markers_not_observed"
    else:
        if ancestry is not None:
            sm_request, vi_handle, vi_request, display_subsession = ancestry
        else:
            paired_handle = next(iter(iter_vi_u_handle_requests()), None)
            if paired_handle is not None:
                sm_request, vi_handle = paired_handle
            else:
                sm_match = SERVICE_MANAGER_GET_SERVICE_HANDLE_REQUEST.search(data)
                sm_request = sm_match.start() if sm_match is not None else -1
                vi_handle = None
            vi_request = (
                after('IPC request service="vi:u" cmd=', vi_handle)
                if vi_handle is not None else None
            )
            display_subsession = (
                after("IApplicationDisplayService sub-session handle=", vi_request)
                if vi_request is not None else None
            )
        if sm_request < 0:
            any_sm_request = re.search(r'IPC request service="sm:" cmd=\d+\b', data)
            stage = (
                "service_manager_get_service_handle_request_not_observed"
                if any_sm_request is not None
                else "service_manager_request_not_observed"
            )
        elif vi_handle is None:
            unpaired_vi_handle = any(
                match.group(1) == "vi:u"
                for match in SM_GET_SERVICE_HANDLE_EVENT.finditer(data)
            )
            stage = (
                "vi_u_service_handle_marker_without_correlated_cmd1"
                if unpaired_vi_handle
                else "before_vi_u_service_handle_observed"
            )
        elif vi_request is None:
            stage = "vi_u_handle_created_ipc_request_not_observed"
        elif display_subsession is None:
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
                response_match = regex_after(
                    native_window_response_pattern,
                    native_window_request.start(),
                )
                if response_match is None:
                    native_window_response_status = "no_response"
                else:
                    same_command_request_pattern = re.compile(
                        r'IPC request service="IApplicationDisplayService" cmd='
                        + re.escape(native_window_cmd)
                        + r'\b'
                    )
                    repeated_request = same_command_request_pattern.search(
                        data, native_window_request.end(), response_match.start()
                    )
                    if repeated_request is not None:
                        # The first-occurrence response is not correlated to a
                        # request/thread ID. A second outstanding request makes
                        # the response unsafe to attribute to the first request.
                        native_window_response_status = "ambiguous"
                    else:
                        line_end = data.find("\n", response_match.start())
                        if line_end < 0:
                            line_end = len(data)
                        response_line = data[response_match.start():line_end]
                        rc_match = re.search(r"\brc=(0x[0-9a-fA-F]{8})\b", response_line)
                        response_len_match = re.search(r"\bresponse_len=([0-9]{1,20})\b", response_line)
                        preview_match = re.search(
                            r"\bresponse_first64=([0-9a-fA-F,]{0,191})\s+in_data_first32=",
                            response_line,
                        )
                        if (rc_match is None or response_len_match is None
                                or preview_match is None):
                            native_window_response_status = "unverified"
                        else:
                            response_len = int(response_len_match.group(1))
                            preview_text = preview_match.group(1)
                            preview_tokens = preview_text.split(",") if preview_text else []
                            valid_preview = (
                                response_len <= MAX_DISPLAY_IPC_RESPONSE_BYTES
                                and len(preview_tokens) == min(response_len, 64)
                                and all(re.fullmatch(r"[0-9a-fA-F]{2}", token)
                                        for token in preview_tokens)
                            )
                            if not valid_preview:
                                native_window_response_status = "unverified"
                            else:
                                preview_bytes = bytes(
                                    int(token, 16) for token in preview_tokens
                                )
                                sfco_offset = preview_bytes.find(b"SFCO")
                                if sfco_offset < 0 or sfco_offset + 12 > len(preview_bytes):
                                    # svc.rs defaults its logged rc to zero if SFCO
                                    # is absent; that fallback is not success proof.
                                    native_window_response_status = "unverified"
                                else:
                                    header_rc = int.from_bytes(
                                        preview_bytes[sfco_offset + 8:sfco_offset + 12],
                                        "little",
                                    )
                                    logged_rc = int(rc_match.group(1), 16)
                                    if header_rc != logged_rc:
                                        native_window_response_status = "unverified"
                                    elif header_rc == 0:
                                        native_window_response_status = "success"
                                        native_window_response = response_match
                                    else:
                                        native_window_response_status = "failure"

            pending_branches = []
            if binder_session_request is not None and binder_subsession is None:
                pending_branches.append((
                    binder_session_request.start(),
                    "display_service_binder_subsession_not_observed",
                ))
            if native_window_request is not None and native_window_response is None:
                response_stage = {
                    "no_response": "native_window_request_response_not_observed",
                    "failure": "native_window_request_failed_response_observed",
                    "unverified": "native_window_request_response_status_unverified",
                    "ambiguous": "native_window_request_response_correlation_ambiguous",
                }.get(
                    native_window_response_status,
                    "native_window_request_response_status_unverified",
                )
                pending_branches.append((
                    native_window_request.start(),
                    response_stage,
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
                    connect_match = regex_after(
                        IGBP_CONNECT_PATTERN, binder_transaction.start()
                    )
                    if connect_match is None:
                        stage = "binder_transact_igbp_connect_not_observed"
                    else:
                        connect_binder = connect_match.group(1)
                        buffer_matches = list(
                            IGBP_REQUEST_BUFFER_PATTERN.finditer(
                                data, connect_match.end()
                            )
                        )
                        request_buffer_match = next(
                            (match for match in buffer_matches
                             if match.group(1) == connect_binder),
                            None,
                        )
                        if request_buffer_match is None:
                            if buffer_matches:
                                stage = "igbp_connect_request_buffer_binder_mismatch"
                            else:
                                stage = "igbp_connect_request_buffer_not_observed"
                        else:
                            request_buffer = request_buffer_match.end()
                            operation_patterns = (
                                ("queue", IGBP_QUEUE_BUFFER_PATTERN),
                                ("dequeue_retry", IGBP_DEQUEUE_RETRY_PATTERN),
                                ("dequeue_timeout", IGBP_DEQUEUE_TIMEOUT_PATTERN),
                            )
                            later_operations = []
                            other_binder_operations = []
                            for operation_kind, pattern in operation_patterns:
                                for match in pattern.finditer(data, request_buffer):
                                    item = (match.start(), operation_kind)
                                    if match.group(1) == connect_binder:
                                        later_operations.append(item)
                                    else:
                                        other_binder_operations.append(item)
                            if not later_operations:
                                if other_binder_operations:
                                    stage = (
                                        "igbp_request_buffer_other_binder_activity_"
                                        "unverified"
                                    )
                                else:
                                    stage = (
                                        "igbp_request_buffer_observed_later_buffer_operations_"
                                        "unverified_at_debug_level"
                                    )
                            else:
                                _, last_operation = max(later_operations)
                                if last_operation == "queue":
                                    stage = "igbp_queue_observed_not_gpu_proof"
                                else:
                                    stage = "igbp_dequeue_retry_or_timeout_observed"
    return {
        "schema": "nexium-stage73-display-ipc-path/v1",
        "observed_stage": stage,
        "expected_vi_u_display_ancestry_observed": ancestry is not None,
        "downstream_ipc_without_expected_ancestry": sequence_inconsistent,
        "probe_process_status": receipt["status"],
        **last_ipc_request_summary(data),
        "native_window_response_status": native_window_response_status,
        **evidence,
        "guest_framebuffer_runtime_completed": False,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }
