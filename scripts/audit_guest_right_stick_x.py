#!/usr/bin/env python3
"""Stage46: strict source-bound Intel guest libnx right-stick X readback audit.

Checks authentic guest SVC markers, original host SDL axis, original read-only
InputSnapshot, and real NPad B publication in one process. Uploads booleans
and sample counts only; never native FileLogger or guest memory contents.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest
from audit_guest_ab_chord import ordered

GUEST = (
    "STAGE46_GUEST_RIGHT_X_START",
    "STAGE46_GUEST_B_NEUTRAL_FIRST",
    "STAGE46_GUEST_RIGHT_X_NEGATIVE",
    "STAGE46_GUEST_RIGHT_X_CENTER_AFTER_NEGATIVE",
    "STAGE46_GUEST_RIGHT_X_POSITIVE",
    "STAGE46_GUEST_RIGHT_X_CENTER_AFTER_POSITIVE",
    "STAGE46_GUEST_B_RELEASED_NEUTRAL",
    "STAGE46_GUEST_RIGHT_X_PASS",
)
HOST_AXIS = (
    "STAGE46_RIGHTX_NEGATIVE_SENT",
    "STAGE46_RIGHTX_CENTER_AFTER_NEGATIVE_SENT",
    "STAGE46_RIGHTX_POSITIVE_SENT",
    "STAGE46_RIGHTX_CENTER_AFTER_POSITIVE_SENT",
)
HOST_SNAPSHOT = (
    "STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_NEGATIVE",
    "STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_CENTER_AFTER_NEGATIVE",
    "STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_POSITIVE",
    "STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_CENTER_AFTER_POSITIVE",
)
B_PRESS = "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"
B_RELEASE = "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"


def audit(report_dir: Path) -> dict:
    original = audit_guest(report_dir)
    log_dir = report_dir / "data-root" / "logs"
    logger_files = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(logger_files) != 1:
        raise ValueError("exactly one genuine original FileLogger is required")
    guest = logger_files[0].read_text(encoding="utf-8", errors="replace")
    host = (report_dir / "nexium-console.log").read_text(encoding="utf-8", errors="replace")

    guest_order = ordered(guest, tuple("OutputDebugString: " + value for value in GUEST))
    incomplete = "OutputDebugString: STAGE46_GUEST_RIGHT_X_INCOMPLETE" in guest
    wrong_button = "OutputDebugString: STAGE46_GUEST_UNEXPECTED_DIGITAL_BUTTON" in guest
    axis_order = ordered(host, HOST_AXIS)
    snapshot_order = ordered(host, HOST_SNAPSHOT)

    b_holds = (
        original["host_press_release_marker_order_valid"]
        and host.find(B_PRESS) < host.find(HOST_AXIS[0])
        < host.find(HOST_AXIS[-1]) < host.find(B_RELEASE)
    )
    authentic_guest = all((
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
    passed = bool(authentic_guest and guest_order and not incomplete
                  and not wrong_button and axis_order and snapshot_order
                  and b_holds and npad_b)

    return {
        "schema": "nexium-stage46-guest-right-stick-x/v1",
        "same_process_guest_right_x_roundtrip_passed": passed,
        "guest_boot_and_hid_map_observed": authentic_guest,
        "guest_right_x_signed_sequence_observed": guest_order,
        "guest_incomplete_marker_observed": incomplete,
        "guest_unexpected_button_marker_observed": wrong_button,
        "original_host_right_x_axis_pulses_ordered": axis_order,
        "original_input_snapshot_right_x_ordered": snapshot_order,
        "original_host_b_surrounds_right_x": b_holds,
        "original_npad_b_published_and_released": npad_b,
        "original_npad_serialized_sample_count": original["serialized_npad_samples"],
        "physical_controller_verified": False,
        "gameplay_verified": False,
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
        report = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        return 0 if report["same_process_guest_right_x_roundtrip_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE46_GUEST_RIGHT_X_AUDIT_BLOCKED: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
