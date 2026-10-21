#!/usr/bin/env python3
"""Stage53 source-authentic dual-stick deadzone below/above threshold audit.

Original SDL3 pulses raw 3000 (< 0.12*32768) and 6000 (> threshold)
on four axes. Host original InputSnapshot MUST show below suppression,
above signed samples, and neutral transitions. Genuine libnx guest
samples both axes in original NPad without private memory injection.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest
from audit_guest_ab_chord import ordered

GUEST = (
    "STAGE53_GUEST_THRESHOLD_START",
    "STAGE53_GUEST_B_BELOW_THRESHOLD_NEUTRAL",
    "STAGE53_GUEST_ABOVE_A_ALL_FOUR_AXES",
    "STAGE53_GUEST_CENTER_AFTER_A",
    "STAGE53_GUEST_ABOVE_B_REVERSED_ALL_AXES",
    "STAGE53_GUEST_CENTER_AFTER_B",
    "STAGE53_GUEST_RELEASE_NEUTRAL",
    "STAGE53_GUEST_THRESHOLD_PASS",
)
HOST_PULSE = (
    "STAGE53_BELOW_A_SENT",
    "STAGE53_ABOVE_A_SENT",
    "STAGE53_CENTER_AFTER_A_SENT",
    "STAGE53_BELOW_B_SENT",
    "STAGE53_ABOVE_B_SENT",
    "STAGE53_CENTER_AFTER_B_SENT",
)
HOST_SOURCE = (
    "STAGE53_ORIGINAL_BELOW_A_SUPPRESSED",
    "STAGE53_ORIGINAL_ABOVE_A_PASSED",
    "STAGE53_ORIGINAL_CENTER_AFTER_A",
    "STAGE53_ORIGINAL_BELOW_B_SUPPRESSED",
    "STAGE53_ORIGINAL_ABOVE_B_PASSED",
    "STAGE53_ORIGINAL_CENTER_AFTER_B",
)
B_PRESS = "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"
B_RELEASE = "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"
FAILURES = (
    "STAGE53_GUEST_UNEXPECTED_DIGITAL_BUTTON",
    "STAGE53_GUEST_THRESHOLD_INCOMPLETE",
)

def audit(report_dir: Path) -> dict:
    original = audit_guest(report_dir)
    log_dir = report_dir / "data-root" / "logs"
    paths = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(paths) != 1:
        raise ValueError("one isolated original guest FileLogger required")
    guest = paths[0].read_text(encoding="utf-8", errors="replace")
    host = (report_dir / "nexium-console.log").read_text(
        encoding="utf-8", errors="replace"
    )
    guest_order = ordered(guest, tuple("OutputDebugString: " + m for m in GUEST))
    guest_failed = any("OutputDebugString: " + x in guest for x in FAILURES)
    host_order = ordered(host, HOST_PULSE)
    source_order = ordered(host, HOST_SOURCE)
    host_axis_fail = "STAGE53_THRESHOLD_VIRTUAL_AXIS_FAILED" in host
    b_surrounds = bool(
        original["host_press_release_marker_order_valid"]
        and host.find(B_PRESS) < host.find(HOST_PULSE[0])
        < host.find(HOST_PULSE[-1]) < host.find(B_RELEASE)
    )
    boot = all((
        original["nro_autoload_observed"],
        original["guest_boot_started_observed"],
        original["guest_boot_context_ready_observed"],
        original["guest_hid_map_svc_observed"],
        original["guest_hid_map_success_marker_observed"],
        original["guest_output_debug_svc_observed"],
        original["probe_process_outcome_acceptable"],
        not original["guest_boot_failed_observed"],
    ))
    npad = original["serialized_npad_trace_roundtrip_observed"]
    passed = bool(
        boot and npad and guest_order and not guest_failed
        and host_order and source_order and not host_axis_fail
        and b_surrounds
    )
    return {
        "schema": "nexium-stage53-guest-deadzone-threshold/v1",
        "same_process_guest_deadzone_threshold_passed": passed,
        "original_guest_hid_map_and_svc_observed": boot,
        "original_host_b_surrounds_below_above_pulses": b_surrounds,
        "original_host_sdl3_below_above_pulses_ordered": host_order,
        "original_source_below_zero_above_signed_all_four_axes": source_order,
        "guest_above_threshold_both_sticks_in_order": guest_order,
        "guest_incomplete_or_unexpected_button_observed": guest_failed,
        "original_sdl3_virtual_set_failure_observed": host_axis_fail,
        "original_npad_b_pressed_then_released": npad,
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
        result = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["same_process_guest_deadzone_threshold_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE53_THRESHOLD_AUDIT_BLOCKED: " + type(error).__name__, file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
