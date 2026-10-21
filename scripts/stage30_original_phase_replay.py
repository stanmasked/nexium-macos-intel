#!/usr/bin/env python3
"""Stage30: independently replay authenticated Stage28 Intel constructor traces.

Only the genuine Stage28 Mach-O is accepted. Missing phase markers are recorded
as evidence, not guessed or treated as an automatic audit success/failure.
Original private logs remain only in temporary CI directories and are NOT
uploaded. No NRO or game content is launched.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

EXPECTED_SHA256 = "345bb6188e3e5956018605d994e245550f660832fd240587fce6ac292ce59049"
PHASES = (
    "00_BEFORE_THEME",
    "01_BEFORE_UI_AUDIO",
    "02_AFTER_UI_AUDIO",
    "03_BEFORE_INPUT",
    "04_AFTER_INPUT",
    "05_BEFORE_NEXTENDO",
    "06_AFTER_NEXTENDO",
    "07_AFTER_STRUCT",
    "08_AFTER_PROFILE",
    "09_AFTER_SFX",
    "10_BEFORE_RESCAN",
    "11_AFTER_RESCAN",
    "12_BEFORE_RETURN",
)
PHASE_LINE = re.compile(r"^STAGE28_HORIZON_CTOR_PHASE_([A-Z0-9_]+)[ \t]*$", re.MULTILINE)
MODES = ("full-horizonapp", "constructor-only", "full-init-minimal")


def phase_evidence(private_console: str) -> dict:
    # Full-line matching excludes marker names from stack traces or copied
    # source snippets and preserves genuine stderr emission order.
    phases = PHASE_LINE.findall(private_console)
    unknown = [name for name in phases if name not in PHASES]
    if unknown:
        raise ValueError("unrecognized original constructor phase identifier")
    unique = list(dict.fromkeys(phases))
    reached = set(phases)
    if phases:
        high = max(PHASES.index(p) for p in phases)
        missed = [p for p in PHASES[:high] if p not in reached]
    else:
        missed = []
    prefix = 0
    for p in PHASES:
        if p not in reached:
            break
        prefix += 1
    return {
        "observed_emission_order": phases,
        "unique_observed_in_emission_order": unique,
        "highest_index_observed": max((PHASES.index(p) for p in phases), default=None),
        "last_emitted_phase": phases[-1] if phases else None,
        "unobserved_predecessors_before_highest": missed,
        "contiguous_prefix_length": prefix,
        "duplicate_phase_identifiers": sorted(p for p, n in Counter(phases).items() if n > 1),
        "phase_trace_present": bool(phases),
    }


def classify_rows(original_rows: dict[str, tuple[dict, str]]) -> dict:
    if set(original_rows) != set(MODES):
        raise ValueError("all three genuine source modes required")
    modes = {}
    digest = None
    for name in MODES:
        row, console = original_rows[name]
        if row.get("probe") != "no_nro_gui_process_only":
            raise ValueError("wrong origin process schema")
        if any(row.get(k) is not False for k in ("nro_verified", "gameplay_verified", "gui_verified")):
            raise ValueError("unsupported NRO/game/window assertion")
        if row.get("outcome") not in (
            "exited_nonzero", "exited_zero_unverified", "alive_without_gui_verification"
        ):
            raise ValueError("missing authentic process outcome")
        d = row.get("emulator_sha256")
        if d != EXPECTED_SHA256:
            raise ValueError("not the authenticated original Stage28 Intel Mach-O")
        if digest is None:
            digest = d
        if d != digest:
            raise ValueError("process binaries differ")
        evidence = phase_evidence(console)
        entered = "STAGE26_HORIZON_CTOR_ENTERED" in console
        returned = "STAGE26_HORIZON_CTOR_RETURNED" in console
        minimal = "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED" in console
        if name == "constructor-only":
            if not entered or minimal:
                raise ValueError("constructor-only path never entered genuine constructor")
            if returned and "12_BEFORE_RETURN" not in evidence["observed_emission_order"]:
                raise ValueError("return marker without final phase")
        elif name == "full-init-minimal":
            if not minimal or entered or returned or evidence["phase_trace_present"]:
                raise ValueError("negative control executed constructor")
        else:
            if minimal or entered or returned:
                raise ValueError("full startup mixed with guarded alternative")
        modes[name] = {
            "outcome": row["outcome"],
            "exit_signal": row.get("exit_signal"),
            "alive_at_12_second_deadline": row.get("alive_at_deadline"),
            "process_owned_window_found": row.get("window_found"),
            "horizon_constructor_entered": entered,
            "horizon_constructor_returned": returned,
            "winit_reentrancy_panic_observed":
                "tried to handle event while another event is currently being handled" in console,
            "trace": evidence,
        }
    return {
        "schema": "nexium-stage30-original-stage28-intel-phase-replay/v1",
        "result": "THREE_REAL_INTEL_CONSTRUCTOR_TRACE_REPORTS_CLASSIFIED",
        "source_stage28_action_run": 39558456359,
        "single_original_binary_sha256": digest,
        "variants": modes,
        "absence_of_marker_does_not_prove_source_call_was_not_executed": True,
        "phase_trace_instrumentation_is_not_a_causal_fix": True,
        "original_nro_executed": False,
        "frame_pixels_verified": False,
        "speaker_audio_verified": False,
        "root_cause_verified": False,
        "raw_private_logs_uploaded": False,
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        rows={}
        for name in MODES:
            folder=args.reports/name
            row=json.loads((folder/"gui_process_probe.json").read_text(encoding="utf-8"))
            console=(folder/"nexium-stdout-stderr.log").read_text(encoding="utf-8",errors="replace")
            rows[name]=(row,console)
        result=classify_rows(rows)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,sort_keys=True))
    except (OSError,UnicodeError,ValueError,KeyError,json.JSONDecodeError) as e:
        print("STAGE30_AUTHENTIC_TRACE_CLASSIFICATION_BLOCKED: "+str(e),file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
