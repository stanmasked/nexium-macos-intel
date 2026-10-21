#!/usr/bin/env python3
"""Stage50 authentic mixed DPad + dual analog libnx source-bound audit.

Requires original host SDL3 virtual DPad AND dual-stick pulse observations,
original four-axis InputSnapshot observations, original serialized NPad
direction mask states, and guest libnx SVC markers from isolated FileLogger.
Publishes sanitized booleans/counts only, never raw memory/logs/images.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_ab_chord import ordered
from audit_guest_dpad_up_right import B, UP, RIGHT, npad_direction_sequence
from audit_guest_hid_runtime import audit as audit_guest, npad_samples

GUEST = (
    "STAGE50_GUEST_MIXED_START",
    "STAGE50_GUEST_B_ONLY_ALL_NEUTRAL",
    "STAGE50_GUEST_B_UP_AND_DUAL_DIAGONAL_A",
    "STAGE50_GUEST_B_ONLY_CENTER_AFTER_A",
    "STAGE50_GUEST_B_RIGHT_AND_DUAL_DIAGONAL_B",
    "STAGE50_GUEST_B_ONLY_CENTER_AFTER_B",
    "STAGE50_GUEST_ALL_RELEASED_NEUTRAL",
    "STAGE50_GUEST_MIXED_PASS",
)
HOST_MIXED = (
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
    "STAGE43_DPAD_UP_PRESS_SENT",
    "STAGE48_DUAL_DIAGONAL_A_SENT",
    "STAGE43_DPAD_UP_RELEASE_SENT",
    "STAGE48_DUAL_CENTER_AFTER_A_SENT",
    "STAGE43_DPAD_RIGHT_PRESS_SENT",
    "STAGE48_DUAL_DIAGONAL_B_SENT",
    "STAGE43_DPAD_RIGHT_RELEASE_SENT",
    "STAGE48_DUAL_CENTER_AFTER_B_SENT",
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
)
SOURCE_SNAPSHOT = (
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_DIAGONAL_A",
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_CENTER_AFTER_A",
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_DIAGONAL_B",
    "STAGE48_ORIGINAL_SNAPSHOT_DUAL_CENTER_AFTER_B",
)
GUEST_FAILURES = (
    "STAGE50_GUEST_MIXED_INCOMPLETE",
    "STAGE50_GUEST_SPURIOUS_OR_OVERLAPPED_DIGITAL",
)


def audit(report_dir: Path) -> dict:
    source = audit_guest(report_dir)
    log_dir = report_dir / "data-root" / "logs"
    files = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(files) != 1:
        raise ValueError("one isolated original guest FileLogger required")
    guest_text = files[0].read_text(encoding="utf-8", errors="replace")
    host_text = (report_dir / "nexium-console.log").read_text(
        encoding="utf-8", errors="replace"
    )
    guest_order = ordered(guest_text, tuple("OutputDebugString: " + m for m in GUEST))
    guest_failed = any(
        "OutputDebugString: " + marker in guest_text
        for marker in GUEST_FAILURES
    )
    host_mixed = ordered(host_text, HOST_MIXED)
    snapshot_order = ordered(host_text, SOURCE_SNAPSHOT)
    virtual_fail = any(marker in host_text for marker in (
        "STAGE43_DPAD_UP_SET_FAILED",
        "STAGE43_DPAD_RIGHT_SET_FAILED",
        "STAGE48_DUAL_AXIS_SET_FAILED",
    ))
    samples = npad_samples(guest_text)
    npad_order = npad_direction_sequence(samples)
    # No spurious digital button bits in any original published state.
    states = [0 if not sample else sample[0] for sample in samples]
    for sample_idx, sample in enumerate(samples):
        if sample:
            state = 0
            for value in sample:
                state |= value
            states[sample_idx] = state
    unexpected_npad = any(state & ~(B | UP | RIGHT) for state in states)
    known = all((
        source["nro_autoload_observed"],
        source["guest_boot_started_observed"],
        source["guest_boot_context_ready_observed"],
        source["guest_hid_map_svc_observed"],
        source["guest_hid_map_success_marker_observed"],
        source["guest_output_debug_svc_observed"],
        source["probe_process_outcome_acceptable"],
        not source["guest_boot_failed_observed"],
    ))
    passed = bool(known and guest_order and not guest_failed and host_mixed
                  and snapshot_order and not virtual_fail and npad_order
                  and not unexpected_npad)

    return {
        "schema": "nexium-stage50-guest-mixed-dpad-dual-stick/v1",
        "same_process_guest_mixed_digital_analog_passed": passed,
        "original_guest_boot_and_hid_mapping_observed": known,
        "guest_mixed_digital_and_simultaneous_analog_phases_ordered": guest_order,
        "original_host_dpad_and_four_axis_pulses_interleaved": host_mixed,
        "original_single_snapshot_both_diagonals_in_order": snapshot_order,
        "original_npad_b_up_b_right_b_neutral_observed": npad_order,
        "original_npad_serialized_sample_count": len(samples),
        "original_npad_unexpected_button_bits_observed": unexpected_npad,
        "guest_incomplete_or_spurious_marker_observed": guest_failed,
        "host_sdl3_virtual_input_call_failure_observed": virtual_fail,
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
        return 0 if receipt["same_process_guest_mixed_digital_analog_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE50_MIXED_DPAD_DUAL_STICK_AUDIT_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
