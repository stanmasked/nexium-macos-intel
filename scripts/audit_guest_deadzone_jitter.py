#!/usr/bin/env python3
"""Stage52 fail-closed original SDL3 deadzone and libnx guest leak audit.

Host raw +/-1000 pulses MUST be seen in original InputSnapshot.raw_sticks
while processed InputSnapshot.sticks stays exactly neutral. Guest must
independently read all four processed NPad axes as zero throughout B hold.
Only boolean/count JSON evidence may be uploaded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_ab_chord import ordered
from audit_guest_hid_runtime import audit as audit_guest

GUEST = (
    "STAGE52_GUEST_JITTER_START",
    "STAGE52_GUEST_JITTER_B_NEUTRAL_FIRST",
    "STAGE52_GUEST_JITTER_B_NEUTRAL_PERSISTED",
    "STAGE52_GUEST_JITTER_RELEASE_NEUTRAL",
    "STAGE52_GUEST_JITTER_PASS",
)
HOST_PULSE = (
    "STAGE52_JITTER_RAW_PATTERN_A_SENT",
    "STAGE52_JITTER_CENTER_AFTER_A_SENT",
    "STAGE52_JITTER_RAW_PATTERN_B_SENT",
    "STAGE52_JITTER_CENTER_AFTER_B_SENT",
)
HOST_ORIGINAL = (
    "STAGE52_ORIGINAL_RAW_JITTER_A_PROCESSED_NEUTRAL",
    "STAGE52_ORIGINAL_JITTER_CENTER_AFTER_A",
    "STAGE52_ORIGINAL_RAW_JITTER_B_PROCESSED_NEUTRAL",
    "STAGE52_ORIGINAL_JITTER_CENTER_AFTER_B",
)
FAILURES = (
    "STAGE52_GUEST_ANALOG_DEADZONE_LEAK",
    "STAGE52_GUEST_UNEXPECTED_DIGITAL_BUTTON",
    "STAGE52_GUEST_B_HOLD_TOO_SHORT",
    "STAGE52_GUEST_JITTER_INCOMPLETE",
)
B_PRESS = "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"
B_RELEASE = "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"


def audit(report_dir: Path) -> dict:
    original = audit_guest(report_dir)
    log_dir = report_dir / "data-root" / "logs"
    files = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(files) != 1:
        raise ValueError("one isolated original guest FileLogger is required")
    guest = files[0].read_text(encoding="utf-8", errors="replace")
    host = (report_dir / "nexium-console.log").read_text(
        encoding="utf-8", errors="replace"
    )

    guest_order = ordered(guest, tuple("OutputDebugString: " + x for x in GUEST))
    failures = {
        marker.lower().replace("stage52_guest_", ""):
            ("OutputDebugString: " + marker) in guest
        for marker in FAILURES
    }
    original_pulse_order = ordered(host, HOST_PULSE)
    original_snapshot_order = ordered(host, HOST_ORIGINAL)
    virtual_axis_failed = "STAGE52_JITTER_VIRTUAL_AXIS_SET_FAILED" in host
    b_surrounds = (
        original["host_press_release_marker_order_valid"] and
        host.find(B_PRESS) < host.find(HOST_PULSE[0]) <
        host.find(HOST_PULSE[-1]) < host.find(B_RELEASE)
    )
    guest_boot = all((
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
        guest_boot and guest_order and not any(failures.values())
        and original_pulse_order and original_snapshot_order
        and not virtual_axis_failed and b_surrounds and npad_b
    )
    return {
        "schema": "nexium-stage52-guest-deadzone-jitter/v1",
        "same_process_guest_deadzone_jitter_passed": passed,
        "original_guest_boot_hid_svc_observed": guest_boot,
        "original_sdl3_all_four_axis_jitter_pulses_ordered": original_pulse_order,
        "original_raw_nonzero_processed_zero_all_four_axes_observed":
            original_snapshot_order,
        "original_host_b_hold_surrounds_jitter": b_surrounds,
        "guest_all_four_axes_neutral_through_b_hold": guest_order,
        "guest_leak_or_unexpected_marker_observed": any(failures.values()),
        "original_virtual_axis_failure_observed": virtual_axis_failed,
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
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["same_process_guest_deadzone_jitter_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE52_DEADZONE_JITTER_AUDIT_BLOCKED: " +
              type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
