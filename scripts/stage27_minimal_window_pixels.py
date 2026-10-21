#!/usr/bin/env python3
"""Stage27: attempt strictly PID-scoped NeXium minimal window screenshot.

Unlike Stage25's CoreGraphics window *existence* proof, this attempts a real
window-specific PNG capture on the SAME previously compiled Intel binary.
Never captures the desktop or an arbitrary process and never publishes PNGs.
A screenshot is not validation of emulation or game rendering.
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

EXPECTED_EXE = "nexium"
EXPECTED_SHA = "38f66e29623995835af8f35409d802e929e084774e40727223de7b3bf9f5e5ad"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as infile:
        for data in iter(lambda: infile.read(1048576), b""):
            digest.update(data)
    return digest.hexdigest()


def summarise_capture(details: dict, binary_hash: str, exited_early: bool) -> dict:
    """Never forward raw paths, arbitrary window content or private logs."""
    frames = details.get("frames") or []
    safe = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        dims = frame.get("dimensions")
        digest = frame.get("sha256")
        bytecount = frame.get("bytes")
        if (isinstance(dims, list) and len(dims) == 2
                and all(isinstance(x,int) and x >= 100 for x in dims)
                and isinstance(digest,str) and len(digest)==64
                and all(x in "0123456789abcdef" for x in digest)
                and isinstance(bytecount,int) and bytecount >= 128):
            safe.append({"dimensions":dims, "sha256":digest, "bytes":bytecount})
    return {
        "schema": "nexium-stage27-pid-scoped-minimal-window-png/v1",
        "compiled_emulator_sha256": binary_hash,
        "original_stage25_binary_verified": binary_hash == EXPECTED_SHA,
        "capture_type": "target_pid_window_only",
        "process_exited_before_window_capture": exited_early,
        "capture_status": "captured_window_png_unverified_content" if safe
            else "no_window_png_captured",
        "valid_png_count": len(safe),
        "unique_png_hashes": len({x["sha256"] for x in safe}),
        "original_pngs_uploaded": False,
        "other_windows_captured": False,
        "nro_supplied": False,
        "window_content_is_correct_emulator_ui": None,
        "gameplay_verified": False,
        "actual_switch_sound_verified": False,
        "frames": safe,
        "capture_error_count": len(details.get("errors") or []),
    }


def run(exe: Path, report: Path, seconds: int) -> dict:
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise ValueError("authentic Intel macOS runner required")
    if exe.name != EXPECTED_EXE or not exe.is_file() or not os.access(exe,os.X_OK):
        raise ValueError("unknown or missing NeXium executable")
    binary_hash = sha256(exe)
    if binary_hash != EXPECTED_SHA:
        raise ValueError("not the verified original native Stage25 Intel Mach-O")
    capture_script = Path(__file__).with_name("capture_macos_window.py")
    if not capture_script.is_file():
        raise ValueError("same-repository scoped window capture script missing")
    report.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stage27-minimal-pixel-capture-") as temp:
        private = Path(temp)
        env = dict(os.environ)
        env.update({
            "HOME": str(private / "home"),
            "XDG_DATA_HOME": str(private / "data"),
            "XDG_CONFIG_HOME": str(private / "config"),
            "NEXIUM_MACOS_MINIMAL_EFRAME": "1",
            "NEXIUM_MACOS_FULL_INIT_MINIMAL_APP": "0",
            "NEXIUM_MACOS_NO_AUDIO": "1",
            "RUST_BACKTRACE": "0",
        })
        (private/"home").mkdir()
        with (private/"nexium-console-private.txt").open("wb") as console:
            child=subprocess.Popen([str(exe)],env=env,cwd=private,
                                   stdin=subprocess.DEVNULL,
                                   stdout=console,stderr=subprocess.STDOUT,
                                   start_new_session=True)
            try:
                time.sleep(2)
                early = child.poll() is not None
                capture_details={}
                if not early:
                    bounded=subprocess.run([
                        sys.executable, str(capture_script),
                        "--pid", str(child.pid),
                        "--output", str(private/"capture"),
                        "--duration", str(seconds),
                        "--interval", "2",
                    ], capture_output=True,text=True,timeout=seconds+90,check=False)
                    p=private/"capture/window_capture_result.json"
                    if p.is_file():
                        capture_details=json.loads(p.read_text(encoding="utf-8"))
                    else:
                        capture_details={"frames":[],"errors":["capture helper did not produce report"]}
                else:
                    capture_details={"frames":[],"errors":["process exited before camera attempt"]}
            finally:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid,signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            result=summarise_capture(capture_details,binary_hash,early)
            # Scope is strictly target PID; PNGs and private stdout remain in
            # a TemporaryDirectory, auto-deleted before this report is written.
    (report/"stage27-window-pixel-receipt.json").write_text(
        json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seconds",type=int,default=8)
    args=parser.parse_args()
    if not (2<=args.seconds<=60):
        parser.error("--seconds must be 2..60")
    try:
        run(args.exe.resolve(),args.output.resolve(),args.seconds)
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print("STAGE27_BLOCKED: "+str(error),file=sys.stderr)
        return 2
    # No screenshot (e.g. macOS permissions) is meaningful negative evidence
    # and must not make the receipt masquerade as an image success.
    return 0


if __name__=="__main__":
    raise SystemExit(main())
