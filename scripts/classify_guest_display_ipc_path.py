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
from stage73_safe_evidence_read import read_bounded_regular_bytes

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
    ("service_manager", re.compile(r'IPC request service=\"(sm:)\" cmd=(\d+)')),
    ("vi_u", re.compile(r'IPC request service=\"(vi:u)\" cmd=(\d+)')),
    ("vi_m", re.compile(r'IPC request service=\"(vi:m)\" cmd=(\d+)')),
    ("vi_s", re.compile(r'IPC request service=\"(vi:s)\" cmd=(\d+)')),
    ("display_service", re.compile(r'IPC request service=\"(IApplicationDisplayService)\" cmd=(\d+)')),
    ("binder", re.compile(r'IPC request service=\"(IHOSBinderDriver)\" cmd=(\d+)')),
    ("nvdrv", re.compile(r'IPC request service=\"(nvdrv(?::[ast])?)\" cmd=(\d+)')),
)
VI_SERVICES = frozenset(("vi:u", "vi:m", "vi:s"))

# The pinned dispatcher maps SM command 0 to RegisterClient and command 1
# to GetServiceHandle. Only cmd=1 can anchor a VI service handle acquisition path.
SERVICE_MANAGER_ANY_REQUEST = re.compile(
    r'IPC request service="sm:" cmd=\d+\b'
)
SERVICE_MANAGER_GET_SERVICE_HANDLE_REQUEST = re.compile(
    r'IPC request service="sm:" cmd=1\b'
)
SM_GET_SERVICE_HANDLE_EVENT = re.compile(r"SM::GetServiceHandle '([^']*)'")
SM_RETURN_HANDLE_PATTERN = re.compile(r"SM: returning handle (0x[0-9a-fA-F]+) for service '([^']+)'")
SESSION_IPC_REQUEST_PATTERN = re.compile(
    r'IPC request service="([^"]+)" cmd=(\d+) session=(0x[0-9a-fA-F]+)\b'
)
SUBSESSION_PARENT_PATTERN = re.compile(
    r"([A-Za-z][A-Za-z0-9]*) sub-session handle=(0x[0-9a-fA-F]+) parent_session=(0x[0-9a-fA-F]+)"
)
IPC_RESPONSE_PATTERN = re.compile(
    r"IPC FIRST-OCCURRENCE response \(compare with RustSwitch\) "
    r"service=(sm:|vi:u|vi:m|vi:s|IApplicationDisplayService|IHOSBinderDriver|nvdrv(?::[ast])?) cmd=(\d+)"
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



# The pinned scoped diagnostic patch deduplicates responses by
# (service, session, command). Do not attribute another session's first reply
# to the latest request merely because its service and command match.
# None represents an *unscoped* legacy log, never a wildcard.
IPC_LINE_SESSION_PATTERN = re.compile(r"\bsession=(0x[0-9a-fA-F]+)\b")


def last_ipc_request_summary(data: str) -> dict:
    requests = []
    responses = []
    for line_no, line in enumerate(data.splitlines()):
        session_match = IPC_LINE_SESSION_PATTERN.search(line)
        session = int(session_match.group(1), 16) if session_match else None
        for service_kind, pattern in IPC_REQUEST_PATTERNS:
            match = pattern.search(line)
            if match:
                # Preserve the exact service endpoint. nvdrv:a, nvdrv:s and
                # nvdrv:t share a family but are not interchangeable endpoints.
                requests.append((line_no, service_kind, match.group(1),
                                 int(match.group(2)), session))
        match = IPC_RESPONSE_PATTERN.search(line)
        if match:
            responses.append((line_no, match.group(1), int(match.group(2)),
                              session))
    if not requests:
        return {
            "last_ipc_request_stage": "no_allowlisted_ipc_request_observed",
            "last_ipc_request_response_after_request": None,
            "last_ipc_request_same_response_seen_before": False,
            "last_ipc_request_session_scoped": None,
            "last_ipc_request_other_session_response_after_request": None,
            "last_ipc_request_prior_unanswered_same_command": None,
        }
    request_line, kind, request_service, command, request_session = requests[-1]
    matching = [(line_no, service, cmd, reply_session)
                for line_no, service, cmd, reply_session in responses
                if (service == request_service and cmd == command
                    and reply_session == request_session)]
    # If an earlier identical request is still pending, a later first-
    # occurrence reply cannot be assigned to the final request without a
    # request/thread correlation ID, even if the session handle matches.
    # Treat unscoped legacy request groups the same way (None is never a
    # wildcard). Keep request IDs and raw session handles out of the result.
    previous_matching_requests = [
        earlier_line for earlier_line, _, service, cmd, session in requests[:-1]
        if service == request_service and cmd == command
        and session == request_session
    ]
    # Pair each earlier reply at most once, in log order. Reusing one
    # response to discharge multiple overlapping requests would certify a
    # false completion. Orphan replies before the first request do not count.
    prior_events = sorted(
        [(line_no, 1) for line_no in previous_matching_requests]
        + [(line_no, -1) for line_no, _, _, _ in matching
           if line_no < request_line]
    )
    outstanding_prior = 0
    for _, change in prior_events:
        if change > 0:
            outstanding_prior += 1
        elif outstanding_prior:
            outstanding_prior -= 1
    prior_unanswered = outstanding_prior > 0
    response_after = (
        not prior_unanswered and
        any(line_no > request_line for line_no, _, _, _ in matching)
    )
    response_before = any(line_no < request_line for line_no, _, _, _ in matching)
    other_session_after = (
        any(line_no > request_line and service == request_service
            and cmd == command and reply_session != request_session
            for line_no, service, cmd, reply_session in responses)
        if request_session is not None else False
    )
    if kind == "display_service" and command in (2020, 2030):
        stage = "native_window_layer_request_last_observed"
    else:
        stage = {
            "service_manager": "service_manager_request_last_observed",
            "vi_u": "vi_u_request_last_observed",
            "vi_m": "vi_m_request_last_observed",
            "vi_s": "vi_s_request_last_observed",
            "display_service": "display_service_request_last_observed",
            "binder": "binder_transaction_request_last_observed",
            "nvdrv": "nvdrv_request_last_observed",
        }[kind]
    return {
        "last_ipc_request_stage": stage,
        "last_ipc_request_response_after_request": response_after,
        "last_ipc_request_same_response_seen_before": response_before,
        "last_ipc_request_session_scoped": request_session is not None,
        "last_ipc_request_other_session_response_after_request": other_session_after,
        "last_ipc_request_prior_unanswered_same_command": prior_unanswered,
    }


EVIDENCE = {
    "ipc_request_marker_observed": 'IPC request service="',
    "vi_u_service_handle_requested": "SM::GetServiceHandle 'vi:u'",
    "vi_m_service_handle_requested": "SM::GetServiceHandle 'vi:m'",
    "vi_s_service_handle_requested": "SM::GetServiceHandle 'vi:s'",
    "vi_u_ipc_request_observed": 'IPC request service="vi:u" cmd=',
    "vi_m_ipc_request_observed": 'IPC request service="vi:m" cmd=',
    "vi_s_ipc_request_observed": 'IPC request service="vi:s" cmd=',
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


def _path_contains_symlink_component(path: Path) -> bool:
    """Reject symlinks in every component, not only the final path element."""
    candidate = path if path.is_absolute() else Path.cwd() / path
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if part != ".." and current.is_symlink():
            return True
    return False


def inspect_guest_display_ipc_path(report: Path, macho_sha: str,
                                   nro_sha: str) -> dict:
    # The report directory is part of the trust boundary too: rejecting only
    # linked child files would still allow the entire evidence root to be
    # redirected to a different directory before the receipt is read.
    if _path_contains_symlink_component(report) or not report.is_dir():
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
    data = read_bounded_regular_bytes(log, MAX_LOG_BYTES).decode("utf-8", errors="replace")
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

    def iter_vi_handle_requests():
        # The request log contains the command but not its input bytes. Pair a
        # cmd=1 request only with the next service-manager handler event, and
        # reject it if another SM request intervenes. VI exposes user, manager
        # and system service variants; each can return the display-service
        # subsession according to the pinned dispatcher map.
        for request_match in SERVICE_MANAGER_GET_SERVICE_HANDLE_REQUEST.finditer(data):
            handle_match = SM_GET_SERVICE_HANDLE_EVENT.search(data, request_match.end())
            if handle_match is None or handle_match.group(1) not in VI_SERVICES:
                continue
            next_request = SERVICE_MANAGER_ANY_REQUEST.search(data, request_match.end())
            if next_request is not None and next_request.start() < handle_match.start():
                continue
            yield request_match.start(), handle_match.start(), handle_match.group(1)

    session_correlation_fields_observed = SESSION_IPC_REQUEST_PATTERN.search(data) is not None
    session_correlation = {
        "vi_service_handle_return_correlated": False if session_correlation_fields_observed else None,
        "vi_request_session_correlated": False if session_correlation_fields_observed else None,
        "vi_display_request_ambiguous": False if session_correlation_fields_observed else None,
        "display_subsession_parent_correlated": False if session_correlation_fields_observed else None,
        "display_binder_request_session_correlated": False if session_correlation_fields_observed else None,
        "binder_subsession_parent_correlated": False if session_correlation_fields_observed else None,
        "binder_subsession_request_ambiguous": False if session_correlation_fields_observed else None,
        "native_window_request_session_correlated": False if session_correlation_fields_observed else None,
        "native_window_response_session_correlated": False if session_correlation_fields_observed else None,
        "binder_transaction_session_correlated": False if session_correlation_fields_observed else None,
    }

    def session_request(service: str, commands: tuple[int, ...],
                        after_position: int, expected_session: int):
        # All IDs are used transiently; never return or log raw handles.
        return next((
            match for match in SESSION_IPC_REQUEST_PATTERN.finditer(
                data, after_position + 1)
            if match.group(1) == service
            and int(match.group(2)) in commands
            and int(match.group(3), 16) == expected_session
        ), None)

    def scoped_response(service: str, command: str, position: int,
                        expected_session: int):
        pattern = re.compile(
            r"IPC FIRST-OCCURRENCE response \(compare with RustSwitch\) "
            r"service=" + re.escape(service) + r" cmd=" + command + r"\b"
        )
        other_session_observed = False
        for match in pattern.finditer(data, position + 1):
            end = data.find("\n", match.start())
            line = data[match.start():end if end >= 0 else len(data)]
            marker = IPC_LINE_SESSION_PATTERN.search(line)
            if (marker is not None and
                    int(marker.group(1), 16) == expected_session):
                return match, other_session_observed
            other_session_observed = True
        return None, other_session_observed

    def find_expected_ancestry() -> tuple[int, int, int, int, str] | None:
        # When session IDs are available, ordering alone is insufficient:
        # correlate the SM-returned VI handle to the VI request, then require
        # the returned display sub-session to name that same parent session.
        if session_correlation_fields_observed:
            for sm_request, vi_handle, vi_service in iter_vi_handle_requests():
                returned = SM_RETURN_HANDLE_PATTERN.search(data, vi_handle)
                if returned is None or returned.group(2) != vi_service:
                    continue
                next_request = SERVICE_MANAGER_ANY_REQUEST.search(data, vi_handle + 1)
                next_handler = SM_GET_SERVICE_HANDLE_EVENT.search(data, vi_handle + 1)
                intervening_return = SM_RETURN_HANDLE_PATTERN.search(data, vi_handle)
                # The handle value alone does not identify which simultaneous
                # SM handler produced it. Stop at the next handler/request,
                # or the first unrelated return; otherwise a later VI return
                # can be borrowed from a separate service-manager operation.
                # This can fail closed on incomplete/interleaved debug logs,
                # but must not assert an unprovable guest display ancestry.
                if ((next_request is not None
                     and next_request.start() < returned.start())
                        or (next_handler is not None
                            and next_handler.start() < returned.start())
                        or (intervening_return is not None
                            and intervening_return.start() < returned.start())):
                    continue
                session_correlation["vi_service_handle_return_correlated"] = True
                returned_handle = int(returned.group(1), 16)
                vi_request_match = next(
                    (
                        match for match in SESSION_IPC_REQUEST_PATTERN.finditer(data, returned.end())
                        if match.group(1) == vi_service
                        and int(match.group(3), 16) == returned_handle
                        and int(match.group(2)) in (0, 1, 2, 3)
                    ),
                    None,
                )
                if vi_request_match is None:
                    continue
                session_correlation["vi_request_session_correlated"] = True
                display_subsession_match = next(
                    (
                        match for match in SUBSESSION_PARENT_PATTERN.finditer(
                            data, vi_request_match.end()
                        )
                        if match.group(1) == "IApplicationDisplayService"
                        and int(match.group(3), 16) == returned_handle
                    ),
                    None,
                )
                if display_subsession_match is None:
                    continue
                # An interleaved second VI display request on the same
                # service handle leaves the sub-session response ambiguous:
                # the instrumentation has no request ID to disambiguate it.
                # Requests on other handles do not affect this path.
                overlapping_vi_request = next((
                    match for match in SESSION_IPC_REQUEST_PATTERN.finditer(
                        data, vi_request_match.end(),
                        display_subsession_match.start())
                    if match.group(1) == vi_service
                    and int(match.group(2)) in (0, 1, 2, 3)
                    and int(match.group(3), 16) == returned_handle
                ), None)
                if overlapping_vi_request is not None:
                    session_correlation["vi_display_request_ambiguous"] = True
                    continue
                session_correlation["display_subsession_parent_correlated"] = True
                return (
                    sm_request, vi_handle, vi_request_match.start(),
                    display_subsession_match.start(), vi_service,
                    int(display_subsession_match.group(2), 16),
                )
            return None

        # Compatibility for older synthetic fixtures without session fields.
        for sm_request, vi_handle, vi_service in iter_vi_handle_requests():
            vi_request_match = re.search(
                r'IPC request service="' + re.escape(vi_service) + r'" cmd=(?:0|1|2|3)\b',
                data[vi_handle + 1:],
            )
            vi_request = (
                vi_handle + 1 + vi_request_match.start()
                if vi_request_match is not None else None
            )
            if vi_request is None:
                continue
            display_subsession = after(
                "IApplicationDisplayService sub-session handle=", vi_request
            )
            if display_subsession is not None:
                return sm_request, vi_handle, vi_request, display_subsession, vi_service, None
        return None

    ancestry = find_expected_ancestry()
    variant_evidence = (
        ("vi_u", evidence["vi_u_service_handle_requested"] or evidence["vi_u_ipc_request_observed"]),
        ("vi_m", evidence["vi_m_service_handle_requested"] or evidence["vi_m_ipc_request_observed"]),
        ("vi_s", evidence["vi_s_service_handle_requested"] or evidence["vi_s_ipc_request_observed"]),
    )
    observed_variants = [name for name, seen in variant_evidence if seen]
    observed_vi_service_variant = (
        {"vi:u": "vi_u", "vi:m": "vi_m", "vi:s": "vi_s"}[ancestry[4]]
        if ancestry is not None
        else observed_variants[0] if len(observed_variants) == 1
        else "multiple_or_unresolved" if observed_variants
        else "not_observed"
    )
    sequence_inconsistent = downstream_ipc_observed and ancestry is None
    if sequence_inconsistent:
        # The response signature can exist in the log without a validated
        # request ancestry. Report it as present but unattributed, not absent.
        if (evidence["display_cmd_2020_response_observed"]
                or evidence["display_cmd_2030_response_observed"]):
            native_window_response_status = "observed_but_unattributed"
        # Downstream markers exist, but the required ordered VI-display ancestry
        # cannot be established. Do not misreport this as an early stop.
        stage = "ipc_sequence_inconsistent_or_cross_path"
    elif not evidence["ipc_request_marker_observed"]:
        stage = "ipc_request_markers_not_observed"
    else:
        if ancestry is not None:
            sm_request, vi_handle, vi_request, display_subsession, vi_service, display_session = ancestry
        else:
            paired_handle = next(iter(iter_vi_handle_requests()), None)
            if paired_handle is not None:
                sm_request, vi_handle, vi_service = paired_handle
            else:
                sm_match = SERVICE_MANAGER_GET_SERVICE_HANDLE_REQUEST.search(data)
                sm_request = sm_match.start() if sm_match is not None else -1
                vi_handle = None
                vi_service = None
            vi_request = (
                after(f'IPC request service="{vi_service}" cmd=', vi_handle)
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
            unpaired_vi_services = [
                match.group(1)
                for match in SM_GET_SERVICE_HANDLE_EVENT.finditer(data)
                if match.group(1) in VI_SERVICES
            ]
            if "vi:u" in unpaired_vi_services:
                stage = "vi_u_service_handle_marker_without_correlated_cmd1"
            elif unpaired_vi_services:
                stage = "vi_service_handle_marker_without_correlated_cmd1"
            elif evidence["vi_m_ipc_request_observed"] or evidence["vi_s_ipc_request_observed"]:
                stage = "before_vi_service_handle_observed"
            else:
                stage = "before_vi_u_service_handle_observed"
        elif vi_request is None:
            stage = (
                "vi_u_handle_created_ipc_request_not_observed"
                if vi_service == "vi:u"
                else "vi_service_handle_created_ipc_request_not_observed"
            )
        elif display_subsession is None:
            stage = (
                "vi_u_ipc_request_display_subsession_not_observed"
                if vi_service == "vi:u"
                else "vi_ipc_request_display_subsession_not_observed"
            )
        else:
            binder_session_request_pattern = re.compile(
                r'IPC request service="IApplicationDisplayService" cmd=(100|103)\b'
            )
            native_window_request_pattern = re.compile(
                r'IPC request service="IApplicationDisplayService" cmd=(2020|2030)\b'
            )
            if display_session is None:
                # Historical synthetic fixtures without instrumented handles.
                binder_session_request = regex_after(
                    binder_session_request_pattern, display_subsession)
                binder_subsession = (
                    after("IHOSBinderDriver sub-session handle=",
                          binder_session_request.start())
                    if binder_session_request is not None else None
                )
                binder_session = None
                native_window_request = regex_after(
                    native_window_request_pattern, display_subsession)
            else:
                binder_session_request = session_request(
                    "IApplicationDisplayService", (100, 103),
                    display_subsession, display_session)
                native_window_request = session_request(
                    "IApplicationDisplayService", (2020, 2030),
                    display_subsession, display_session)
                session_correlation["display_binder_request_session_correlated"] = (
                    binder_session_request is not None)
                session_correlation["native_window_request_session_correlated"] = (
                    native_window_request is not None)
                binder_subsession_match = (
                    next((match for match in SUBSESSION_PARENT_PATTERN.finditer(
                        data, binder_session_request.end())
                        if match.group(1) == "IHOSBinderDriver"
                        and int(match.group(3), 16) == display_session),
                         None)
                    if binder_session_request is not None else None
                )
                # The parent handle identifies the display session, but a
                # response is NOT attributable to the first request when a
                # second same-session Binder request was issued while pending.
                # A request in another display session is unrelated.
                overlapping_binder_request = (
                    next((
                        match for match in SESSION_IPC_REQUEST_PATTERN.finditer(
                            data, binder_session_request.end(),
                            binder_subsession_match.start())
                        if match.group(1) == "IApplicationDisplayService"
                        and int(match.group(2)) in (100, 103)
                        and int(match.group(3), 16) == display_session
                    ), None)
                    if binder_subsession_match is not None else None
                )
                session_correlation["binder_subsession_request_ambiguous"] = (
                    overlapping_binder_request is not None)
                if overlapping_binder_request is not None:
                    binder_subsession_match = None
                binder_subsession = (
                    binder_subsession_match.start()
                    if binder_subsession_match is not None else None)
                binder_session = (
                    int(binder_subsession_match.group(2), 16)
                    if binder_subsession_match is not None else None)
                session_correlation["binder_subsession_parent_correlated"] = (
                    binder_subsession_match is not None)
            native_window_response = None
            if native_window_request is not None:
                # Scoped request regex groups service, command, session;
                # the historical unscoped regex captures only command.
                native_window_cmd = native_window_request.group(
                    2 if display_session is not None else 1)
                native_window_response_pattern = re.compile(
                    r"IPC FIRST-OCCURRENCE response \(compare with RustSwitch\) "
                    r"service=IApplicationDisplayService cmd="
                    + re.escape(native_window_cmd)
                    + r"\b"
                )
                if display_session is None:
                    response_match = regex_after(
                        native_window_response_pattern,
                        native_window_request.start())
                    other_response_session_observed = False
                else:
                    response_match, other_response_session_observed = scoped_response(
                        "IApplicationDisplayService", native_window_cmd,
                        native_window_request.start(), display_session)
                    session_correlation["native_window_response_session_correlated"] = (
                        response_match is not None)
                if response_match is None:
                    native_window_response_status = (
                        "other_session" if other_response_session_observed
                        else "no_response")
                else:
                    same_command_request_pattern = re.compile(
                        r'IPC request service="IApplicationDisplayService" cmd='
                        + re.escape(native_window_cmd)
                        + r'\b'
                    )
                    repeated_request = None
                    for candidate in same_command_request_pattern.finditer(
                            data, native_window_request.end(),
                            response_match.start()):
                        if display_session is None:
                            repeated_request = candidate
                            break
                        end = data.find("\n", candidate.start())
                        line = data[candidate.start():end if end >= 0 else len(data)]
                        marker = IPC_LINE_SESSION_PATTERN.search(line)
                        if marker is not None and int(marker.group(1), 16) == display_session:
                            repeated_request = candidate
                            break
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
                    ("display_service_binder_subsession_correlation_ambiguous"
                     if session_correlation["binder_subsession_request_ambiguous"]
                     else "display_service_binder_subsession_not_observed"),
                ))
            if native_window_request is not None and native_window_response is None:
                response_stage = {
                    "no_response": "native_window_request_response_not_observed",
                    "other_session": "native_window_response_other_session_unverified",
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
                if binder_session is None:
                    binder_transaction = regex_after(
                        binder_transaction_pattern, ready_after)
                else:
                    binder_transaction = session_request(
                        "IHOSBinderDriver", (0, 3), ready_after, binder_session)
                    session_correlation["binder_transaction_session_correlated"] = (
                        binder_transaction is not None)
                if binder_transaction is None:
                    stage = "display_and_native_window_ready_binder_transact_not_observed"
                else:
                    connect_match = regex_after(
                        IGBP_CONNECT_PATTERN, binder_transaction.start()
                    )
                    if connect_match is None:
                        stage = "binder_transact_igbp_connect_not_observed"
                    else:
                        # The debug log has no Binder transaction/request ID,
                        # and Connect has no session field. Any intervening Binder
                        # transaction (including one from another session) can
                        # own the next Connect, so ordering alone cannot establish
                        # attribution. Fail closed rather than borrowing it.
                        interleaved_binder_transaction = next(
                            binder_transaction_pattern.finditer(
                                data, binder_transaction.end(),
                                connect_match.start()),
                            None,
                        )
                        if interleaved_binder_transaction is not None:
                            stage = "binder_transaction_igbp_connect_correlation_ambiguous"
                        else:
                            connect_binder = connect_match.group(1)
                            # Binder IDs can be reused across a repeated Connect.
                            # Keep this Connect's evidence window separate from
                            # a later connection carrying the same ID.
                            next_same_binder_connect = next((
                                match for match in IGBP_CONNECT_PATTERN.finditer(
                                    data, connect_match.end())
                                if match.group(1) == connect_binder
                            ), None)
                            buffer_end = (
                                next_same_binder_connect.start()
                                if next_same_binder_connect is not None else len(data)
                            )
                            buffer_matches = list(
                                IGBP_REQUEST_BUFFER_PATTERN.finditer(
                                    data, connect_match.end(), buffer_end
                                )
                            )
                            request_buffer_match = next(
                                (match for match in buffer_matches
                                 if match.group(1) == connect_binder),
                                None,
                            )
                            if request_buffer_match is None:
                                if next_same_binder_connect is not None:
                                    stage = "igbp_connect_request_buffer_correlation_ambiguous"
                                elif buffer_matches:
                                    stage = "igbp_connect_request_buffer_binder_mismatch"
                                else:
                                    stage = "igbp_connect_request_buffer_not_observed"
                            else:
                                request_buffer = request_buffer_match.end()
                                # Do not borrow a queue/dequeue marker from a
                                # subsequent same-ID connection. The log does
                                # not expose a unique connection generation.
                                operation_end = (
                                    next_same_binder_connect.start()
                                    if next_same_binder_connect is not None
                                    else len(data)
                                )
                                operation_patterns = (
                                    ("queue", IGBP_QUEUE_BUFFER_PATTERN),
                                    ("dequeue_retry", IGBP_DEQUEUE_RETRY_PATTERN),
                                    ("dequeue_timeout", IGBP_DEQUEUE_TIMEOUT_PATTERN),
                                )
                                later_operations = []
                                other_binder_operations = []
                                for operation_kind, pattern in operation_patterns:
                                    for match in pattern.finditer(
                                            data, request_buffer, operation_end):
                                        item = (match.start(), operation_kind)
                                        if match.group(1) == connect_binder:
                                            later_operations.append(item)
                                        else:
                                            other_binder_operations.append(item)
                                if not later_operations:
                                    if next_same_binder_connect is not None:
                                        stage = (
                                            "igbp_request_buffer_reconnect_before_later_"
                                            "buffer_operation_unverified"
                                        )
                                    elif other_binder_operations:
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
        "schema": "nexium-stage73-display-ipc-path/v3",
        "observed_stage": stage,
        "observed_vi_service_variant": observed_vi_service_variant,
        "session_correlation_fields_observed": session_correlation_fields_observed,
        "vi_service_handle_return_correlated": session_correlation["vi_service_handle_return_correlated"],
        "vi_request_session_correlated": session_correlation["vi_request_session_correlated"],
        "vi_display_request_ambiguous": session_correlation["vi_display_request_ambiguous"],
        "display_subsession_parent_correlated": session_correlation["display_subsession_parent_correlated"],
        "display_binder_request_session_correlated": session_correlation["display_binder_request_session_correlated"],
        "binder_subsession_parent_correlated": session_correlation["binder_subsession_parent_correlated"],
        "binder_subsession_request_ambiguous": session_correlation["binder_subsession_request_ambiguous"],
        "native_window_request_session_correlated": session_correlation["native_window_request_session_correlated"],
        "native_window_response_session_correlated": session_correlation["native_window_response_session_correlated"],
        "binder_transaction_session_correlated": session_correlation["binder_transaction_session_correlated"],
        "expected_vi_display_ancestry_observed": ancestry is not None,
        "expected_vi_u_display_ancestry_observed": (
            ancestry is not None and ancestry[4] == "vi:u"
        ),
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
