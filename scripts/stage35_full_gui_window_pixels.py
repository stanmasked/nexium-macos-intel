#!/usr/bin/env python3
"""Stage35: unchanged original Stage32 Intel NeXium, PID-scoped GUI-window PNGs.

Compare genuine original full HorizonApp with SDL3 preinitialized to a
minimal-eframe control. Only the specific NeXium process window is captured;
raw PNGs and private logs are deleted before any public output.
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

SOURCE_SHA = "4d40b18bb52b5a498f0efb1d00812643bc4062e18c6e27a4d2af6b208787be93"
MODES = ("full-preinitialized-sdl3", "minimal-eframe")


def binary_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for b in iter(lambda: stream.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()


def receipt(raw: dict, mode: str, binary_hash: str, crashed_before: bool,
            observed_after: bool) -> dict:
    if mode not in MODES:
        raise ValueError("invalid original GUI mode")
    if binary_hash != SOURCE_SHA:
        raise ValueError("wrong original native Stage32 NeXium executable")
    if not isinstance(raw, dict):
        raise ValueError("invalid capture source")
    safe = []
    for f in raw.get("frames") or []:
        if not isinstance(f, dict):
            continue
        dims, digest, size = f.get("dimensions"), f.get("sha256"), f.get("bytes")
        if (isinstance(dims, list) and len(dims) == 2 and
            all(type(v) is int and v >= 100 for v in dims) and
            isinstance(digest, str) and len(digest) == 64 and
            all(v in "0123456789abcdef" for v in digest) and
            type(size) is int and size >= 128):
            safe.append({"dimensions": dims, "sha256": digest, "bytes": size})
    return {
        "mode": mode,
        "source_native_intel_neXium_sha256": binary_hash,
        "original_stage32_executable_verified": True,
        "capture_scope": "only_visible_window_of_exact_owned_neXium_PID",
        "capture_status": "genuine_pid_owned_window_png" if safe else "no_window_png",
        "valid_png_count": len(safe),
        "unique_frame_hashes": len({x["sha256"] for x in safe}),
        "process_exited_before_capture": crashed_before,
        "process_alive_after_capture": observed_after,
        "capture_error_count": len(raw.get("errors") or []),
        "raw_pngs_uploaded": False,
        "private_console_uploaded": False,
        "desktop_captured": False,
        "gui_content_correctness_verified": False,
        "nro_executed": False,
        "vandal_hearts_game_verified": False,
        "controller_buttons_verified": False,
        "physical_audio_verified": False,
        "frames": safe,
    }


def run_mode(exe: Path, mode: str, seconds: int) -> dict:
    if mode not in MODES:
        raise ValueError("unsupported source-verified UI path")
    with tempfile.TemporaryDirectory(prefix="nexium-stage35-") as tmp:
        private = Path(tmp)
        home = private/"home"
        home.mkdir()
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(private/"config"),
            "XDG_DATA_HOME": str(private/"data"),
            "RUST_BACKTRACE": "0",
            "NEXIUM_MACOS_NO_AUDIO": "1",
            "NEXIUM_MACOS_MINIMAL_EFRAME": "1" if mode=="minimal-eframe" else "0",
            "NEXIUM_MACOS_FULL_INIT_MINIMAL_APP": "0",
            "NEXIUM_MACOS_HORIZON_CTOR_ONLY": "0",
            "NEXIUM_MACOS_SKIP_SDL3_INPUT": "0",
            "NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT":
                "0" if mode=="minimal-eframe" else "1",
        })
        with (private/"original-stdout-stderr-private.txt").open("wb") as out:
            child=subprocess.Popen(
                [str(exe)], cwd=private, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                time.sleep(2)
                crashed = child.poll() is not None
                capture={}
                if not crashed:
                    helper=Path(__file__).with_name("capture_macos_window.py")
                    if not helper.is_file():
                        raise ValueError("original PID-only macOS capture helper absent")
                    bounded=subprocess.run([
                        sys.executable,str(helper), "--pid",str(child.pid),
                        "--output",str(private/"only-neXium-window"),
                        "--duration",str(seconds),"--interval","2"
                    ], capture_output=True,text=True,timeout=seconds+90,check=False)
                    source=private/"only-neXium-window/window_capture_result.json"
                    if source.is_file():
                        capture=json.loads(source.read_text(encoding="utf-8"))
                    else:
                        capture={"frames":[],"errors":["window helper receipt absent"]}
                else:
                    capture={"frames":[],"errors":["NeXium exited before capture"]}
                alive = child.poll() is None
            finally:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid,signal.SIGTERM)
                    except (ProcessLookupError,PermissionError):
                        child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
        return receipt(capture,mode,SOURCE_SHA,crashed,alive)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seconds",type=int,default=8)
    a=p.parse_args(argv)
    try:
        if platform.system()!="Darwin" or platform.machine()!="x86_64":
            raise ValueError("genuine macOS Intel runner required")
        if not 2<=a.seconds<=30:
            raise ValueError("invalid bounded window capture duration")
        exe=a.exe.resolve()
        if exe.name!="nexium" or not exe.is_file() or not os.access(exe,os.X_OK):
            raise ValueError("original NeXium native Mach-O not executable")
        if binary_sha256(exe)!=SOURCE_SHA:
            raise ValueError("not original verified Stage32 native Intel NeXium Mach-O")
        results={mode:run_mode(exe,mode,a.seconds) for mode in MODES}
        a.output.parent.mkdir(parents=True,exist_ok=True)
        summary={
            "schema":"nexium-stage35-real-intel-gui-window-png/v1",
            "source_stage32_run":39588444239,
            "source_original_intel_macho_sha256":SOURCE_SHA,
            "comparison":"full-original-horizon-sdl3-preinitialized-vs-early-minimal-eframe",
            "modes":results,
            "both_modes_captured_window_png":
                all(results[k]["valid_png_count"]>0 for k in MODES),
            "distinct_captured_window_image_hashes":
                (bool(set(f["sha256"] for f in results[MODES[0]]["frames"])
                      != set(f["sha256"] for f in results[MODES[1]]["frames"]))
                 if all(results[k]["valid_png_count"]>0 for k in MODES) else None),
            "gameplay_verified":False,
            "gui_pixel_correctness_verified":False,
            "physical_controller_verified":False,
            "raw_images_uploaded":False
        }
        a.output.write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(summary,sort_keys=True))
    except (OSError,ValueError,subprocess.SubprocessError,json.JSONDecodeError) as e:
        print("STAGE35_SOURCE_BOUND_CAPTURE_BLOCKED: "+str(e),file=sys.stderr)
        return 2
    # If macOS screen permission denied, report explicit negative evidence,
    # never fabricate a PNG or turn a process-owned window into pixel proof.
    return 0


if __name__=="__main__":
    sys.exit(main())
