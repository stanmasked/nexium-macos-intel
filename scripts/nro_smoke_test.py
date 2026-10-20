#!/usr/bin/env python3
"""Local NeXium .nro smoke test: EVIDENCE collection, not gameplay certification.

Runs only on macOS Intel; does not upload private NROs/firmware/keys.
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
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def bitmap_size(path: Path):
    try:
        with path.open("rb") as f:
            head = f.read(26)
        if len(head) < 26 or head[:2] != b"BM":
            return None
        return [int.from_bytes(head[18:22], "little", signed=True),
                int.from_bytes(head[22:26], "little", signed=True)]
    except OSError:
        return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", type=Path, required=True, help="NeXium executable")
    p.add_argument("--nro", type=Path, required=True, help="local private NRO")
    p.add_argument("--output", type=Path, required=True, help="diagnostic directory")
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--snapshot-ms", type=int, default=2000)
    p.add_argument("--allow-nonmac-test", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if not 1 <= args.seconds <= 3600:
        p.error("--seconds must be 1..3600")
    if not 100 <= args.snapshot_ms <= 60000:
        p.error("--snapshot-ms must be 100..60000")
    if not args.allow_nonmac_test:
        if platform.system() != "Darwin" or platform.machine() != "x86_64":
            p.error("a native Intel macOS host is required")
        try:
            if subprocess.check_output(["sysctl", "-n", "hw.optional.arm64"],
                                       stderr=subprocess.DEVNULL).strip() == b"1":
                p.error("Apple Silicon / Rosetta is not supported")
        except subprocess.CalledProcessError:
            pass
    exe = args.exe.expanduser().resolve()
    nro = args.nro.expanduser().resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        p.error(f"NeXium executable missing/non-executable: {exe}")
    if not nro.is_file() or nro.suffix.lower() != ".nro":
        p.error(f"Private NRO missing: {nro}")
    out = args.output.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    snaps = out / "snapshots"
    snaps.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["NEXIUM_DATA_ROOT"] = str(out / "data-root")
    env["NEXIUM_SNAPSHOT_DIR"] = str(snaps)
    env["NEXIUM_SNAPSHOT_EVERY_MS"] = str(args.snapshot_ms)
    env["NEXIUM_LOG_LEVEL"] = "info"
    env["RUST_BACKTRACE"] = "1"
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.platform(),
        "arch": platform.machine(),
        "nro_file": nro.name,
        "nro_size": nro.stat().st_size,
        "nro_sha256": sha256(nro),
        "emulator_sha256": sha256(exe),
        "duration_limit_seconds": args.seconds,
        "status": "not_started", "exit_code": None,
        "snapshots": [], "unique_frame_hashes": 0,
        "gameplay_verified": False
    }
    started = time.monotonic()
    with (out / "nexium-console.log").open("wb") as logfile:
        try:
            proc = subprocess.Popen([str(exe), str(nro)], stdout=logfile,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
            try:
                report["exit_code"] = proc.wait(timeout=args.seconds)
                report["status"] = ("exited_zero_unverified" if proc.returncode == 0
                                    else "exited_nonzero")
            except subprocess.TimeoutExpired:
                report["status"] = "timeout_alive_unverified"
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        except OSError as e:
            report["status"] = "launch_failed"
            report["error"] = str(e)
    report["wall_seconds"] = round(time.monotonic() - started, 2)
    for path in sorted(snaps.glob("*.bmp")):
        report["snapshots"].append({
            "filename": path.name, "sha256": sha256(path),
            "bytes": path.stat().st_size, "dimensions": bitmap_size(path)
        })
    report["unique_frame_hashes"] = len({s["sha256"] for s in report["snapshots"]})
    report["note"] = ("Telemetry only. Screenshots or a living process do not establish "
                      "correct gameplay, controls, sound, or rendering.")
    (out / "smoke_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] in ("launch_failed", "exited_nonzero") else 0


if __name__ == "__main__":
    sys.exit(main())
