#!/usr/bin/env python3
"""Native Intel macOS *GUI-process* probe; does not load games or certify frames.

Launch an existing x86_64 NeXium executable without an NRO and observe
whether the process immediately crashes or stays alive for a short window.
Results distinguish exit/crash from "still alive, GUI unverified". Never
treat elapsed runtime as proof of graphics, input, firmware, or game execution.
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
import tempfile
import time
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as data:
        for block in iter(lambda: data.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stop_group(process: subprocess.Popen, sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def probe(exe: Path, output: Path, seconds: int, window_helper: Path | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "probe": "no_nro_gui_process_only",
        "emulator_sha256": sha256(exe),
        "duration_limit_seconds": seconds,
        "outcome": "not_started",
        "exit_code": None,
        "alive_at_deadline": False,
        "gui_verified": False,
        "window_found": False,
        "window_id": None,
        "window_probe": "not_requested",
        "nro_verified": False,
        "gameplay_verified": False,
    }
    env = os.environ.copy()
    # Ensure no private game input. Isolate only NeXium's application data;
    # do not mutate the runner's HOME or globally configure the simulator.
    env["NEXIUM_DATA_ROOT"] = str(output / "private-neXium-data")
    env["NEXIUM_LOG_LEVEL"] = "info"
    env["RUST_BACKTRACE"] = "1"
    env.pop("NEXIUM_SNAPSHOT_DIR", None)
    env.pop("NEXIUM_SNAPSHOT_EVERY_MS", None)
    started = time.monotonic()
    with (output / "nexium-stdout-stderr.log").open("wb") as console:
        try:
            process = subprocess.Popen(
                [str(exe)], stdin=subprocess.DEVNULL, stdout=console,
                stderr=subprocess.STDOUT, env=env, start_new_session=True,
            )
            try:
                result["exit_code"] = process.wait(timeout=seconds)
                result["outcome"] = "exited_zero_unverified" if process.returncode == 0 else "exited_nonzero"
            except subprocess.TimeoutExpired:
                result["alive_at_deadline"] = True
                result["outcome"] = "alive_without_gui_verification"
                if window_helper is not None:
                    try:
                        inspected = subprocess.run(
                            [str(window_helper), str(process.pid)],
                            capture_output=True, text=True, timeout=10, check=False,
                        )
                        id_text = inspected.stdout.strip()
                        if inspected.returncode == 0 and id_text.isdigit() and int(id_text) > 0:
                            result["window_found"] = True
                            result["window_id"] = int(id_text)
                            result["window_probe"] = "own_visible_window_observed"
                        else:
                            result["window_probe"] = "no_visible_window_identified"
                            result["window_probe_detail"] = inspected.stderr.strip()[-300:]
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        result["window_probe"] = "window_inspection_failed"
                        result["window_probe_detail"] = str(exc)
                stop_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    stop_group(process, signal.SIGKILL)
                    process.wait(timeout=5)
        except OSError as exc:
            result["outcome"] = "launch_failed"
            result["error"] = str(exc)
    result["wall_seconds"] = round(time.monotonic() - started, 2)
    result["note"] = (
        "NO NRO was supplied. A living process or zero exit is NOT proof of "
        "window presentation, audio, input, homebrew or gameplay."
    )
    (output / "gui_process_probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=12)
    parser.add_argument("--window-helper", type=Path,
                        help="optional compiled macOS helper: identify a visible window owned by this PID")
    parser.add_argument("--allow-nonmac-synthetic", action="store_true",
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.allow_nonmac_synthetic:
        if platform.system() != "Darwin" or platform.machine() != "x86_64":
            parser.error("native Intel macOS required, not Apple Silicon/Rosetta")
        try:
            if subprocess.check_output(
                ["sysctl", "-n", "hw.optional.arm64"], stderr=subprocess.DEVNULL,
            ).strip() == b"1":
                parser.error("Apple Silicon/Rosetta not supported")
        except subprocess.CalledProcessError:
            pass
    if not 1 <= args.seconds <= 120:
        parser.error("--seconds must be 1..120")
    executable = args.exe.expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        parser.error(f"missing/non-executable NeXium binary: {executable}")
    helper = args.window_helper.expanduser().resolve() if args.window_helper is not None else None
    if helper is not None and (not helper.is_file() or not os.access(helper, os.X_OK)):
        parser.error("--window-helper must be an existing executable")
    outcome = probe(executable, args.output.expanduser().resolve(), args.seconds, helper)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    # Exit-zero from a child is not gameplay proof, but it is valid telemetry.
    return 2 if outcome["outcome"] in ("exited_nonzero", "launch_failed") else 0


if __name__ == "__main__":
    sys.exit(main())
