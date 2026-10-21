#!/usr/bin/env python3
"""Stage46: source-bound Intel NeXium original GUI/audio startup A-B audit.

Compares two authentic processes of a previously verified single native Intel
NeXium Mach-O. The source patch NEXIUM_MACOS_NO_AUDIO=1 suppresses host and
UI audio, while =0 preserves both. Process/window viability does NOT prove
CoreAudio device selection, decoded PCM, sound quality, or actual audio output.

Only fixed source labels and process metadata are published; no original
application logs, filenames, device IDs, screenshots, game data or audio.
"""
import argparse
import json
from pathlib import Path
import re

MODES = ("audio-off", "audio-on")
SOURCE_LABELS = (
    "STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
    "STAGE40_PREWARM_MAIN_READY",
    "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
    "STAGE42_FULL_UI_ENTERED",
    "STAGE42_INPUT_POLL_FIRST",
)
MARKER_RX = re.compile(r"^((?:STAGE40|STAGE42)_[A-Z0-9_]+)[ \t]*$", re.M)
PANIC = "tried to handle event while another event is currently being handled"

def validate(mode: str, receipt: dict, log: str) -> dict:
    if mode not in MODES:
        raise ValueError("unknown audio mode")
    if receipt.get("probe") != "no_nro_gui_process_only":
        raise ValueError("not an original native NeXium process")
    if receipt.get("duration_limit_seconds") != 12:
        raise ValueError("invalid native observation duration")
    if any(receipt.get(k) is not False for k in ("nro_verified","gameplay_verified","gui_verified")):
        raise ValueError("unwarranted NRO/gameplay/frame claim")
    digest=receipt.get("emulator_sha256")
    if not isinstance(digest,str) or re.fullmatch(r"[a-f0-9]{64}",digest) is None:
        raise ValueError("invalid Intel executable checksum")
    alive=receipt.get("alive_at_deadline")
    window=receipt.get("window_found")
    if type(alive) is not bool or type(window) is not bool:
        raise ValueError("non-boolean process/window evidence")
    if alive != (receipt.get("outcome") == "alive_without_gui_verification"):
        raise ValueError("inconsistent process status")
    if window and (not alive or receipt.get("window_probe") != "own_visible_window_observed"):
        raise ValueError("window did not belong to living NeXium process")
    raw=MARKER_RX.findall(log)
    if len(set(raw)) != len(raw) or any(x not in SOURCE_LABELS for x in raw):
        raise ValueError("duplicate or unknown original UI source marker")
    found=set(raw)
    if alive and any(x not in found for x in SOURCE_LABELS):
        raise ValueError("surviving app lacks original SDL3/UI/poll checkpoint")
    return {
        "process_alive_at_12_seconds": alive,
        "own_visible_window_identified": window,
        "source_markers_observed": [k for k in SOURCE_LABELS if k in found],
        "original_ui_entered": "STAGE42_FULL_UI_ENTERED" in found,
        "original_sdl3_poll_returned": "STAGE42_INPUT_POLL_FIRST" in found,
        "winit_reentrant_panic": PANIC in log,
        "exit_signal":receipt.get("exit_signal"),
        "outcome":receipt.get("outcome"),
    }

def audit(root: Path) -> dict:
    results={}
    digest=[]
    for mode in MODES:
        private=root/mode
        receipt=json.loads((private/"gui_process_probe.json").read_text("utf-8"))
        log=(private/"nexium-stdout-stderr.log").read_bytes()[:320000].decode("utf-8","replace")
        results[mode]=validate(mode,receipt,log)
        digest.append(receipt["emulator_sha256"])
    if len(set(digest)) != 1:
        raise ValueError("native executable differs between audio modes")
    return {
        "schema":"nexium-stage46-intel-original-full-gui-audio-startup-ab/v1",
        "single_native_intel_executable_sha256":digest[0],
        "original_intel_process_count":2,
        "modes":results,
        "audio_on_requested_does_not_prove_pcm_or_audible_output":True,
        "coreaudio_output_signal_verified":False,
        "audio_pcm_verified":False,
        "gameplay_verified":False,
        "game_pixels_verified":False,
        "physical_controller_verified":False,
    }

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reports",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    record=audit(a.reports)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,sort_keys=True,indent=2)+"\n","utf-8")
    print(json.dumps(record,sort_keys=True))
    # Preserve negative evidence, but a full GUI+SDL3+audio startup
    # must be real and healthy before this compatibility test passes.
    on=record["modes"]["audio-on"]
    if not (on["process_alive_at_12_seconds"] and on["own_visible_window_identified"]
            and on["original_ui_entered"] and on["original_sdl3_poll_returned"]
            and not on["winit_reentrant_panic"]):
        raise ValueError("native audio-enabled original GUI startup is not confirmed")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
