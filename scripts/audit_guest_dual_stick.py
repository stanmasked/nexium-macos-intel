#!/usr/bin/env python3
"""Stage48: audit true simultaneous left+right stick states in Intel guest libnx.

Requires original SDL3 host virtual pulse markers, original same-snapshot
four-axis read-only observer, and genuine guest SVC markers from the isolated
original FileLogger with HID mapping and real original NPad B lifecycle.
No guest memory or raw logs are published in its sanitized JSON receipt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_ab_chord import ordered
from audit_guest_hid_runtime import audit as audit_guest

GUEST = (
    "STAGE48_GUEST_DUAL_STICK_START",
    "STAGE48_GUEST_B_AND_ALL_NEUTRAL",
    "STAGE48_GUEST_B_AND_DUAL_DIAGONAL_A",
    "STAGE48_GUEST_DUAL_CENTER_AFTER_A",
    "STAGE48_GUEST_B_AND_DUAL_DIAGONAL_B",
    "STAGE48_GUEST_DUAL_CENTER_AFTER_B",
    "STAGE48_GUEST_ALL_RELEASED_AND_NEUTRAL",
    "STAGE48_GUEST_DUAL_STICK_PASS",
)
HOST_AXIS = (
    "STAGE48_DUAL_DIAGONAL_A_SENT",
    "STAGE48_DUAL_CENTER_AFTER_A_SENT",
    "STAGE48_DUAL_DIAGONAL_B_SENT",
    "STAGE48_DUAL_CENTER_AFTER_B_SENT",
)
HOST_SNAPSHOT = (
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_DIAGONAL_A",
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_CENTER_AFTER_A",
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_DIAGONAL_B",
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_CENTER_AFTER_B",
)
B_PRESS = "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"
B_RELEASE = "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"


def audit(report_dir: Path) -> dict:
    original = audit_guest(report_dir)
    log_dir = report_dir / "data-root" / "logs"
    logs = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(logs) != 1:
        raise ValueError("exactly one isolated original FileLogger required")

    guest_text = logs[0].read_text(encoding="utf-8", errors="replace")
    host_text = (report_dir / "nexium-console.log").read_text(
        encoding="utf-8", errors="replace"
    )
    guest_order = ordered(
        guest_text, tuple("OutputDebugString: " + m for m in GUEST)
    )
    guest_incomplete = (
        "OutputDebugString: STAGE48_GUEST_DUAL_STICK_INCOMPLETE" in guest_text
    )
    guest_wrong_button = (
        "OutputDebugString: STAGE48_GUEST_UNEXPECTED_DIGITAL_BUTTON" in guest_text
    )
    axis_order = ordered(host_text, HOST_AXIS)
    snapshot_order = ordered(host_text, HOST_SNAPSHOT)
    axis_failed = "STAGE48_DUAL_AXIS_SET_FAILED" in host_text
    b_surrounds = (
        original["host_press_release_marker_order_valid"]
        and host_text.find(B_PRESS) < host_text.find(HOST_AXIS[0])
        < host_text.find(HOST_AXIS[-1]) < host_text.find(B_RELEASE)
    )
    guest_mapped = all((
        original["nro_autoload_observed"],
        original["guest_boot_started_observed"],
        original["guest_boot_context_ready_observed"],
        original["guest_hid_map_svc_observed"],
        original["guest_hid_map_success_marker_observed"],
        original["guest_output_debug_svc_observed"],
        original["probe_process_outcome_acceptable"],
        not original["guest_boot_failed_observed"],
    ))
    npad_b = original["serialized_npad_trace_roundtrip_observed"]
    passed = bool(
        guest_mapped and guest_order and not guest_incomplete
        and not guest_wrong_button and axis_order and not axis_failed
        and snapshot_order and b_surrounds and npad_b
    )
    return {
        "schema": "nexium-stage48-guest-dual-stick-combined/v1",
        "same_process_guest_dual_stick_passed": passed,
        "original_guest_boot_and_hid_map_observed": guest_mapped,
        "guest_simultaneous_four_axis_phases_in_order": guest_order,
        "original_sdl3_combined_axis_pulses_ordered": axis_order,
        "original_single_input_snapshot_diagonal_phases_in_order": snapshot_order,
        "original_b_hold_surrounds_both_diagonals": b_surrounds,
        "original_npad_b_published_and_released": npad_b,
        "original_npad_serialized_sample_count": original["serialized_npad_samples"],
        "original_virtual_axis_failed": axis_failed,
        "guest_incomplete_marker_observed": guest_incomplete,
        "guest_unexpected_digital_button_observed": guest_wrong_button,
        "gameplay_verified": False,
        "physical_controller_verified": False,
        "real_switch_verified": False,
        "raw_logs_uploaded": False,
        "frame_images_uploaded": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["same_process_guest_dual_stick_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE48_DUAL_STICK_AUDIT_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
