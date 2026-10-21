#!/usr/bin/env python3
"""Stage42: authentic source-bound guest libnx A+B chord audit.

Requires original host B, the separately pulsed synthetic SDL EAST/A,
serialised NPad button states, and guest SVC readback in the same Intel run.
Raw FileLogger/console files never leave the CI runner.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest, npad_samples

GUEST = (
    "STAGE42_GUEST_AB_PROBE_START",
    "STAGE42_GUEST_B_ONLY_FIRST",
    "STAGE42_GUEST_A_AND_B",
    "STAGE42_GUEST_B_ONLY_AFTER_A",
    "STAGE42_GUEST_BOTH_RELEASED",
    "STAGE42_GUEST_AB_CHORD_PASS",
)
HOST_A = ("STAGE42_VIRTUAL_A_PRESS_SENT", "STAGE42_VIRTUAL_A_RELEASE_SENT")


def ordered(text: str, markers: tuple[str, ...]) -> bool:
    offset = 0
    for marker in markers:
        location = text.find(marker, offset)
        if location < 0:
            return False
        offset = location + len(marker)
    return True


def npad_chord_order(samples: list[list[int]]) -> bool:
    # npad=[...] gives buttons of each layout for one sample. All active
    # layouts report the same physical buttons; OR avoids picking a layout.
    values = []
    for sample in samples:
        combined = 0
        for v in sample:
            combined |= (v & 3)
        values.append(combined)
    expected = [2, 3, 2, 0]  # B, A+B, B, neutral
    i = 0
    for value in values:
        if value == expected[i]:
            i += 1
            if i == len(expected):
                return True
    return False


def audit(report_dir: Path) -> dict:
    source = audit_guest(report_dir)
    logger_dir = report_dir / "data-root" / "logs"
    paths = sorted(logger_dir.glob("nexium-*.log")) if logger_dir.is_dir() else []
    if len(paths) != 1:
        raise ValueError("exactly one isolated original FileLogger is required")
    file_log = paths[0].read_text(encoding="utf-8", errors="replace")
    console = (report_dir / "nexium-console.log").read_text(encoding="utf-8", errors="replace")

    markers = tuple("OutputDebugString: " + x for x in GUEST)
    guest_sequence = ordered(file_log, markers)
    incomplete = "OutputDebugString: STAGE42_GUEST_AB_CHORD_INCOMPLETE" in file_log
    host_a_sequence = ordered(console, HOST_A)
    host_b_sequence = source["host_press_release_marker_order_valid"]
    host_press = console.find("STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE")
    host_release = console.find("STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE")
    host_a_press = console.find(HOST_A[0])
    host_a_release = console.find(HOST_A[1])
    host_chord_nesting = (
        host_b_sequence and host_a_sequence
        and host_press < host_a_press < host_a_release < host_release
    )

    samples = npad_samples(file_log)
    traced = npad_chord_order(samples)
    guest_boot = all((
        source["nro_autoload_observed"],
        source["guest_boot_started_observed"],
        source["guest_boot_context_ready_observed"],
        source["guest_hid_map_svc_observed"],
        source["guest_hid_map_success_marker_observed"],
        source["guest_output_debug_svc_observed"],
        not source["guest_boot_failed_observed"],
        source["probe_process_outcome_acceptable"],
    ))
    passed = bool(guest_boot and guest_sequence and not incomplete
                  and host_chord_nesting and traced)

    return {
        "schema": "nexium-stage42-guest-ab-chord/v1",
        "same_process_guest_ab_chord_passed": passed,
        "guest_boot_and_hid_map_observed": guest_boot,
        "guest_ab_chord_sequence_observed": guest_sequence,
        "guest_ab_incomplete_observed": incomplete,
        "host_a_press_release_observed": host_a_sequence,
        "host_b_press_release_observed": host_b_sequence,
        "host_a_nested_within_b_observed": host_chord_nesting,
        "original_npad_b_ab_b_neutral_order_observed": traced,
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
        args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["same_process_guest_ab_chord_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE42_AB_CHORD_AUDIT_BLOCKED: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
