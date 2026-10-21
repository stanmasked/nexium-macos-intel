#!/usr/bin/env python3
"""Stage40 source-bound process classification; publish whitelist-only evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MODES = ("normal", "prewarm", "skipped")
PHASES = (
    "00_ENTRY", "01_BEFORE_SDL_INIT", "02_BEFORE_GAMEPAD_SUBSYSTEM",
    "03_BEFORE_RUMBLE", "04_BEFORE_INPUT_STRUCT",
)
PHASE = re.compile(r"^STAGE38_SDL3_INPUT_([A-Z0-9_]+)[ \t]*$", re.M)
SOURCE_MARKERS = (
    "STAGE29_SDL3_INPUT_ENABLED",
    "STAGE29_SDL3_INPUT_SKIPPED",
    "STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
    "STAGE40_PREWARM_MAIN_READY",
    "STAGE40_PREWARM_MAIN_UNAVAILABLE",
    "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
    "STAGE40_PREWARM_CONSTRUCTOR_MISSING",
)
OUTCOMES = ("exited_nonzero", "exited_zero_unverified", "alive_without_gui_verification")
PANIC_TEXT = "tried to handle event while another event is currently being handled"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def classify(mode: str, receipt: dict, log: str) -> dict:
    require(mode in MODES, "unexpected mode")
    require(receipt.get("probe") == "no_nro_gui_process_only", "not genuine process probe")
    require(receipt.get("outcome") in OUTCOMES, "invalid or missing launch")
    require(receipt.get("duration_limit_seconds") == 12, "wrong duration")
    require(all(receipt.get(field) is False for field in (
        "nro_verified", "gameplay_verified", "gui_verified",
    )), "unsupported game or pixels evidence")
    digest = receipt.get("emulator_sha256")
    require(isinstance(digest, str) and bool(re.fullmatch(r"[0-9a-f]{64}", digest)),
            "invalid original executable SHA")
    alive = receipt.get("alive_at_deadline")
    window = receipt.get("window_found")
    require(type(alive) is bool and type(window) is bool, "invalid process flags")
    require(alive == (receipt["outcome"] == "alive_without_gui_verification"),
            "inconsistent process result")
    require(not window or (
        alive and receipt.get("window_probe") == "own_visible_window_observed"
    ), "inconsistent own-window receipt")
    signal = receipt.get("exit_signal")
    require(signal is None or (
        isinstance(signal, str) and bool(re.fullmatch(r"SIG[A-Z0-9]+", signal))
    ), "invalid exit signal")
    require(not signal or not alive, "signal while process alive")
    phases = PHASE.findall(log)
    require(phases == list(PHASES[:len(phases)]), "out-of-order or duplicate subphases")
    present = {key for key in SOURCE_MARKERS
               if re.search(r"^" + re.escape(key) + r"[ \t]*$", log, re.M)}
    def has(marker: str) -> bool:
        return marker in present
    if mode == "skipped":
        require(has("STAGE29_SDL3_INPUT_SKIPPED")
                and not has("STAGE29_SDL3_INPUT_ENABLED")
                and not phases and not any(m.startswith("STAGE40") for m in present),
                "bypass must not initialize SDL3")
        require(alive and window, "safe-window negative control regression")
    elif mode == "normal":
        require(has("STAGE29_SDL3_INPUT_ENABLED")
                and not has("STAGE29_SDL3_INPUT_SKIPPED")
                and not any(m.startswith("STAGE40") for m in present)
                and phases, "normal SDL3 constructor path not reached")
    else:
        require(has("STAGE40_PREWARM_MAIN_BEFORE_EFRAME"),
                "prewarm did not run before eframe")
        require(not has("STAGE29_SDL3_INPUT_SKIPPED"),
                "prewarm did not preserve enabled SDL3")
        require(not (has("STAGE40_PREWARM_MAIN_READY")
                     and has("STAGE40_PREWARM_MAIN_UNAVAILABLE")),
                "contradictory prewarm result")
        require(not (has("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED")
                     and has("STAGE40_PREWARM_CONSTRUCTOR_MISSING")),
                "contradictory same-thread handoff")
        if has("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"):
            require(has("STAGE40_PREWARM_MAIN_READY")
                    and has("STAGE29_SDL3_INPUT_ENABLED"),
                    "prewarm handoff lacks real initialized source")
        if alive:
            require(has("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"),
                    "survival without verified SDL3 handoff cannot imply controller availability")
    return {
        "outcome": receipt["outcome"],
        "alive_at_deadline": alive,
        "own_window_found": window,
        "exit_signal": signal,
        "source_phases": phases,
        "source_markers": [m for m in SOURCE_MARKERS if m in present],
        "winit_reentrant_panic_observed": PANIC_TEXT in log,
    }


def audit(root: Path) -> dict:
    rows, hashes = {}, []
    for mode in MODES:
        base = root / mode
        report = json.loads((base / "gui_process_probe.json").read_text("utf-8"))
        log = (base / "nexium-stdout-stderr.log").read_bytes()[:350000].decode(
            "utf-8", "replace"
        )
        rows[mode] = classify(mode, report, log)
        hashes.append(report["emulator_sha256"])
    require(len(set(hashes)) == 1, "not one identical native executable")
    return {
        "schema": "nexium-stage40-intel-sdl3-prewarm/v1",
        "native_x86_64_binary_sha256": hashes[0],
        "observed_native_processes": len(rows),
        "modes": rows,
        "same_thread_handoff_only": True,
        "early_controller_preparation_proves_live_input": False,
        "native_root_cause_verified": False,
        "gameplay_verified": False,
        "pixel_content_verified": False,
        "controller_buttons_verified": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    result = audit(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", "utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
