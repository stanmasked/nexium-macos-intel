#!/usr/bin/env python3
"""Stage43: native Intel macOS private *NeXium-owned* window pixel sampling.

Run full original HorizonApp without an NRO, with Stage40 SDL3 prewarm and
Stage42 SDL3 polling source markers. This tool captures *only* the window
belonging to its own subprocess PID. Frames and raw stderr stay in Temporary-
Directory on the runner and are never copied to published reports. The only
output is whitelisted derived metadata (no images, paths, inputs, titles).
No claims about game pixels, audio, controllers, or NRO execution.
Requires Pillow for local pixel evaluation; no OCR or image upload.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time

from PIL import Image

MARKERS = (
    "STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
    "STAGE40_PREWARM_MAIN_READY",
    "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
    "STAGE42_FULL_UI_ENTERED",
    "STAGE42_INPUT_POLL_FIRST",
)
VALID = re.compile(r"^(" + "|".join(map(re.escape, MARKERS)) + r")[ \t]*$", re.M)


def evaluate_pixels(path: Path) -> dict:
    """Measure actual decoded pixels, not merely a PNG signature or file hash."""
    with Image.open(path) as opened:
        opened.verify()
    with Image.open(path) as opened:
        dimensions = opened.size
        if not (dimensions[0] >= 320 and dimensions[1] >= 200):
            raise ValueError("implausibly small native GUI image")
        if dimensions[0] > 8192 or dimensions[1] > 8192:
            raise ValueError("implausibly large native GUI image")
        rgb = opened.convert("RGB")
        # Downsample deterministically; no full-res pixels leave this process.
        sample = rgb.resize((64, 40), Image.Resampling.BOX)
        # RGB byte triplets avoid Pillow's deprecated getdata() API and
        # are independent of the library's pixel iterator behavior.
        pixels = sample.tobytes()
        samples = [(pixels[i], pixels[i + 1], pixels[i + 2])
                   for i in range(0, len(pixels), 3)]
    lum = [(299*r + 587*g + 114*b) / 1000 for (r,g,b) in samples]
    unique = len(set(samples))
    spread = round(statistics.pstdev(lum), 3)
    return {
        "width": dimensions[0],
        "height": dimensions[1],
        "sampled_unique_rgb_colors": unique,
        "sampled_luminance_stddev": spread,
        # Four strongly separated blocks are legitimate decoded nonuniform
        # pixels. This asserts only pixel diversity, not correct UI/gameplay.
        "spatially_nonuniform": unique >= 4 and spread >= 5,
    }


def extract_source_flags(log: str) -> dict:
    found = set(VALID.findall(log))
    return {
        "sdl3_before_eframe": "STAGE40_PREWARM_MAIN_BEFORE_EFRAME" in found,
        "sdl3_preinitialized": "STAGE40_PREWARM_MAIN_READY" in found,
        "same_thread_input_consumed": "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED" in found,
        "original_ui_entered": "STAGE42_FULL_UI_ENTERED" in found,
        "sdl3_input_poll_returned": "STAGE42_INPUT_POLL_FIRST" in found,
        "winit_reentrant_panic_detected":
            "tried to handle event while another event is currently being handled" in log,
    }


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def inspect(binary: Path, helper: Path, duration: int, max_frames: int) -> dict:
    record = {
        "schema": "nexium-stage43-private-owned-window-pixels-intel/v1",
        "native_x86_64_required": True,
        "no_nro_supplied": True,
        "gui_pixel_proof": "only private NeXium-owned window after decoded image validation",
        "original_ui_pixel_samples": [],
        "capture_attempts": 0,
        "native_window_identified": False,
        "physical_controller_input_verified": False,
        "nro_boot_verified": False,
        "gameplay_pixels_verified": False,
        "native_audio_verified": False,
    }
    with tempfile.TemporaryDirectory(prefix="stage43-private-owned-window-") as tmp:
        private = Path(tmp)
        env = os.environ.copy()
        env.update({
            "NEXIUM_DATA_ROOT": str(private / "private-nexium-data"),
            "NEXIUM_MACOS_NO_AUDIO": "1",
            "NEXIUM_MACOS_MINIMAL_EFRAME": "0",
            "NEXIUM_MACOS_FULL_INIT_MINIMAL_APP": "0",
            "NEXIUM_MACOS_HORIZON_CTOR_ONLY": "0",
            "NEXIUM_MACOS_PREWARM_SDL3_INPUT": "1",
            "NEXIUM_MACOS_SKIP_SDL3_INPUT": "0",
            "NEXIUM_MACOS_SDL3_STOP_BEFORE": "none",
            "NEXIUM_MACOS_SDL3_SUBPHASE_TRACE": "1",
            "NEXIUM_MACOS_SDL3_POLL_TRACE": "1",
            "RUST_BACKTRACE": "0",
        })
        # Never inherit optional user-provided game path or capture directories.
        for key in ("NEXIUM_SNAPSHOT_DIR", "NEXIUM_SNAPSHOT_EVERY_MS"):
            env.pop(key, None)
        path = private / "console-private.log"
        with path.open("wb") as log:
            process = subprocess.Popen(
                [str(binary)], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, env=env,
                start_new_session=True,
            )
            record["native_process_spawned"] = True
            started = time.monotonic()
            try:
                while time.monotonic() - started < duration:
                    if process.poll() is not None:
                        break
                    scanned = subprocess.run(
                        [str(helper), str(process.pid)],
                        capture_output=True, text=True, timeout=8, check=False,
                    )
                    window = scanned.stdout.strip()
                    if (scanned.returncode == 0 and window.isdigit()
                            and int(window) > 0):
                        record["native_window_identified"] = True
                        if len(record["original_ui_pixel_samples"]) < max_frames:
                            idx = record["capture_attempts"]
                            dest = private / f"private-window-{idx}.png"
                            capture = subprocess.run(
                                ["screencapture", "-x", "-l", window, str(dest)],
                                capture_output=True, timeout=10, check=False,
                            )
                            record["capture_attempts"] += 1
                            if capture.returncode == 0 and dest.is_file():
                                try:
                                    record["original_ui_pixel_samples"].append(
                                        evaluate_pixels(dest)
                                    )
                                except (OSError, ValueError, SyntaxError):
                                    pass
                            dest.unlink(missing_ok=True)
                    if len(record["original_ui_pixel_samples"]) >= max_frames:
                        # Keep process alive for short observation, but do not
                        # claim rendering accuracy merely from sampling frames.
                        break
                    time.sleep(1.5)
            finally:
                record["alive_before_cleanup"] = process.poll() is None
                record["exit_before_cleanup"] = process.poll()
                _terminate(process)
        source = extract_source_flags(
            path.read_bytes()[:350000].decode("utf-8", "replace")
        )
        record.update(source)
    record["decoded_private_window_frame_count"] = len(record["original_ui_pixel_samples"])
    record["nonuniform_window_frame_count"] = sum(
        int(i["spatially_nonuniform"]) for i in record["original_ui_pixel_samples"]
    )
    record["interpretation"] = (
        "decoded_nonuniform_neXium_window_pixels_not_gameplay"
        if record["nonuniform_window_frame_count"] else
        "no_verified_nonuniform_window_pixels"
    )
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--window-helper", type=Path, required=True)
    parser.add_argument("--duration", type=int, default=18)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        parser.error("native Intel macOS required")
    if not 8 <= args.duration <= 60 or not 1 <= args.samples <= 5:
        parser.error("unsupported sampling limits")
    try:
        mac = subprocess.check_output(["sysctl","-n","hw.optional.arm64"],
                                      stderr=subprocess.DEVNULL).strip()
        if mac == b"1":
            parser.error("Apple Silicon/Rosetta not accepted")
    except subprocess.CalledProcessError:
        pass
    binary = args.binary.resolve(strict=True)
    helper = args.window_helper.resolve(strict=True)
    result = inspect(binary, helper, args.duration, args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", "utf-8")
    print(json.dumps(result, sort_keys=True))
    # A permission failure results in "unverified" data, not fake success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
