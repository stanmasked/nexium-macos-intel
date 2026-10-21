#!/usr/bin/env python3
"""Stage41: fail-closed no-virtual-SDL3 control after a real Stage40 guest pass.

Both jobs use the exact same CI-build NeXium Mach-O and libnx diagnostic NRO.
This run deliberately DOES NOT attach Stage36's synthetic SDL3 gamepad. The
guest must start, map its HID shared memory and finish WITHOUT seeing B.

Reads only the current run's private NEXIUM_DATA_ROOT FileLogger and the
sanitized positive receipt. Emits booleans/counts, never raw logs or pixels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_guest_hid_runtime import audit as audit_guest

END_MARKER = "OutputDebugString: STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP"
POSITIVE_SCHEMA = "nexium-stage40-guest-npad-readback/v1"


def audit_no_virtual(report_dir: Path, positive_receipt: Path) -> dict:
    positive = json.loads(positive_receipt.read_text(encoding="utf-8"))
    if positive.get("schema") != POSITIVE_SCHEMA:
        raise ValueError("Stage41 requires the genuine Stage40 receipt schema")
    positive_pass = positive.get("same_process_guest_input_roundtrip_passed") is True
    if not positive_pass:
        raise ValueError("Stage41 requires the previous positive guest B round-trip")

    result = audit_guest(report_dir)
    root = report_dir / "data-root" / "logs"
    logs = sorted(root.glob("nexium-*.log")) if root.is_dir() else []
    if len(logs) != 1:
        raise ValueError("Stage41 requires exactly one isolated guest FileLogger")
    guest_text = logs[0].read_text(encoding="utf-8", errors="replace")
    start_marker = "OutputDebugString: STAGE40_GUEST_HID_PROBE_START"
    start_at = guest_text.find(start_marker)
    end_at = guest_text.find(END_MARKER)
    # Reject any lone B_UP line too: "up after down" would otherwise be false.
    # The no-B exit event must be produced after the guest actually started.
    end_seen = start_at >= 0 and end_at > start_at
    guest_b_absent = not any((
        result["guest_libnx_b_down_observed"],
        "OutputDebugString: STAGE40_GUEST_HID_B_UP" in guest_text,
        result["guest_probe_pass_marker_observed"],
    ))
    host_b_absent = not any((
        result["host_original_hid_b_press_observed"],
        result["host_original_hid_b_release_observed"],
    ))
    npad_b_absent = result["serialized_npad_b_press_samples"] == 0
    guest_boot_ok = all((
        result["nro_autoload_observed"],
        result["guest_boot_started_observed"],
        result["guest_boot_context_ready_observed"],
        result["guest_hid_map_svc_observed"],
        result["guest_hid_map_success_marker_observed"],
        result["guest_output_debug_svc_observed"],
        result["guest_probe_start_observed"],
        not result["guest_boot_failed_observed"],
        result["probe_process_outcome_acceptable"],
    ))
    passed = bool(positive_pass and guest_boot_ok and end_seen
                  and guest_b_absent and host_b_absent and npad_b_absent
                  and not result["same_process_guest_input_roundtrip_passed"])

    return {
        "schema": "nexium-stage41-no-virtual-guest-npad-control/v1",
        "stage40_positive_guest_roundtrip_confirmed": positive_pass,
        "negative_same_nro_guest_boot_and_hid_map_observed": bool(guest_boot_ok),
        "negative_guest_probe_exited_without_b_observed": end_seen,
        "negative_guest_b_markers_absent": guest_b_absent,
        "negative_host_synthetic_b_markers_absent": host_b_absent,
        "negative_published_npad_b_absent": npad_b_absent,
        "negative_original_npad_sample_count": result["serialized_npad_samples"],
        "no_virtual_guest_control_passed": passed,
        "guest_gameplay_verified": False,
        "physical_controller_verified": False,
        "real_switch_verified": False,
        "raw_logs_uploaded": False,
        "frame_images_uploaded": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--stage40-positive-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_no_virtual(args.report_dir, args.stage40_positive_receipt)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0 if result["no_virtual_guest_control_passed"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE41_NO_VIRTUAL_GUEST_CONTROL_BLOCKED: "
              + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
