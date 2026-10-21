#!/usr/bin/env python3
"""Stage40: fail-closed audit of guest-visible libnx B press/release.

Raw emulator logs and snapshots stay local to the runner. The emitted JSON
contains only booleans, counts, and the probe process outcome.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

NPAD_TRACE = re.compile(r"\[hid-publish\].*?npad=\[([0-9a-fA-FxX,\s]+)\]")
B_BIT = 1 << 1

GUEST_MARKERS = (
    "STAGE40_GUEST_HID_PROBE_START",
    "STAGE40_GUEST_HID_B_DOWN",
    "STAGE40_GUEST_HID_B_UP",
    "STAGE40_GUEST_HID_PRESS_RELEASE_PASS",
)
HOST_MARKERS = (
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
)


def npad_samples(console: str) -> list[list[int]]:
    samples = []
    for line in console.splitlines():
        match = NPAD_TRACE.search(line)
        if not match:
            continue
        try:
            samples.append([int(value.strip(), 16)
                            for value in match.group(1).split(",")
                            if value.strip()])
        except ValueError:
            continue
    return samples


def audit(report_dir: Path) -> dict:
    report_path = report_dir / "smoke_result.json"
    console_path = report_dir / "nexium-console.log"
    if not report_path.is_file() or not console_path.is_file():
        raise ValueError("missing NRO smoke receipt or local emulator console log")
    smoke = json.loads(report_path.read_text(encoding="utf-8"))
    console = console_path.read_text(encoding="utf-8", errors="replace")

    # NeXium's pinned FileLogger writes guest SVC OutputDebugString records
    # to NEXIUM_DATA_ROOT/logs, not necessarily to the captured stdout/stderr.
    # The smoke harness sets NEXIUM_DATA_ROOT to report_dir/data-root, so only
    # read logs from this isolated run; never search a user-wide log directory.
    file_logger_dir = report_dir / "data-root" / "logs"
    file_logger_paths = sorted(file_logger_dir.glob("nexium-*.log")) if file_logger_dir.is_dir() else []
    file_logger_chunks = []
    for log_path in file_logger_paths:
        try:
            file_logger_chunks.append(log_path.read_text(encoding="utf-8", errors="replace"))
        except OSError as error:
            raise ValueError("could not read isolated NeXium file logger output") from error
    evidence = "\n".join([console, *file_logger_chunks])

    guest = {marker: marker in evidence for marker in GUEST_MARKERS}
    host = {marker: marker in evidence for marker in HOST_MARKERS}
    samples = npad_samples(evidence)
    pressed = [i for i, values in enumerate(samples) if any(v & B_BIT for v in values)]
    released_after = any(
        all((value & B_BIT) == 0 for value in samples[j])
        for i in pressed for j in range(i + 1, len(samples))
    )
    mapping_call = "svcMapSharedMemory" in evidence
    hid_mapping_success = "recognized as HID shared memory" in evidence
    process_status = smoke.get("status", "missing")
    process_outcome_acceptable = (
        process_status == "exited_zero_unverified" and smoke.get("exit_code") == 0
    ) or process_status == "timeout_alive_unverified"
    guest_down_at = evidence.find(GUEST_MARKERS[1])
    guest_up_at = evidence.find(GUEST_MARKERS[2])
    guest_pass_at = evidence.find(GUEST_MARKERS[3])
    guest_edges_ordered = guest_down_at >= 0 and guest_up_at > guest_down_at
    guest_pass_after_edges = guest_edges_ordered and guest_pass_at > guest_up_at
    host_press_at = evidence.find(HOST_MARKERS[0])
    host_release_at = evidence.find(HOST_MARKERS[1])
    host_edges_ordered = host_press_at >= 0 and host_release_at > host_press_at

    result = {
        "schema": "nexium-stage40-guest-npad-readback/v1",
        "same_process_guest_input_roundtrip_passed": bool(
            guest_pass_after_edges and host_edges_ordered and mapping_call
            and hid_mapping_success and process_outcome_acceptable
        ),
        "guest_libnx_b_down_observed": guest[GUEST_MARKERS[1]],
        "guest_libnx_b_up_observed_after_down_marker": guest_edges_ordered,
        "guest_probe_start_observed": guest[GUEST_MARKERS[0]],
        "guest_probe_pass_marker_observed": guest[GUEST_MARKERS[3]],
        "host_original_hid_b_press_observed": host[HOST_MARKERS[0]],
        "host_original_hid_b_release_observed": host[HOST_MARKERS[1]],
        "guest_hid_map_svc_observed": mapping_call,
        "guest_hid_map_success_marker_observed": hid_mapping_success,
        "file_logger_log_count": len(file_logger_paths),
        "serialized_npad_samples": len(samples),
        "serialized_npad_b_press_samples": len(pressed),
        "serialized_npad_b_release_after_press_observed": bool(released_after),
        "serialized_npad_trace_roundtrip_observed": bool(pressed and released_after),
        "guest_press_release_marker_order_valid": bool(guest_pass_after_edges),
        "host_press_release_marker_order_valid": bool(host_edges_ordered),
        "probe_process_outcome_acceptable": bool(process_outcome_acceptable),
        "probe_process_status": process_status,
        "gameplay_verified": False,
        "physical_controller_verified": False,
        "real_switch_verified": False,
        "raw_console_uploaded": False,
        "frame_images_uploaded": False,
    }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0 if result["same_process_guest_input_roundtrip_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE40_GUEST_HID_RUNTIME_AUDIT_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
