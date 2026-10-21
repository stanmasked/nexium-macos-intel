#!/usr/bin/env python3
"""Source-bound Stage47 libnx guest right-Y audit (positive Switch up)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest
from audit_guest_ab_chord import ordered

GUEST = (
    "STAGE47_GUEST_RIGHT_Y_START",
    "STAGE47_GUEST_B_NEUTRAL_FIRST",
    "STAGE47_GUEST_RIGHT_Y_UP_POSITIVE",
    "STAGE47_GUEST_RIGHT_Y_CENTER_AFTER_UP",
    "STAGE47_GUEST_RIGHT_Y_DOWN_NEGATIVE",
    "STAGE47_GUEST_RIGHT_Y_CENTER_AFTER_DOWN",
    "STAGE47_GUEST_B_RELEASED_NEUTRAL",
    "STAGE47_GUEST_RIGHT_Y_PASS",
)
HOST_AXIS = (
    "STAGE47_RIGHTY_SDL_UP_SENT",
    "STAGE47_RIGHTY_CENTER_AFTER_UP_SENT",
    "STAGE47_RIGHTY_SDL_DOWN_SENT",
    "STAGE47_RIGHTY_CENTER_AFTER_DOWN_SENT",
)
HOST_SNAPSHOT = (
    "STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_UP_POSITIVE",
    "STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_CENTER_AFTER_UP",
    "STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_DOWN_NEGATIVE",
    "STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_CENTER_AFTER_DOWN",
)
B_DOWN = "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"
B_UP = "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"


def audit(report_dir: Path) -> dict:
    original = audit_guest(report_dir)
    logs = report_dir / "data-root" / "logs"
    paths = sorted(logs.glob("nexium-*.log")) if logs.is_dir() else []
    if len(paths) != 1:
        raise ValueError("one isolated original FileLogger is required")
    guest = paths[0].read_text(encoding="utf-8", errors="replace")
    host = (report_dir / "nexium-console.log").read_text(encoding="utf-8", errors="replace")
    ordered_guest = ordered(guest, tuple("OutputDebugString: " + marker for marker in GUEST))
    failed_guest = any(
        ("OutputDebugString: " + marker) in guest
        for marker in ("STAGE47_GUEST_RIGHT_Y_INCOMPLETE",
                       "STAGE47_GUEST_UNEXPECTED_DIGITAL_BUTTON")
    )
    axis = ordered(host, HOST_AXIS)
    snapshot = ordered(host, HOST_SNAPSHOT)
    b_surrounds_axis = (
        original["host_press_release_marker_order_valid"] and
        host.find(B_DOWN) < host.find(HOST_AXIS[0]) <
        host.find(HOST_AXIS[-1]) < host.find(B_UP)
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
    published_b = original["serialized_npad_trace_roundtrip_observed"]
    passed = bool(
        boot and ordered_guest and not failed_guest and axis
        and snapshot and b_surrounds_axis and published_b
    )
    return {
        "schema": "nexium-stage47-guest-right-stick-y/v1",
        "same_process_guest_right_y_roundtrip_passed": passed,
        "guest_boot_and_hid_mapping_observed": boot,
        "guest_positive_up_negative_down_sequence_observed": ordered_guest,
        "guest_incomplete_or_unexpected_button_observed": failed_guest,
        "host_virtual_sdl_y_pulses_ordered": axis,
        "original_input_snapshot_inverted_y_sign_observed": snapshot,
        "original_host_b_surrounds_y_pulses": b_surrounds_axis,
        "original_npad_b_published_and_released": published_b,
        "original_npad_serialized_sample_count": original["serialized_npad_samples"],
        "gameplay_verified": False,
        "physical_controller_verified": False,
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
        result = audit(args.report_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["same_process_guest_right_y_roundtrip_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE47_RIGHT_Y_AUDIT_BLOCKED: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
