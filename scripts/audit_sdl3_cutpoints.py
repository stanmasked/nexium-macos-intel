#!/usr/bin/env python3
"""Source-bound Stage39 native Intel SDL3 process audit.

Read native process receipts and private stderr on the runner. Write ONLY a
whitelisted derived JSON; never copy logs, screenshots or original receipts
into public artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MODES = (
    "no-input", "before-hints", "before-init", "before-gamepad",
    "before-rumble", "before-struct", "full",
)
CUTS = ("hints", "init", "gamepad", "rumble", "struct")
PHASES = (
    "00_ENTRY", "01_BEFORE_SDL_INIT", "02_BEFORE_GAMEPAD_SUBSYSTEM",
    "03_BEFORE_RUMBLE", "04_BEFORE_INPUT_STRUCT",
)
SHA = re.compile(r"[0-9a-f]{64}\Z")
SIGNAL = re.compile(r"SIG[A-Z0-9]+\Z")
PHASE = re.compile(r"^STAGE38_SDL3_INPUT_([A-Z0-9_]+)[ \t]*$", re.M)
STOP = re.compile(r"^STAGE39_SDL3_STOP_BEFORE_([A-Z]+)[ \t]*$", re.M)
ENABLED = re.compile(r"^STAGE29_SDL3_INPUT_ENABLED[ \t]*$", re.M)
SKIPPED = re.compile(r"^STAGE29_SDL3_INPUT_SKIPPED[ \t]*$", re.M)
PANIC_TEXT = "tried to handle event while another event is currently being handled"
OUTCOMES = (
    "alive_without_gui_verification", "exited_nonzero", "exited_zero_unverified"
)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def classify(name: str, receipt: dict, log: str) -> dict:
    """Validate actual source checkpoints and exclude unsupported evidence."""
    _require(name in MODES, "unknown variant")
    _require(receipt.get("probe") == "no_nro_gui_process_only", "wrong process probe")
    digest = receipt.get("emulator_sha256")
    _require(isinstance(digest, str) and bool(SHA.fullmatch(digest)), "invalid binary digest")
    _require(all(receipt.get(k) is False for k in (
        "nro_verified", "gameplay_verified", "gui_verified"
    )), "unsupported game, GUI pixel or NRO claim")
    _require(receipt.get("duration_limit_seconds") == 12, "unexpected probe duration")
    _require(receipt.get("outcome") in OUTCOMES, "process not successfully launched")
    alive = receipt.get("alive_at_deadline")
    window = receipt.get("window_found")
    _require(type(alive) is bool and type(window) is bool, "invalid process/window flags")
    _require(alive == (receipt["outcome"] == OUTCOMES[0]), "process outcome inconsistent")
    _require(not window or (
        alive and receipt.get("window_probe") == "own_visible_window_observed"
    ), "window observation inconsistent")
    sig = receipt.get("exit_signal")
    _require(sig is None or (
        isinstance(sig, str) and bool(SIGNAL.fullmatch(sig))
    ), "invalid signal code")
    if sig is not None:
        _require(not alive, "live process falsely signalled")

    phases = PHASE.findall(log)
    stops = STOP.findall(log)
    enabled = bool(ENABLED.search(log))
    skipped = bool(SKIPPED.search(log))
    _require(phases == list(PHASES[:len(phases)]), "missing, duplicate or reordered phase")
    _require(not (enabled and skipped), "conflicting SDL3 branches")
    if name == "no-input":
        _require(skipped and not enabled and not phases and not stops, "bad bypass control")
        _require(alive and window, "safe negative control no longer alive with its window")
    elif name == "full":
        _require(enabled and not skipped and not stops and phases, "full SDL3 path missing")
    else:
        _require(enabled and not skipped, "cutpoint did not use enabled SDL3 branch")
        cut = name.removeprefix("before-")
        ix = CUTS.index(cut)
        _require(stops in ([], [cut.upper()]), "wrong or duplicate cutpoint marker")
        _require(len(phases) <= ix + 1, "execution passed a requested cutpoint")
        if stops:
            _require(phases == list(PHASES[:ix + 1]), "trace disagrees with cutpoint")
        else:
            _require(not alive, "survivor never reached required cutpoint")
    return {
        "process_outcome": receipt["outcome"],
        "exit_signal": sig,
        "alive_at_deadline": alive,
        "own_window_found": window,
        "observed_ordered_input_phases": phases,
        "requested_cutpoint": name if name.startswith("before-") else None,
        "cutpoint_reached": bool(stops),
        "winit_reentrant_panic_observed": PANIC_TEXT in log,
    }


def audit(root: Path) -> dict:
    records = {}
    digests = []
    for mode in MODES:
        sub = root / mode
        receipt = json.loads((sub / "gui_process_probe.json").read_text("utf-8"))
        # Only source-emitted marker lines and one boolean are ever preserved.
        log = (sub / "nexium-stdout-stderr.log").read_bytes()[:350000].decode(
            "utf-8", "replace"
        )
        records[mode] = classify(mode, receipt, log)
        digests.append(receipt["emulator_sha256"])
    _require(len(set(digests)) == 1, "mismatched x86_64 executables")
    return {
        "schema": "nexium-stage39-intel-sdl3-cutpoint-contrast/v2",
        "single_native_x86_64_macho_sha256": digests[0],
        "real_process_count": len(records),
        "variants": records,
        "early_return_may_trigger_sdl_destructors": True,
        "native_root_cause_verified": False,
        "gameplay_verified": False,
        "game_pixels_verified": False,
        "controller_input_verified": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    result = audit(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
