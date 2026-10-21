#!/usr/bin/env python3
"""Stage44: no-hardware native Intel synthetic SDL3 input audit.

Never publish raw stderr, actual controller IDs, button events, paths or game
files. This proves a system SDL3 virtual gamepad's controlled input roundtrip
only. It does not test NeXium's pinned static SDL3 or physical controllers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

SUCCESS = ("PROCESS_ENTERED", "BEFORE_SDL_INIT", "SDL_READY",
           "BEFORE_ATTACH", "ATTACHED", "GAMEPAD_OPENED",
           "BEFORE_INJECTION", "BUTTON_AXIS_OBSERVED",
           "RELEASE_OBSERVED", "DETACHED", "CLEAN_EXIT")
FAILURE = ("SDL_INIT_FAILED", "ATTACH_FAILED", "OPEN_FAILED",
           "INJECTION_FAILED", "RELEASE_FAILED", "DETACH_FAILED")
RX = re.compile(r"^STAGE44_([A-Z0-9_]+)[ \t]*$", re.M)


def classify(mode: str, code: int | None, stderr: str, timeout: bool = False) -> dict:
    if mode not in ("bare", "appkit"):
        raise ValueError("unknown harness mode")
    prefix = ("PROCESS_ENTERED",) if mode == "bare" else (
        "PROCESS_ENTERED", "BEFORE_APPKIT", "AFTER_APPKIT"
    )
    expected = prefix + SUCCESS[1:]
    phases = RX.findall(stderr)
    if not phases or phases[0] != "PROCESS_ENTERED":
        raise ValueError("native source did not emit entry marker")
    if len(set(phases)) != len(phases):
        raise ValueError("duplicate source checkpoints")
    if timeout:
        if code is not None:
            raise ValueError("timeout and exit code cannot coexist")
    elif code is None:
        raise ValueError("no native process result")
    if phases[-1] in FAILURE:
        before = {
            "SDL_INIT_FAILED": "SDL_READY",
            "ATTACH_FAILED": "ATTACHED",
            "OPEN_FAILED": "GAMEPAD_OPENED",
            "INJECTION_FAILED": "BUTTON_AXIS_OBSERVED",
            "RELEASE_FAILED": "RELEASE_OBSERVED",
            "DETACH_FAILED": "DETACHED",
        }[phases[-1]]
        expected = expected[:expected.index(before)] + (phases[-1],)
    if phases != list(expected[:len(phases)]):
        raise ValueError("invalid ordering or unknown virtual SDL3 checkpoints")
    if code == 0 and (timeout or phases[-1] != "CLEAN_EXIT"):
        raise ValueError("success cannot omit readback, release and quit")
    return {
        "mode": mode,
        "exit_type": "timeout" if timeout else ("zero" if code == 0 else "nonzero"),
        "exit_signal": f"SIG{-code}" if code is not None and code < 0 else None,
        "phases": phases,
        "virtual_gamepad_opened": "GAMEPAD_OPENED" in phases,
        "virtual_button_and_axis_readback": "BUTTON_AXIS_OBSERVED" in phases,
        "virtual_release_readback": "RELEASE_OBSERVED" in phases,
        "clean_detach": "DETACHED" in phases and "CLEAN_EXIT" in phases,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    binary = args.binary.resolve(strict=True)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    outcomes = {}
    for mode in ("bare", "appkit"):
        for iteration in (1, 2):
            timeout = False
            code = None
            raw = b""
            try:
                p = subprocess.run(
                    [str(binary), mode], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=12, check=False,
                )
                raw = p.stderr[:100000]
                code = p.returncode
            except subprocess.TimeoutExpired as exc:
                raw = (exc.stderr or b"")[:100000]
                timeout = True
            outcomes[f"{mode}-{iteration}"] = classify(
                mode, code, raw.decode("utf-8", "replace"), timeout
            )
    data = {
        "schema": "nexium-stage44-system-sdl3-virtual-gamepad-intel/v1",
        "identical_native_binary_sha256": digest,
        "process_count": len(outcomes),
        "results": outcomes,
        "system_sdl3_not_nexium_static_library": True,
        "actual_physical_controller_verified": False,
        "neXium_input_snapshot_verified": False,
        "gameplay_verified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(data, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
