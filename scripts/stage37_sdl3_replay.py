#!/usr/bin/env python3
"""Stage37: exact-branch replay of one already-built native Intel SDL3 A/B/C/D.

The old inline Stage29 classifier confused a Stage26 *wrapper* marker with
entering HorizonApp::new from the ordinary path. Here source-specific
markers are evaluated per branch. Absence is reported, not guessed.
Never upload stdout, user paths, screenshots, NROs or game files.
"""
from pathlib import Path
import argparse
import json
import re

EXECUTABLE_SHA = None
VARIANTS = (
    "ctor-input-enabled",
    "ctor-input-skipped",
    "full-input-skipped",
    "full-init-minimal",
)
PREFIX = "STAGE28_HORIZON_CTOR_PHASE_"
PHASE = re.compile(r"^STAGE28_HORIZON_CTOR_PHASE_([A-Z0-9_]+)\s*$", re.MULTILINE)
SENTINELS = (
    "STAGE26_HORIZON_CTOR_ENTERED",
    "STAGE26_HORIZON_CTOR_RETURNED",
    "STAGE29_SDL3_INPUT_ENABLED",
    "STAGE29_SDL3_INPUT_SKIPPED",
    "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED",
)
REENTRANT = "tried to handle event while another event is currently being handled"

def exact_marker(console: str, marker: str) -> bool:
    return bool(re.search(r"^" + re.escape(marker) + r"\s*$",
                          console, re.MULTILINE))

def observe(name: str, report: dict, console: str) -> dict:
    if name not in VARIANTS:
        raise ValueError("unknown diagnostic branch")
    if report.get("probe") != "no_nro_gui_process_only":
        raise ValueError("missing actual no-NRO process receipt")
    if any(report.get(key) is not False for key in
           ("nro_verified", "gameplay_verified", "gui_verified")):
        raise ValueError("invalid game/GUI certification")
    if report.get("outcome") not in (
        "exited_nonzero", "exited_zero_unverified",
        "alive_without_gui_verification"
    ):
        raise ValueError("unrecognized host process outcome")
    marker = {name: exact_marker(console, name) for name in SENTINELS}
    wrapper = marker[SENTINELS[0]]
    returned = marker[SENTINELS[1]]
    enabled = marker[SENTINELS[2]]
    skipped = marker[SENTINELS[3]]
    host_control = marker[SENTINELS[4]]
    if enabled and skipped:
        raise ValueError("mutually exclusive SDL3 paths both emitted")
    if name.startswith("ctor-"):
        if not wrapper:
            raise ValueError("constructor-only wrapper was not entered")
        if name == "ctor-input-enabled" and skipped:
            raise ValueError("enabled path unexpectedly skipped SDL3")
        if name == "ctor-input-skipped" and enabled:
            raise ValueError("disabled path unexpectedly entered SDL3")
    else:
        # Stage26 emits wrapper entry only for *_CTOR_ONLY=1.
        # An ordinary HorizonApp uses its direct constructor without wrapper.
        if wrapper or returned:
            raise ValueError("wrapper marker in non-wrapper path")
        if name == "full-input-skipped" and enabled:
            raise ValueError("full UI unexpectedly enabled SDL3")
        if name == "full-init-minimal":
            if not host_control or enabled or skipped:
                raise ValueError("negative control entered original input")
    if name != "full-init-minimal" and host_control:
        raise ValueError("unexpected host-only minimal control")
    phases = PHASE.findall(console)
    if any(not re.fullmatch(r"\d\d_[A-Z_]+", p) for p in phases):
        raise ValueError("unexpected phase format")
    if name == "full-init-minimal" and phases:
        raise ValueError("original constructor executed in negative control")
    return {
        "outcome": report["outcome"],
        "exit_signal": report.get("exit_signal"),
        "alive_at_deadline": report.get("alive_at_deadline", False),
        "own_window_found": report.get("window_found", False),
        "stage26_wrapper_entered": wrapper,
        "stage26_wrapper_returned": returned,
        "sdl3_enabled_marker": enabled,
        "sdl3_skipped_marker": skipped,
        "full_host_minimal_control_marker": host_control,
        "observed_phase_order": phases,
        "last_observed_phase": phases[-1] if phases else None,
        "winit_reentrant_panic": REENTRANT in console,
    }

def classify(root: Path) -> dict:
    variants = {}
    shared_sha = None
    for name in VARIANTS:
        run = root / name
        report_path = run / "gui_process_probe.json"
        console_path = run / "nexium-stdout-stderr.log"
        if not report_path.is_file() or not console_path.is_file():
            raise ValueError("missing genuine Intel report: " + name)
        receipt = json.loads(report_path.read_text())
        sha = receipt.get("emulator_sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise ValueError("invalid native executable digest")
        if shared_sha is None:
            shared_sha = sha
        if shared_sha != sha:
            raise ValueError("different native Mach-O used in comparison")
        private_console = console_path.read_bytes()[:350_000].decode("utf-8", "replace")
        variants[name] = observe(name, receipt, private_console)
    return {
        "schema": "nexium-stage37-original-sdl3-input-replay/v1",
        "result": "FOUR_IDENTICAL_INTEL_BINARY_PROCESSES_CLASSIFIED",
        "original_executable_sha256": shared_sha,
        "original_run_id": 39559370735,
        "variants": variants,
        "nro_supplied": False,
        "guest_instructions_verified": False,
        "pixel_correctness_verified": False,
        "controller_functionality_verified": False,
        "speaker_audio_verified": False,
        "gameplay_verified": False,
        "source_specific_constructor_wrapper_marker": True,
        "audio_disabled_all_variants": True,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = classify(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
