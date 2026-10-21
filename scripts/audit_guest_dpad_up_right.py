#!/usr/bin/env python3
"""Stage43 fail-closed Intel libnx DPad Up/Right round-trip audit.

Requires coherent original FileLogger guest SVC messages, original serialized
HidState NPad words and synthetic SDL3 host markers in ONE NeXium process.
Never uploads raw logs, guest SD, screenshots, addresses or game data.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest, npad_samples
from audit_guest_ab_chord import ordered

B = 1 << 1
UP = 1 << 13
RIGHT = 1 << 14
MASK = B | UP | RIGHT
GUEST = (
    "STAGE43_GUEST_DPAD_PROBE_START",
    "STAGE43_GUEST_B_ONLY_FIRST",
    "STAGE43_GUEST_B_AND_UP",
    "STAGE43_GUEST_B_ONLY_AFTER_UP",
    "STAGE43_GUEST_B_AND_RIGHT",
    "STAGE43_GUEST_B_ONLY_AFTER_RIGHT",
    "STAGE43_GUEST_ALL_RELEASED",
    "STAGE43_GUEST_DPAD_PASS",
)
HOST_DPAD = (
    "STAGE43_DPAD_UP_PRESS_SENT",
    "STAGE43_DPAD_UP_RELEASE_SENT",
    "STAGE43_DPAD_RIGHT_PRESS_SENT",
    "STAGE43_DPAD_RIGHT_RELEASE_SENT",
)
HOST_B = (
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
    "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
)


def npad_direction_sequence(samples: list[list[int]]) -> bool:
    required = (B, B | UP, B, B | RIGHT, B, 0)
    step = 0
    for sample in samples:
        if not sample:
            continue
        state = 0
        for buttons in sample:
            state |= buttons
        # An A press, opposite direction, or mixed Up+Right must not pass.
        if state & ~MASK:
            return False
        if state == required[step]:
            step += 1
            if step == len(required):
                return True
    return False


def audit(report_dir: Path) -> dict:
    source = audit_guest(report_dir)
    logs = report_dir / "data-root" / "logs"
    paths = sorted(logs.glob("nexium-*.log")) if logs.is_dir() else []
    if len(paths) != 1:
        raise ValueError("Stage43 requires one isolated original NeXium FileLogger")
    guest_text = paths[0].read_text(encoding="utf-8", errors="replace")
    host_text = (report_dir / "nexium-console.log").read_text(encoding="utf-8", errors="replace")

    guest_markers = tuple("OutputDebugString: " + m for m in GUEST)
    guest_order = ordered(guest_text, guest_markers)
    guest_no_failure = not any(
        ("OutputDebugString: " + m) in guest_text
        for m in ("STAGE43_GUEST_DPAD_INCOMPLETE", "STAGE43_GUEST_DPAD_UNEXPECTED_BUTTON")
    )
    host_order = ordered(host_text, (HOST_B[0],) + HOST_DPAD + (HOST_B[1],))
    samples = npad_samples(guest_text)
    traced = npad_direction_sequence(samples)
    guest_boot_ok = all((
        source["nro_autoload_observed"],
        source["guest_boot_started_observed"],
        source["guest_boot_context_ready_observed"],
        source["guest_hid_map_svc_observed"],
        source["guest_hid_map_success_marker_observed"],
        source["guest_output_debug_svc_observed"],
        source["probe_process_outcome_acceptable"],
        not source["guest_boot_failed_observed"],
    ))
    passed = bool(guest_boot_ok and guest_order and guest_no_failure
                  and host_order and traced)
    return {
        "schema": "nexium-stage43-guest-dpad-up-right/v1",
        "same_process_guest_dpad_readback_passed": passed,
        "guest_boot_and_hid_map_observed": guest_boot_ok,
        "guest_dpad_sequence_observed": guest_order,
        "guest_incomplete_or_unexpected_button_observed": not guest_no_failure,
        "host_dpad_pulses_nested_inside_b_observed": host_order,
        "original_npad_b_up_b_right_b_neutral_observed": traced,
        "original_npad_serialized_sample_count": len(samples),
        "guest_gameplay_verified": False,
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
        return 0 if receipt["same_process_guest_dpad_readback_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE43_GUEST_DPAD_AUDIT_BLOCKED: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
