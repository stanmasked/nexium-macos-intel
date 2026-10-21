#!/usr/bin/env python3
"""Stage31: independent repeatability audit of unchanged Stage29 Intel NeXium.

Only the original Stage29 x86_64 Mach-O and genuine process reports may pass.
Correctly distinguish Stage26 ctor-wrapper markers from the normal full GUI.
Store only source-bound markers and sanitized process receipts, never raw logs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

PINNED_SHA256 = "dcde8e712eac86966bd66b6510b5d99ab69092adbaa4c67f19a4a3172c44d89b"
MODES = (
    "ctor-input-enabled",
    "ctor-input-skipped",
    "full-input-skipped",
    "full-init-minimal",
)
REPETITIONS = ("1", "2")
PHASE_LINE = re.compile(r"^STAGE28_HORIZON_CTOR_PHASE_([A-Z0-9_]+)[ \t]*$", re.MULTILINE)
VALID_PHASES = (
    "00_BEFORE_THEME", "01_BEFORE_UI_AUDIO", "02_AFTER_UI_AUDIO",
    "03_BEFORE_INPUT", "04_AFTER_INPUT", "05_BEFORE_NEXTENDO",
    "06_AFTER_NEXTENDO", "07_AFTER_STRUCT", "08_AFTER_PROFILE",
    "09_AFTER_SFX", "10_BEFORE_RESCAN", "11_AFTER_RESCAN",
    "12_BEFORE_RETURN",
)


def classify_one(name: str, report: dict, console: str) -> dict:
    if name not in MODES:
        raise ValueError("unknown SDL3 control mode")
    if report.get("probe") != "no_nro_gui_process_only":
        raise ValueError("not an original NeXium process receipt")
    if report.get("emulator_sha256") != PINNED_SHA256:
        raise ValueError("not the original Stage29 native Intel binary")
    if any(report.get(field) is not False for field in
           ("nro_verified", "gameplay_verified", "gui_verified")):
        raise ValueError("unsupported gameplay, rendering, or NRO claim")
    if report.get("outcome") not in (
        "alive_without_gui_verification", "exited_nonzero",
        "exited_zero_unverified",
    ):
        raise ValueError("unrecognized process outcome")
    entered = "STAGE26_HORIZON_CTOR_ENTERED" in console
    returned = "STAGE26_HORIZON_CTOR_RETURNED" in console
    skipped = "STAGE29_SDL3_INPUT_SKIPPED" in console
    enabled = "STAGE29_SDL3_INPUT_ENABLED" in console
    early = "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED" in console
    if entered and returned is False and report.get("outcome") == "alive_without_gui_verification":
        raise ValueError("inert constructor wrapper alive without constructor return")
    if skipped and enabled:
        raise ValueError("mutually exclusive SDL3 branches both present")
    if name == "full-init-minimal":
        if not early or entered or returned or skipped or enabled:
            raise ValueError("minimal host control mixed with original GUI paths")
    elif name == "full-input-skipped":
        # No Stage26 wrapper marker is expected in original full HorizonApp.
        if early or entered or returned or enabled:
            raise ValueError("full GUI control contains another guarded branch")
        if report.get("alive_at_deadline") and not skipped:
            raise ValueError("full GUI survived but did not confirm SDL3 bypass")
    elif name == "ctor-input-skipped":
        if not entered or early or enabled:
            raise ValueError("SDL3-skipped ctor-wrapper branch not proven")
        if report.get("alive_at_deadline") and (not skipped or not returned):
            raise ValueError("surviving ctor-wrapper did not return via SDL3 skip")
    else:
        if not entered or early or skipped:
            raise ValueError("original SDL3-enabled ctor-wrapper branch not proven")
        if report.get("alive_at_deadline") and (not enabled or not returned):
            raise ValueError("surviving SDL3-enabled ctor wrapper never returned")
    raw_phases = PHASE_LINE.findall(console)
    if any(p not in VALID_PHASES for p in raw_phases):
        raise ValueError("unrecognized constructor phase marker")
    return {
        "outcome": report["outcome"],
        "exit_signal": report.get("exit_signal"),
        "alive_at_12s_deadline": report.get("alive_at_deadline"),
        "process_owned_visible_window": report.get("window_found"),
        "horizon_constructor_entered": entered,
        "horizon_constructor_returned": returned,
        "actual_sdl3_input_skipped_marker": skipped,
        "actual_sdl3_input_enabled_marker": enabled,
        "full_host_minimal_marker": early,
        "actual_constructor_phases_in_emission_order": raw_phases,
        "last_emitted_phase": raw_phases[-1] if raw_phases else None,
        "winit_reentrant_event_panic_observed":
            "tried to handle event while another event is currently being handled" in console,
    }


def classify_all(rows: dict[tuple[str, str], tuple[dict, str]]) -> dict:
    expected = {(m, rep) for m in MODES for rep in REPETITIONS}
    if set(rows) != expected:
        raise ValueError("must audit two authentic launches of each of four modes")
    modes = {}
    for mode in MODES:
        observations = [
            classify_one(mode, *rows[(mode, rep)]) for rep in REPETITIONS
        ]
        modes[mode] = {
            "runs": observations,
            "survived_12s_count": sum(r["alive_at_12s_deadline"] is True
                                      for r in observations),
            "sigabrt_count": sum(r["exit_signal"] == "SIGABRT"
                                 for r in observations),
            "visible_window_count": sum(r["process_owned_visible_window"] is True
                                         for r in observations),
        }
    return {
        "schema": "nexium-stage31-authentic-intel-sdl3-ablation-repeat/v1",
        "result": "EIGHT_REAL_NATIVE_INTEL_PROCESS_RUNS_CLASSIFIED",
        "source_stage29_run_id": 39559370735,
        "pinned_original_intel_executable_sha256": PINNED_SHA256,
        "repeat_count_per_mode": 2,
        "modes": modes,
        "input_initialized_by_bypassed_mode": False,
        "actual_rendered_pixels_verified": False,
        "nro_supplied": False,
        "guest_game_played": False,
        "speaker_audio_verified": False,
        "causal_root_cause_proven": False,
        "original_console_or_png_uploaded": False,
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        rows={}
        for mode in MODES:
            for rep in REPETITIONS:
                path=args.reports/(mode+"-"+rep)
                receipt=json.loads((path/"gui_process_probe.json").read_text(encoding="utf-8"))
                console=(path/"nexium-stdout-stderr.log").read_text(
                    encoding="utf-8", errors="replace")
                rows[(mode,rep)]=(receipt,console)
        out=classify_all(rows)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(out,sort_keys=True))
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
        print("STAGE31_AUTHENTIC_INTEL_AUDIT_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
