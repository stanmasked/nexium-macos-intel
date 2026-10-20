#!/usr/bin/env python3
"""Capture ONLY a specified emulator PID's visible macOS window.

Experimental local diagnostics. This NEVER captures the entire desktop, sends
anything to a server or treats screenshots as proof of correct gameplay.
Requires macOS Screen Recording permission; silence/denial is reported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_dimensions(path: Path) -> list[int] | None:
    try:
        with path.open("rb") as reader:
            head = reader.read(24)
        if len(head) < 24 or head[:8] != PNG_MAGIC or head[12:16] != b"IHDR":
            return None
        return [int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")]
    except OSError:
        return None


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return False


def is_nexium_process(pid: int) -> bool:
    """Fail closed if a PID was reused or belongs to another macOS app."""
    if pid <= 0 or not process_alive(pid):
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (result.returncode == 0 and
            Path(result.stdout.strip()).name.casefold() == "nexium")


def run_capture(pid: int, out: Path, duration: int, interval: float) -> dict:
    result: dict = {
        "pid": pid, "capture_type": "macos_pid_owned_window_only",
        "duration_seconds": duration, "interval_seconds": interval,
        "frames": [], "unique_hashes": 0, "errors": [],
        "gameplay_verified": False,
    }
    if not is_nexium_process(pid):
        result["errors"].append("refusing capture: PID is not a running NeXium process")
        result["status"] = "rejected_non_nexium_pid"
        return result
    out.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).with_name("nexium_window_id.swift")
    helper = out / "nexium-window-id"
    try:
        compiler = subprocess.run(
            ["xcrun", "swiftc", "-framework", "CoreGraphics", "-o", str(helper), str(src)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["errors"].append(f"Swift window helper compiler unavailable: {exc}")
        return result
    if compiler.returncode != 0:
        result["errors"].append(f"Swift helper compile failed: {compiler.stderr[-1200:]}")
        return result

    end = time.monotonic() + duration
    index = 0
    while time.monotonic() < end and is_nexium_process(pid):
        try:
            detected = subprocess.run(
                [str(helper), str(pid)], capture_output=True, text=True, timeout=6,
                check=False,
            )
            candidate = detected.stdout.strip()
            if detected.returncode != 0 or not candidate.isdigit() or int(candidate) < 1:
                result["errors"].append(f"Emulator window not visible: {detected.stderr.strip()[-160:]}")
            else:
                filename = f"emulator-window-{index:03d}.png"
                path = out / filename
                capture = subprocess.run(
                    ["screencapture", "-x", "-l", candidate, str(path)],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                dimensions = png_dimensions(path)
                if capture.returncode == 0 and dimensions and dimensions[0] > 0 and dimensions[1] > 0:
                    result["frames"].append({
                        "file": filename, "sha256": hash_file(path),
                        "dimensions": dimensions, "bytes": path.stat().st_size,
                    })
                else:
                    path.unlink(missing_ok=True)
                    result["errors"].append(
                        f"Window capture blocked/invalid; possible Screen Recording permission: "
                        f"{capture.stderr.strip()[-160:]}"
                    )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["errors"].append(f"Window discovery/capture error: {exc}")
        index += 1
        time.sleep(min(interval, max(0, end - time.monotonic())))
    result["unique_hashes"] = len({x["sha256"] for x in result["frames"]})
    result["status"] = (
        "window_frames_unverified" if result["frames"] else "no_window_frames_unverified"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=int, default=25)
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        parser.error("native Intel macOS required")
    if args.pid < 1:
        parser.error("--pid must be a positive process ID")
    if not 1 <= args.duration <= 180:
        parser.error("--duration must be 1..180 seconds")
    if not 0.5 <= args.interval <= 30:
        parser.error("--interval must be 0.5..30 seconds")
    out = args.output.expanduser().resolve()
    result = run_capture(args.pid, out, args.duration, args.interval)
    (out / "window_capture_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["frames"] else 2


if __name__ == "__main__":
    sys.exit(main())
