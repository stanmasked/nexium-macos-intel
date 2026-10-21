#!/usr/bin/env python3
"""Classify real clean-public-NRO Intel diagnostics; never claim gameplay.

Read only local A/B JSON, the original PUBLIC NRO checksum receipt,
and bounded target-process log text. Emit a sanitized JSON receipt with
boolean markers. Never copy a raw log, guest screenshot, home path or token.
"""
from pathlib import Path
import argparse
import hashlib
import json


def marker_flags(console: Path, data_logs: Path) -> dict:
    lines = []
    for logfile in [console, *sorted(data_logs.glob("*.log"))[:12]]:
        if not logfile.is_file() or logfile.is_symlink():
            continue
        try:
            # Bound all reads; do not publish raw private diagnostic lines.
            lines.extend(logfile.read_bytes()[:300_000].decode(
                "utf-8", errors="replace").splitlines())
        except OSError:
            continue
    text = "\n".join(lines)
    return {
        "auto_loaded_nro_log_marker": "Auto-loaded NRO:" in text,
        "nro_load_error_log_marker": "Failed to load NRO:" in text,
        "boot_command_log_marker": "Boot: NRO=" in text,
        "guest_boot_thread_entered": "Booting NRO:" in text,
        "guest_boot_context_failure": "Boot failed:" in text,
        "guest_cpu_initialized_log_marker": "cpu memory null policy:" in text,
        "guest_vulkan_renderer_log_marker": "nexium-nvdrv: Vulkan Renderer initialized" in text,
        "guest_snapshot_saved_log_marker": "[snapshot] saved " in text,
        "winit_reentrant_panic": (
            "tried to handle event while another event is currently being handled" in text
        ),
        "log_data_examined": bool(lines),
    }


def classify(baseline: dict, guest: dict, expected: dict, signals: dict) -> dict:
    actual = guest.get("nro_sha256")
    if actual != expected.get("sha256") or len(str(actual)) != 64:
        raise ValueError("public NRO digest mismatch")
    if guest.get("nro_file") != "nexium_clean_smoke.nro":
        raise ValueError("only the original public clean NRO may be classified")
    if baseline.get("emulator_sha256") != guest.get("emulator_sha256"):
        raise ValueError("baseline and guest must run the exact same Intel binary")
    if baseline.get("probe") != "no_nro_gui_process_only":
        raise ValueError("real no-NRO baseline report missing")
    if baseline.get("nro_verified") or baseline.get("gameplay_verified"):
        raise ValueError("invalid no-NRO baseline claims")
    if guest.get("gameplay_verified"):
        raise ValueError("a smoke report may not independently claim gameplay")
    image_hashes = guest.get("unique_frame_hashes", 0)
    if not isinstance(image_hashes, int) or image_hashes < 0:
        raise ValueError("invalid snapshot hashes")
    capture = guest.get("window_capture", {})
    captured_frames = capture.get("frames", 0)
    captured_hashes = capture.get("unique_hashes", 0)
    if (type(captured_frames) is not int or captured_frames < 0 or
            type(captured_hashes) is not int or captured_hashes < 0 or
            captured_hashes > captured_frames):
        raise ValueError("invalid PID-owned window capture counts")
    return {
        "schema": "nexium-intel-public-nro-safegui-boot/v1",
        "public_nro_sha256": actual,
        "same_intel_executable_sha256": guest["emulator_sha256"],
        "no_nro_baseline": {
            "outcome": baseline.get("outcome"),
            "window_found": baseline.get("window_found", False),
            "alive_at_deadline": baseline.get("alive_at_deadline", False),
            "exit_signal": baseline.get("exit_signal"),
        },
        "clean_nro_argument_run": {
            "status": guest.get("status"),
            "exit_code": guest.get("exit_code"),
            "unique_snapshot_hashes": image_hashes,
            "snapshot_count": len(guest.get("snapshots", [])),
            "pid_owned_window_capture": {
                "status": capture.get("status", "not_requested"),
                "capture_attempted": bool(capture.get("requested", False)),
                "frames_observed": captured_frames,
                "unique_hashes": captured_hashes,
                "may_include_only_gui_without_guest_presentation": True,
            },
            **signals,
        },
        "public_test_nro_only": True,
        "nintendo_firmware_or_private_rom_used": False,
        "actual_guest_instructions_verified": False,
        "pixel_correctness_verified": False,
        "gameplay_verified": False,
        "sound_and_controller_input_verified": False,
        "conclusion": (
            "PROCESS_CRASHED_OR_EXITED" if guest.get("status") in
            ("exited_nonzero", "launch_failed")
            else "NRO_LOADER_LOG_MARKER_OBSERVED" if
            signals["auto_loaded_nro_log_marker"] and not
            signals["nro_load_error_log_marker"] else
            "PROCESS_OBSERVED_GUEST_LOAD_UNVERIFIED"
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--guest", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    baseline = json.loads(args.baseline.read_text())
    guest = json.loads(args.guest.read_text())
    expected = json.loads(args.receipt.read_text())
    flags = marker_flags(
        args.guest.parent / "nexium-console.log",
        args.guest.parent / "data-root" / "logs",
    )
    report = classify(baseline, guest, expected, flags)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    # A valid classification does not imply that the guest boot succeeded.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
