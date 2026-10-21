#!/usr/bin/env python3
"""Stage42: classify original HorizonApp full UI versus constructor-only poll.

Whitelisted source checkpoints only: never serialize raw SDL inputs, key
presses, gamepad IDs, native stderr, screenshots, game files, or memory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MODES = ("ctor-prewarm", "full-prewarm", "full-skipped")
PHASES = ("00_ENTRY", "01_BEFORE_SDL_INIT", "02_BEFORE_GAMEPAD_SUBSYSTEM",
          "03_BEFORE_RUMBLE", "04_BEFORE_INPUT_STRUCT")
KNOWN = ("STAGE29_SDL3_INPUT_ENABLED", "STAGE29_SDL3_INPUT_SKIPPED",
         "STAGE40_PREWARM_MAIN_BEFORE_EFRAME", "STAGE40_PREWARM_MAIN_READY",
         "STAGE40_PREWARM_MAIN_UNAVAILABLE",
         "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
         "STAGE40_PREWARM_CONSTRUCTOR_MISSING",
         "STAGE42_FULL_UI_ENTERED", "STAGE42_INPUT_POLL_FIRST",
         "STAGE42_CONTROLLER_CONNECTED")
PHASE_RX = re.compile(r"^STAGE38_SDL3_INPUT_([A-Z0-9_]+)[ \t]*$", re.M)
MARKER_RX = re.compile(r"^(STAGE(?:29|40|42)_[A-Z0-9_]+)[ \t]*$", re.M)


def require(value: bool, why: str) -> None:
    if not value:
        raise ValueError(why)


def classify(mode: str, report: dict, console: str) -> dict:
    require(mode in MODES, "unknown comparison mode")
    require(report.get("probe") == "no_nro_gui_process_only", "not a genuine original process")
    require(report.get("duration_limit_seconds") == 12, "unexpected observation horizon")
    require(all(report.get(k) is False for k in (
        "nro_verified", "gameplay_verified", "gui_verified"
    )), "unsupported gameplay or GUI-pixel assertion")
    hash_text = report.get("emulator_sha256")
    require(isinstance(hash_text, str) and bool(re.fullmatch(r"[a-f0-9]{64}", hash_text)),
            "invalid native binary identity")
    outcome = report.get("outcome")
    require(outcome in ("alive_without_gui_verification", "exited_nonzero",
                        "exited_zero_unverified"), "unexpected process outcome")
    alive, window = report.get("alive_at_deadline"), report.get("window_found")
    require(type(alive) is bool and type(window) is bool, "non-boolean process flags")
    require(alive == (outcome == "alive_without_gui_verification"), "process state contradiction")
    require(not window or (alive and report.get("window_probe") ==
                           "own_visible_window_observed"), "window did not belong to live process")
    phases = PHASE_RX.findall(console)
    require(phases == list(PHASES[:len(phases)]), "unordered or duplicate SDL phase")
    found_all = MARKER_RX.findall(console)
    require(all(m in KNOWN for m in found_all) and len(set(found_all)) == len(found_all),
            "unknown or duplicated original markers")
    found = set(found_all)
    def has(name: str) -> bool:
        return name in found
    if mode == "full-skipped":
        require(has("STAGE29_SDL3_INPUT_SKIPPED") and
                not has("STAGE29_SDL3_INPUT_ENABLED") and
                not phases and
                not any(m.startswith("STAGE40_") for m in found),
                "skipped control unexpectedly initialized SDL3")
        require(not has("STAGE42_INPUT_POLL_FIRST") and
                not has("STAGE42_CONTROLLER_CONNECTED"),
                "disabled input unexpectedly polled")
    else:
        require(has("STAGE29_SDL3_INPUT_ENABLED") and
                not has("STAGE29_SDL3_INPUT_SKIPPED"),
                "SDL3 unexpectedly bypassed")
        if alive:
            require(all(has(m) for m in (
                "STAGE40_PREWARM_MAIN_BEFORE_EFRAME", "STAGE40_PREWARM_MAIN_READY",
                "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"
            )), "live experiment lacks authentic prewarm handoff")
        if has("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"):
            require(has("STAGE40_PREWARM_MAIN_READY"),
                    "consumed input without successful prewarm")
        if mode == "ctor-prewarm":
            require(not any(has(m) for m in (
                "STAGE42_FULL_UI_ENTERED", "STAGE42_INPUT_POLL_FIRST",
                "STAGE42_CONTROLLER_CONNECTED"
            )), "ctor-only control called original UI")
    if has("STAGE42_INPUT_POLL_FIRST"):
        require(has("STAGE42_FULL_UI_ENTERED"), "poll marker without original UI")
    if has("STAGE42_CONTROLLER_CONNECTED"):
        require(has("STAGE42_INPUT_POLL_FIRST"), "connected before poll")
    return {
        "outcome": outcome,
        "alive_at_deadline": alive,
        "own_window_found": window,
        "exit_signal": report.get("exit_signal"),
        "original_ui_entered": has("STAGE42_FULL_UI_ENTERED"),
        "original_sdl3_poll_invoked": has("STAGE42_INPUT_POLL_FIRST"),
        "controller_connection_seen": has("STAGE42_CONTROLLER_CONNECTED"),
        "prewarm_consumed": has("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"),
        "ordered_sdl3_initialization_phases": phases,
        "winit_reentrant_panic_seen":
            "tried to handle event while another event is currently being handled" in console,
    }


def audit(root: Path) -> dict:
    values = {}
    binary = []
    for mode in MODES:
        sub = root / mode
        raw = json.loads((sub / "gui_process_probe.json").read_text(encoding="utf-8"))
        output = (sub / "nexium-stdout-stderr.log").read_bytes()[:350000].decode(
            "utf-8", "replace"
        )
        values[mode] = classify(mode, raw, output)
        binary.append(raw["emulator_sha256"])
    require(len(set(binary)) == 1, "native executable differs between modes")
    return {
        "schema": "nexium-stage42-original-ui-sdl3-poll-intel/v1",
        "identical_native_x86_64_macho_sha256": binary[0],
        "authentic_native_processes": len(values),
        "modes": values,
        "original_ui_poll_is_not_physical_controller_input": True,
        "controller_button_and_axis_mapping_verified": False,
        "gameplay_verified": False,
        "game_pixels_verified": False,
        "native_audio_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = audit(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
