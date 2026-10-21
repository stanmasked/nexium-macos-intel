#!/usr/bin/env python3
"""Stage44: real guest libnx analog LeftX readback audit, source-channel strict.

Original SDL3 virtual axis emits host markers; original InputSnapshot sees
the signed values after SDL polling; guest libnx padGetStickPos reads actual
mapped NPad. B and original publication ensure the same-process HID path.
Only sanitized booleans/counts leave CI, never native logs/guest values.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest
from audit_guest_ab_chord import ordered

GUEST_MARKERS = (
    "STAGE44_GUEST_STICK_X_START",
    "STAGE44_GUEST_B_NEUTRAL_FIRST",
    "STAGE44_GUEST_LEFT_X_NEGATIVE",
    "STAGE44_GUEST_LEFT_X_CENTER_AFTER_NEGATIVE",
    "STAGE44_GUEST_LEFT_X_POSITIVE",
    "STAGE44_GUEST_LEFT_X_CENTER_AFTER_POSITIVE",
    "STAGE44_GUEST_B_RELEASED_NEUTRAL",
    "STAGE44_GUEST_STICK_X_PASS",
)
HOST_AXIS_MARKERS = (
    "STAGE44_LEFTX_NEGATIVE_SENT",
    "STAGE44_LEFTX_NEUTRAL_AFTER_NEGATIVE_SENT",
    "STAGE44_LEFTX_POSITIVE_SENT",
    "STAGE44_LEFTX_NEUTRAL_AFTER_POSITIVE_SENT",
)
HOST_SNAPSHOT_MARKERS = (
    "STAGE44_ORIGINAL_SNAPSHOT_LEFTX_NEGATIVE",
    "STAGE44_ORIGINAL_SNAPSHOT_LEFTX_CENTER_AFTER_NEGATIVE",
    "STAGE44_ORIGINAL_SNAPSHOT_LEFTX_POSITIVE",
    "STAGE44_ORIGINAL_SNAPSHOT_LEFTX_CENTER_AFTER_POSITIVE",
)
HOST_B = (
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
)


def audit(report_dir: Path) -> dict:
    common = audit_guest(report_dir)
    logs_dir = report_dir / "data-root" / "logs"
    logs = sorted(logs_dir.glob("nexium-*.log")) if logs_dir.is_dir() else []
    if len(logs) != 1:
        raise ValueError("Stage44 requires one original isolated guest FileLogger")
    guest_log = logs[0].read_text(encoding="utf-8", errors="replace")
    console = (report_dir / "nexium-console.log").read_text(encoding="utf-8", errors="replace")

    guest_order = ordered(guest_log, tuple("OutputDebugString: " + m for m in GUEST_MARKERS))
    failed_guest = any(
        "OutputDebugString: " + m in guest_log
        for m in ("STAGE44_GUEST_STICK_X_INCOMPLETE", "STAGE44_GUEST_UNEXPECTED_DIGITAL_BUTTON")
    )
    host_axis = ordered(console, HOST_AXIS_MARKERS)
    original_snapshot = ordered(console, HOST_SNAPSHOT_MARKERS)
    b_down_at, b_up_at = (console.find(marker) for marker in HOST_B)
    axis_start = console.find(HOST_AXIS_MARKERS[0])
    axis_end = console.find(HOST_AXIS_MARKERS[-1])
    b_surrounds_axes = common["host_press_release_marker_order_valid"] and (
        b_down_at < axis_start < axis_end < b_up_at
    )
    boot = all((
        common["nro_autoload_observed"],
        common["guest_boot_started_observed"],
        common["guest_boot_context_ready_observed"],
        common["guest_hid_map_svc_observed"],
        common["guest_hid_map_success_marker_observed"],
        common["guest_output_debug_svc_observed"],
        common["probe_process_outcome_acceptable"],
        not common["guest_boot_failed_observed"],
    ))
    published_b = common["serialized_npad_trace_roundtrip_observed"]
    passed = bool(boot and guest_order and not failed_guest and host_axis
                  and original_snapshot and b_surrounds_axes and published_b)

    return {
        "schema": "nexium-stage44-guest-left-stick-x/v1",
        "same_process_guest_left_x_roundtrip_passed": passed,
        "guest_boot_and_hid_mapping_observed": boot,
        "guest_analog_sequence_observed": guest_order,
        "guest_analog_incomplete_or_spurious_button_observed": failed_guest,
        "synthetic_left_x_axis_pulses_ordered": host_axis,
        "original_sdl3_input_snapshot_left_x_ordered": original_snapshot,
        "original_host_b_surrounds_axis_pulses": b_surrounds_axes,
        "original_npad_b_published_and_released": published_b,
        "original_npad_serialized_sample_count": common["serialized_npad_samples"],
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
        receipt = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["same_process_guest_left_x_roundtrip_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print("STAGE44_LEFT_X_AUDIT_BLOCKED: " + type(err).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
