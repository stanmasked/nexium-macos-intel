#!/usr/bin/env python3
"""Stage45: compare authentic original NeXium snapshot on/off native processes.

Only derive fixed source-emitted markers and native window/proc flags.
Never publish private SDL input events, button/axis values, device identities,
raw stderr, home paths, window pixels or game files. The controlled button
roundtrip is a contract, NOT physical controller or gameplay evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

MODES = ("virtual-off", "virtual-on")
SOURCE = (
    "STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
    "STAGE40_PREWARM_MAIN_READY",
    "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
    "STAGE42_FULL_UI_ENTERED",
    "STAGE42_INPUT_POLL_FIRST",
    "STAGE45_ORIGINAL_SNAPSHOT_REQUESTED",
    "STAGE45_VIRTUAL_SNAPSHOT_BEGIN",
    "STAGE45_VIRTUAL_SNAPSHOT_SUBSYSTEM_UNAVAILABLE",
    "STAGE45_VIRTUAL_SNAPSHOT_ATTACH_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_OPEN_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_ATTACHED",
    "STAGE45_VIRTUAL_SNAPSHOT_NOT_CONNECTED",
    "STAGE45_VIRTUAL_SNAPSHOT_CONNECTED",
    "STAGE45_VIRTUAL_SNAPSHOT_INJECT_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_READBACK_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_PRESS_AXIS_OK",
    "STAGE45_VIRTUAL_SNAPSHOT_RELEASE_INJECT_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_RELEASE_READBACK_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK",
    "STAGE45_VIRTUAL_SNAPSHOT_DEVICE_CLEANED",
    "STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_FAILED",
    "STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED",
    "STAGE45_ORIGINAL_SNAPSHOT_BACKEND_MISSING",
)
MARKER = re.compile(r"^(STAGE(?:40|42|45)_[A-Z0-9_]+)[ \t]*$",re.M)
SNAP = ("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED","STAGE45_VIRTUAL_SNAPSHOT_BEGIN",
        "STAGE45_VIRTUAL_SNAPSHOT_ATTACHED","STAGE45_VIRTUAL_SNAPSHOT_CONNECTED",
        "STAGE45_VIRTUAL_SNAPSHOT_PRESS_AXIS_OK",
        "STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK",
        "STAGE45_VIRTUAL_SNAPSHOT_DEVICE_CLEANED",
        "STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED")
FAILS = tuple(x for x in SOURCE if x.startswith("STAGE45_") and
              (x.endswith("_FAILED") or x.endswith("_MISSING") or
               x.endswith("_UNAVAILABLE") or x.endswith("_NOT_CONNECTED")))


def demand(test: bool, reason: str) -> None:
    if not test:
        raise ValueError(reason)


def classify(mode: str, receipt: dict, log: str) -> dict:
    demand(mode in MODES,"unknown source-backed virtual input mode")
    demand(receipt.get("probe")=="no_nro_gui_process_only","not genuine native process")
    demand(receipt.get("duration_limit_seconds")==12,"wrong duration")
    demand(all(receipt.get(key) is False for key in
               ("nro_verified","gameplay_verified","gui_verified")),"fake game/frame proof")
    digest=receipt.get("emulator_sha256")
    demand(isinstance(digest,str) and bool(re.fullmatch("[a-f0-9]{64}",digest)),
           "invalid executable SHA")
    alive=receipt.get("alive_at_deadline")
    own_window=receipt.get("window_found")
    demand(type(alive) is bool and type(own_window) is bool,"unknown process/window state")
    demand(alive==(receipt.get("outcome")=="alive_without_gui_verification"),
           "process status contradiction")
    demand(not own_window or (alive and receipt.get("window_probe")==
           "own_visible_window_observed"),"unverified own window")
    raw=MARKER.findall(log)
    demand(len(raw)==len(set(raw)) and all(k in SOURCE for k in raw),
           "unknown/duplicated native source marker")
    found=set(raw)
    def seen(x: str)->bool:return x in found
    if mode=="virtual-off":
        demand(not any(k.startswith("STAGE45_") for k in found),
               "disabled virtual input mutated original input")
    else:
        demand(seen("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED"),
               "virtual test did not start in real original process")
        demand(not(seen("STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED") and
                   seen("STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_FAILED")),
               "contradictory snapshot contract")
        if seen("STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED"):
            demand(all(seen(k) for k in SNAP),
                   "virtual contract lacks physical source checkpoint progression")
            demand(not any(seen(k) for k in FAILS),
                   "virtual contract hides input failures")
        if seen("STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK"):
            demand(seen("STAGE45_VIRTUAL_SNAPSHOT_PRESS_AXIS_OK"),
                   "release without original press/axis proof")
    if alive and mode=="virtual-on":
        demand(all(seen(m) for m in (
            "STAGE40_PREWARM_MAIN_READY",
            "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
            "STAGE42_FULL_UI_ENTERED",
            "STAGE42_INPUT_POLL_FIRST",
        )), "virtual test never reached original UI or input poll")
    return {
        "native_process_outcome":receipt.get("outcome"),
        "alive_at_deadline":alive,
        "own_window_found":own_window,
        "real_input_backend_virtual_snapshot_test_requested":
            seen("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED"),
        "virtual_device_attached":
            seen("STAGE45_VIRTUAL_SNAPSHOT_ATTACHED"),
        "original_snapshot_south_button_and_left_axis_readback":
            seen("STAGE45_VIRTUAL_SNAPSHOT_PRESS_AXIS_OK"),
        "original_snapshot_button_release_and_neutral_axis_readback":
            seen("STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK"),
        "virtual_device_cleaned":
            seen("STAGE45_VIRTUAL_SNAPSHOT_DEVICE_CLEANED"),
        "original_snapshot_contract_passed":
            seen("STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED"),
        "original_gui_input_poll_returned":
            seen("STAGE42_INPUT_POLL_FIRST"),
        "winit_reentrant_panic":
            "tried to handle event while another event is currently being handled" in log,
    }


def audit(root:Path)->dict:
    processed={}
    digests=[]
    for mode in MODES:
        directory=root/mode
        receipt=json.loads((directory/"gui_process_probe.json").read_text("utf-8"))
        log=(directory/"nexium-stdout-stderr.log").read_bytes()[:350000].decode("utf-8","replace")
        processed[mode]=classify(mode,receipt,log)
        digests.append(receipt["emulator_sha256"])
    demand(len(set(digests))==1,"modes did not use identical original NeXium binary")
    return {
        "schema":"nexium-stage45-original-InputSnapshot-virtual-controller-intel/v1",
        "identical_original_intel_binary_sha256":digests[0],
        "original_native_process_count":2,
        "variants":processed,
        "system_sdl3_standalone_only":False,
        "physical_controller_verified":False,
        "gameplay_verified":False,
        "game_pixels_verified":False,
        "audio_verified":False,
    }


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    data=audit(args.reports)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n","utf-8")
    print(json.dumps(data,sort_keys=True))
    # A negative real outcome is preserved as evidence, but fail CI until
    # original snapshot mappings genuinely work.
    demand(data["variants"]["virtual-on"]["original_snapshot_contract_passed"],
           "Stage45 original NeXium snapshot virtual controller contract did not pass")
    demand(data["variants"]["virtual-on"]["own_window_found"] and
           data["variants"]["virtual-on"]["alive_at_deadline"],
           "Stage45 original full GUI did not remain alive with its own window")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
