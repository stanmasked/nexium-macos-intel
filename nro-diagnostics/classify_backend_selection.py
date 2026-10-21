#!/usr/bin/env python3
"""Compare REAL Intel NeXium public-NRO runs with forced CPU backend choices.

Pure evidence classifier. Process survival, boot log markers, and a valid NRO
never prove guest instructions, video pixels or gameplay. Only aggregate
boolean markers and hashes leave the isolated GitHub runner.
"""
import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_PUBLIC_NRO = "2a1faf864eac55b033b2fcf8f385f2246a897a88b0b2d2f535dc0439e4dbf9d3"
MARKERS = {
    "loader_ui_accepted": "Auto-loaded NRO:",
    "guest_boot_thread_entered": "Booting NRO:",
    "guest_boot_context_ready": "Boot context ready",
    "guest_cpu_initialization_seen": "cpu memory null policy:",
    "guest_vulkan_renderer_created": "nexium-nvdrv: Vulkan Renderer initialized",
    "dynarmic_unavailable": "Dynarmic backend not compiled in",
    "rustarmic_unavailable": "Rustarmic backend not compiled in",
    "reentrant_gui_panic": "tried to handle event while another event is currently being handled",
}

def scan_local_logs(root: Path) -> dict:
    candidates = [root / "nexium-console.log",
                  *sorted((root / "data-root" / "logs").glob("*.log"))[:12]]
    chunks = []
    for p in candidates:
        if not p.is_file() or p.is_symlink():
            continue
        chunks.append(p.read_bytes()[:250_000].decode("utf-8", errors="replace"))
    data = "\n".join(chunks)
    return {key: value in data for key, value in MARKERS.items()}


def classify(dyn: dict, rust: dict, receipt: dict,
             dyn_markers: dict, rust_markers: dict) -> dict:
    expected = receipt.get("sha256")
    if expected != EXPECTED_PUBLIC_NRO:
        raise ValueError("unexpected public NRO digest")
    for name, row in (("dynarmic", dyn), ("rustarmic", rust)):
        if row.get("nro_file") != "nexium_clean_smoke.nro":
            raise ValueError(name + ": not the approved clean NRO")
        if row.get("nro_sha256") != expected:
            raise ValueError(name + ": NRO mismatch")
        if row.get("gameplay_verified") is not False:
            raise ValueError(name + ": unsafe gameplay claim")
        if row.get("status") not in (
            "timeout_alive_unverified", "exited_zero_unverified",
            "exited_nonzero", "launch_failed"
        ):
            raise ValueError(name + ": unexpected process state")
    binary = dyn.get("emulator_sha256")
    if not isinstance(binary, str) or len(binary) != 64 or (
        binary != rust.get("emulator_sha256")
    ):
        raise ValueError("two modes must use the exact same emulator binary")
    if any(not isinstance(v, bool) for d in (dyn_markers, rust_markers)
           for v in d.values()):
        raise ValueError("log markers must be booleans")
    variants = {}
    for name, report, markers in (
        ("requested_dynarmic", dyn, dyn_markers),
        ("forced_rustarmic", rust, rust_markers),
    ):
        capture = report.get("window_capture", {})
        if not isinstance(capture, dict):
            raise ValueError(name + ": invalid window evidence")
        frames = capture.get("frames", 0)
        unique = capture.get("unique_hashes", 0)
        if (type(frames) is not int or type(unique) is not int or
                frames < 0 or unique < 0 or unique > frames):
            raise ValueError(name + ": invalid PID-owned window hash counts")
        variants[name] = {
            "process_status": report["status"],
            "exit_code": report.get("exit_code"),
            "alive_at_deadline": report["status"] == "timeout_alive_unverified",
            "snapshots_observed": len(report.get("snapshots", [])),
            "unique_snapshot_hashes": report.get("unique_frame_hashes", 0),
            "pid_owned_window": {
                "capture_requested": bool(capture.get("requested", False)),
                "capture_status": capture.get("status", "not_requested"),
                "frames_observed": frames,
                "unique_hashes": unique,
                "may_show_gui_without_any_guest_rendering": True,
            },
            "markers": markers,
        }
    return {
        "schema": "nexium-intel-stage34-clean-nro-cpu-selection/v1",
        "result": "TWO_PUBLIC_NRO_NATIVE_CPU_SELECTION_TRIALS_CLASSIFIED",
        "same_native_intel_executable_sha256": binary,
        "public_nro_sha256": expected,
        "variants": variants,
        "cpu_selection_fault_isolated": bool(
            dyn_markers.get("dynarmic_unavailable")
            and not rust_markers.get("dynarmic_unavailable")
        ),
        "native_window_capture_is_not_gameplay_evidence": True,
        "actual_guest_instructions_verified": False,
        "pixel_content_correctness_verified": False,
        "gameplay_verified": False,
        "audio_or_gamepad_functionality_verified": False,
        "no_private_game_data_or_firmware_used": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.root
    dyn = json.loads((base / "dynarmic" / "smoke_result.json").read_text())
    rust = json.loads((base / "rustarmic" / "smoke_result.json").read_text())
    receipt = json.loads(args.receipt.read_text())
    result = classify(
        dyn, rust, receipt,
        scan_local_logs(base / "dynarmic"),
        scan_local_logs(base / "rustarmic"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
