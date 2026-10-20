#!/usr/bin/env python3
"""Stage24 independent Intel eframe process probe; never certify graphical output.

This only observes one child executable, run with one selected renderer.
No NRO/game/private material is accessed. Raw console data stays in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

MARKER = "STAGE24_CONTROL_RENDERER="


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def parse_evidence(text: str, renderer: str) -> dict:
    lines = text.splitlines()
    return {
        "expected_renderer_marker_observed": any(
            line.strip() == MARKER + renderer for line in lines),
        "other_renderer_marker_observed": any(
            line.strip() == MARKER + other for other in ("wgpu", "glow")
            if other != renderer for line in lines),
        "winit_reentrant_event_panic_observed":
            "tried to handle event while another event is currently being handled" in text,
        "panic_cannot_unwind_observed": "panic in a function that cannot unwind" in text,
    }


def run(exe: Path, out: Path, renderer: str, seconds: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["STAGE24_RENDERER"] = renderer
    env["RUST_BACKTRACE"] = "1"
    env["WGPU_BACKEND"] = "metal"
    begun = time.monotonic()
    result = {
        "schema": "nexium-stage24-independent-eframe-process/v1",
        "renderer": renderer,
        "executable_sha256": digest(exe),
        "outcome": "not_started",
        "exit_signal": None,
        "exit_code": None,
        "alive_at_deadline": False,
        "gui_rendering_proven": False,
        "window_pixels_observed": False,
        "nro_supplied": False,
        "nintendo_resources_used": False,
    }
    try:
        with (out / "control-console-private.log").open("wb") as output:
            child = subprocess.Popen([str(exe)], stdin=subprocess.DEVNULL,
                                     stdout=output, stderr=subprocess.STDOUT,
                                     env=env, start_new_session=True)
            try:
                code = child.wait(timeout=seconds)
                result["exit_code"] = code
                result["outcome"] = "exited_zero_unverified" if code == 0 else "exited_nonzero"
                if code < 0:
                    result["exit_signal"] = signal.Signals(-code).name
            except subprocess.TimeoutExpired:
                result["alive_at_deadline"] = True
                result["outcome"] = "alive_without_graphical_verification"
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    if child.poll() is None:
                        child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
    except OSError as exc:
        result["outcome"] = "launch_failed"
        result["launch_errno"] = exc.errno
    try:
        raw = (out / "control-console-private.log").read_bytes()[:200_000]
        result.update(parse_evidence(raw.decode("utf-8", "replace"), renderer))
    except OSError:
        result.update({"expected_renderer_marker_observed": False,
                       "other_renderer_marker_observed": False,
                       "winit_reentrant_event_panic_observed": False,
                       "panic_cannot_unwind_observed": False})
    result["wall_seconds"] = round(time.monotonic() - begun, 2)
    (out / "process-receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def classify_pair(wgpu: dict, glow: dict) -> dict:
    for name, row in (("wgpu", wgpu), ("glow", glow)):
        if not isinstance(row, dict) or row.get("schema") != "nexium-stage24-independent-eframe-process/v1":
            raise ValueError("unverified source receipt: " + name)
        if row.get("renderer") != name or row.get("expected_renderer_marker_observed") is not True:
            raise ValueError("renderer process did not reach expected code: " + name)
        if row.get("other_renderer_marker_observed") is not False:
            raise ValueError("mixed control identity: " + name)
        if row.get("nro_supplied") is not False or row.get("nintendo_resources_used") is not False:
            raise ValueError("unexpected game or proprietary asset")
        if row.get("gui_rendering_proven") is not False or row.get("window_pixels_observed") is not False:
            raise ValueError("unsupported graphics assertion")
        if row.get("outcome") not in ("exited_zero_unverified", "exited_nonzero",
                                       "alive_without_graphical_verification"):
            raise ValueError("missing genuine process observation")
        hexdigest = row.get("executable_sha256")
        if not isinstance(hexdigest, str) or len(hexdigest) != 64 or any(c not in "0123456789abcdef" for c in hexdigest):
            raise ValueError("invalid executable source hash")
    if wgpu["executable_sha256"] != glow["executable_sha256"]:
        raise ValueError("not the same Intel Mac binary")
    return {
        "schema": "nexium-stage24-independent-eframe-control-pair/v1",
        "result": "TWO_REAL_RENDERER_STARTUPS_CLASSIFIED",
        "same_executable_sha256": wgpu["executable_sha256"],
        "wgpu": {k: wgpu.get(k) for k in
                 ("outcome", "exit_code", "exit_signal", "alive_at_deadline",
                  "winit_reentrant_event_panic_observed", "panic_cannot_unwind_observed")},
        "glow": {k: glow.get(k) for k in
                 ("outcome", "exit_code", "exit_signal", "alive_at_deadline",
                  "winit_reentrant_event_panic_observed", "panic_cannot_unwind_observed")},
        "nexium_code_executed": False,
        "nro_executed": False,
        "physical_switch_sound_tested": False,
        "gui_rendering_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--renderer", choices=["wgpu", "glow"], required=True)
    parser.add_argument("--seconds", type=int, default=12)
    a = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        parser.error("physical macOS x86_64 required")
    if not 1 <= a.seconds <= 120:
        parser.error("seconds must be 1..120")
    exe = a.exe.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        parser.error("missing executable")
    result = run(exe, a.output.resolve(), a.renderer, a.seconds)
    print(json.dumps(result, sort_keys=True))
    # The two real failures remain observations; the workflow's final verifier
    # determines whether both controls ran and their source identity matched.
    return 0


if __name__ == "__main__":
    sys.exit(main())
