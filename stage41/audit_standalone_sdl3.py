#!/usr/bin/env python3
"""Stage41: audit 4 native Intel standalone SDL3 process runs.

Only whitelisted source checkpoints and normalized statuses leave the runner.
The Homebrew SDL3 installed for this test is not NeXium's pinned static build.
SDL_InitSubSystem(SDL_INIT_GAMEPAD) is an approximate native analogue of
Rust sdl.gamepad(), NOT proof that both are compiled against the same SDL3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

MODES = ("bare", "appkit")
REPETITIONS = (1, 2)
MARKERS = (
    "PROCESS_ENTERED", "BEFORE_APPKIT", "AFTER_APPKIT",
    "BEFORE_HINTS", "AFTER_HINTS", "BEFORE_SDL_INIT", "SDL_INIT_FAILED",
    "AFTER_SDL_INIT", "BEFORE_GAMEPAD", "GAMEPAD_FAILED",
    "AFTER_GAMEPAD", "AFTER_QUIT",
)
SOURCE_RE = re.compile(r"^STAGE41_([A-Z0-9_]+)[ \t]*$", re.M)
COMMON = ("BEFORE_HINTS", "AFTER_HINTS", "BEFORE_SDL_INIT",
          "AFTER_SDL_INIT", "BEFORE_GAMEPAD", "AFTER_GAMEPAD", "AFTER_QUIT")


def audit_one(mode: str, returncode: int | None, log: str, timeout: bool = False) -> dict:
    if mode not in MODES:
        raise ValueError("unknown isolated SDL3 experiment")
    phases = SOURCE_RE.findall(log)
    if not phases or phases[0] != "PROCESS_ENTERED":
        raise ValueError("missing authentic standalone entry checkpoint")
    if len(set(phases)) != len(phases) or any(p not in MARKERS for p in phases):
        raise ValueError("unknown or repeated source checkpoint")
    if timeout and returncode is not None:
        raise ValueError("timeout/returncode contradiction")
    if not timeout and returncode is None:
        raise ValueError("native process has no result")
    if mode == "bare":
        if "BEFORE_APPKIT" in phases or "AFTER_APPKIT" in phases:
            raise ValueError("bare control incorrectly initialized AppKit")
        expected = ("PROCESS_ENTERED",) + COMMON
    else:
        expected = ("PROCESS_ENTERED", "BEFORE_APPKIT", "AFTER_APPKIT") + COMMON
    if "SDL_INIT_FAILED" in phases:
        if phases[-1] != "SDL_INIT_FAILED" or "AFTER_SDL_INIT" in phases:
            raise ValueError("contradictory SDL init failure")
        expected = expected[:expected.index("AFTER_SDL_INIT")] + ("SDL_INIT_FAILED",)
    if "GAMEPAD_FAILED" in phases:
        if phases[-1] != "GAMEPAD_FAILED" or "AFTER_GAMEPAD" in phases:
            raise ValueError("contradictory gamepad failure")
        expected = expected[:expected.index("AFTER_GAMEPAD")] + ("GAMEPAD_FAILED",)
    if phases != list(expected[:len(phases)]):
        raise ValueError("out-of-order or skipped native SDL3 checkpoint")
    if not timeout and returncode == 0 and phases[-1] != "AFTER_QUIT":
        raise ValueError("process reported success without SDL3 shutdown checkpoint")
    return {
        "mode": mode,
        "outcome": "timeout" if timeout else (
            "exited_zero" if returncode == 0 else "exited_nonzero"
        ),
        "exit_signal": (
            f"SIG{-returncode}" if returncode is not None and returncode < 0 else None
        ),
        "exit_code": returncode if returncode is not None and returncode >= 0 else None,
        "observed_source_phases": phases,
        "gamepad_initialization_returned": "AFTER_GAMEPAD" in phases,
        "clean_sdl_quit": "AFTER_QUIT" in phases,
    }


def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as src:
        for buf in iter(lambda: src.read(1024 * 1024), b""):
            d.update(buf)
    return d.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    executable = args.binary.resolve(strict=True)
    digest = sha256(executable)
    records = {}
    for mode in MODES:
        for rep in REPETITIONS:
            timeout = False
            returncode = None
            output = b""
            try:
                proc = subprocess.run(
                    [str(executable), mode], stdin=subprocess.DEVNULL,
                    capture_output=True, timeout=12, check=False,
                )
                output = proc.stderr[:100000]
                returncode = proc.returncode
            except subprocess.TimeoutExpired as exc:
                timeout = True
                output = (exc.stderr or b"")[:100000]
            record = audit_one(mode, returncode, output.decode("utf-8", "replace"), timeout)
            records[f"{mode}-{rep}"] = record
    result = {
        "schema": "nexium-stage41-standalone-system-sdl3-intel/v1",
        "identical_executable_sha256": digest,
        "native_process_count": len(records),
        "results": records,
        "compiled_against_homebrew_sdl3_not_pinned_nexium": True,
        "appkit_linked_both_modes_shared_application_only_in_appkit_mode": True,
        "actual_neXium_sdl3_binary_tested": False,
        "controller_buttons_or_motion_verified": False,
        "native_root_cause_proven": False,
        "gameplay_or_pixels_verified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
