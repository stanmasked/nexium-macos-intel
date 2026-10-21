#!/usr/bin/env python3
"""Stage38: sanitize existing original HID trace into NPad B press/release booleans.

Reads private local no-NRO process receipts/logs and emits only safe booleans,
counts and the original executable SHA-256. Never prints or uploads raw HID
traces, pointers, keys, or full console lines.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import sys

NPAD_TRACE = re.compile(r"\[hid-publish\].*?npad=\[([0-9a-fA-FxX,\s]+)\]")
B_BIT = 1 << 1
STAGE36_PRESS = "STAGE36_VIRTUAL_SNAPSHOT_PRESS_MAPPED"
STAGE36_RELEASE = "STAGE36_VIRTUAL_SNAPSHOT_RELEASE_MAPPED"
STAGE37_PRESS = "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"
STAGE37_RELEASE = "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"
STAGE37_NO_SHMEM = "STAGE37_HID_BRIDGE_NO_GUEST_NPAD_SHMEM"
STAGE37_SHMEM_UNVERIFIED = "STAGE37_HID_BRIDGE_GUEST_SHMEM_MAPPING_PRESENT_UNVERIFIED"


def parse_npad_samples(console: str) -> list[list[int]]:
    samples: list[list[int]] = []
    for line in console.splitlines():
        match = NPAD_TRACE.search(line)
        if not match:
            continue
        values = [part.strip() for part in match.group(1).split(",") if part.strip()]
        if not values:
            continue
        try:
            sample = [int(value, 16) for value in values]
        except ValueError:
            continue
        samples.append(sample)
    return samples


def analyze_console(console: str) -> dict:
    lines = console.splitlines()
    markers = {line.strip() for line in lines}
    samples = parse_npad_samples(console)
    pressed_at = [i for i, values in enumerate(samples) if any(v & B_BIT for v in values)]
    released_after = [
        j for i in pressed_at for j in range(i + 1, len(samples))
        if all((v & B_BIT) == 0 for v in samples[j])
    ]
    return {
        "actual_hid_publish_trace_samples": len(samples),
        "serialized_npad_b_press_sample_count": len(pressed_at),
        "serialized_npad_b_release_after_press": bool(released_after),
        "original_snapshot_press_marker": STAGE36_PRESS in markers,
        "original_snapshot_release_marker": STAGE36_RELEASE in markers,
        "original_host_hid_press_marker": STAGE37_PRESS in markers,
        "original_host_hid_release_marker": STAGE37_RELEASE in markers,
        "guest_npad_shmem_unbound_marker": STAGE37_NO_SHMEM in markers,
        "guest_npad_shmem_present_unverified_marker": STAGE37_SHMEM_UNVERIFIED in markers,
        "stage40_svc_map_call_seen": "STAGE40_SVC_MAP_SHARED_MEMORY_ENTER" in markers,
        "stage40_hid_size_match_seen": "STAGE40_SVC_MAP_SIZE_MATCH_HID" in markers,
        "stage40_hid_size_other_seen": "STAGE40_SVC_MAP_SIZE_OTHER" in markers,
        "stage40_map_handle_nonzero_seen": "STAGE40_SVC_MAP_HANDLE_NONZERO" in markers,
        "stage40_map_handle_zero_seen": "STAGE40_SVC_MAP_HANDLE_ZERO" in markers,
        "stage40_hid_host_region_bound_seen": "STAGE40_HID_SHARED_MEMORY_HOST_BOUND" in markers,
        "stage40_cpu_map_success_seen": "STAGE40_HID_SHARED_MEMORY_CPU_MAP_OK" in markers,
        "stage40_cpu_map_failure_seen": "STAGE40_HID_SHARED_MEMORY_CPU_MAP_FAILED" in markers,
        "stage40_unmap_noop_seen": "STAGE40_SVC_UNMAP_SHARED_MEMORY_NOOP" in markers,
    }


def audit(root: Path) -> dict:
    modes = ("full-virtual", "full-no-virtual", "ctor-virtual")
    reports: dict[str, dict] = {}
    digest = None
    for mode in modes:
        path = root / mode
        receipt_path = path / "gui_process_probe.json"
        console_path = path / "nexium-stdout-stderr.log"
        if not receipt_path.is_file() or not console_path.is_file():
            raise ValueError(f"missing local source-bound process receipt for {mode}")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("probe") != "no_nro_gui_process_only":
            raise ValueError(f"unexpected process probe schema for {mode}")
        if receipt.get("nro_verified") is not False or receipt.get("gameplay_verified") is not False:
            raise ValueError(f"this audit must remain no-NRO for {mode}")
        if receipt.get("gui_verified") is not False:
            raise ValueError(f"this audit cannot claim rendered game frames for {mode}")
        if receipt.get("outcome") not in (
            "exited_nonzero", "exited_zero_unverified", "alive_without_gui_verification"
        ):
            raise ValueError(f"unclassified process outcome for {mode}")
        if digest is None:
            digest = receipt.get("emulator_sha256")
        if not digest or receipt.get("emulator_sha256") != digest:
            raise ValueError("all modes must use the same compiled NeXium Mach-O")
        console = console_path.read_text(encoding="utf-8", errors="replace")
        trace = analyze_console(console)
        if mode == "full-no-virtual":
            if any(trace[k] for k in (
                "original_snapshot_press_marker", "original_snapshot_release_marker",
                "original_host_hid_press_marker", "original_host_hid_release_marker",
                "serialized_npad_b_press_sample_count",
            )):
                raise ValueError("no-virtual negative control produced synthetic Switch B markers")
        elif mode == "ctor-virtual":
            if STAGE36_PRESS in console or STAGE37_PRESS in console or trace["serialized_npad_b_press_sample_count"]:
                raise ValueError("inert constructor unexpectedly polled or published Switch B")
            if "STAGE36_VIRTUAL_ATTACHED_AND_OPENED" not in console:
                raise ValueError("inert virtual-device control did not attach the synthetic pad")
        reports[mode] = {
            "process_alive_at_deadline": bool(receipt.get("alive_at_deadline")),
            "process_owned_window_found": bool(receipt.get("window_found")),
            **trace,
        }
    full = reports["full-virtual"]
    positive = all((
        full["original_snapshot_press_marker"],
        full["original_snapshot_release_marker"],
        full["original_host_hid_press_marker"],
        full["original_host_hid_release_marker"],
        full["serialized_npad_b_press_sample_count"] > 0,
        full["serialized_npad_b_release_after_press"],
    ))
    return {
        "schema": "nexium-stage38-original-npad-lifo-synthetic-b/v1",
        "result": "THREE_REAL_INTEL_NPAD_LIFO_PATHS_CLASSIFIED",
        "same_compiled_intel_macho_sha256": digest,
        "source_bound_synthetic_b_serialized_npad_lifo_round_trip_positive": positive,
        "guest_npad_shared_memory_verified": False,
        "real_hardware_controller_verified": False,
        "nintendo_game_nro_supplied": False,
        "vandal_hearts_gameplay_verified": False,
        "rendered_game_pixels_verified": False,
        "physical_switch_audio_verified": False,
        "raw_console_uploaded": False,
        "modes": reports,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        # stdout contains only sanitized fields; no raw HID or console data.
        print(json.dumps(result, sort_keys=True))
        return 0 if result["source_bound_synthetic_b_serialized_npad_lifo_round_trip_positive"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("STAGE38_NPAD_LIFO_AUDIT_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
