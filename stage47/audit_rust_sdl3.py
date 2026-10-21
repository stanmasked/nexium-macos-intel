#!/usr/bin/env python3
"""Stage47: verify actual pinned safe Rust SDL3 0.20 static bindings on Intel.

No raw SDL log, actual device identifier, pixel or input event is published.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

EXPECTED=("PROCESS_ENTERED","BEFORE_SDL_INIT","SUBSYSTEMS_READY",
          "BEFORE_ATTACH","VIRTUAL_GAMEPAD_OPENED",
          "BUTTON_AND_AXIS_OK","RELEASE_AND_NEUTRAL_OK",
          "DEVICE_CLEANED","CONTRACT_PASSED")
FAILS={"SDL_INIT_FAILED":"SUBSYSTEMS_READY",
       "JOYSTICK_SUBSYSTEM_FAILED":"SUBSYSTEMS_READY",
       "GAMEPAD_SUBSYSTEM_FAILED":"SUBSYSTEMS_READY",
       "ATTACH_FAILED":"VIRTUAL_GAMEPAD_OPENED",
       "OPEN_JOYSTICK_FAILED":"VIRTUAL_GAMEPAD_OPENED",
       "OPEN_GAMEPAD_FAILED":"VIRTUAL_GAMEPAD_OPENED",
       "EVENT_PUMP_FAILED":"BUTTON_AND_AXIS_OK",
       "INJECTION_FAILED":"BUTTON_AND_AXIS_OK",
       "READBACK_FAILED":"BUTTON_AND_AXIS_OK",
       "RELEASE_FAILED":"RELEASE_AND_NEUTRAL_OK",
       "RELEASE_READBACK_FAILED":"RELEASE_AND_NEUTRAL_OK"}
RX=re.compile(r"^STAGE47_([A-Z0-9_]+)[ \t]*$",re.M)

def inspect(mode:str,code:int|None,raw:str,timed_out:bool=False)->dict:
    if mode not in ("direct-update","event-pump"):
        raise ValueError("unknown original poll simulation")
    seq=RX.findall(raw)
    if not seq or seq[0]!="PROCESS_ENTERED":
        raise ValueError("missing actual Rust executable source entry")
    if len(seq)!=len(set(seq)):
        raise ValueError("repeated source checkpoints")
    if timed_out and code is not None:
        raise ValueError("timeout exit-code contradiction")
    if not timed_out and code is None:
        raise ValueError("process status missing")
    allowed=EXPECTED
    if seq[-1] in FAILS:
        failed=seq[-1]
        allowed=EXPECTED[:EXPECTED.index(FAILS[failed])]+(failed,)
    if tuple(seq)!=allowed[:len(seq)]:
        raise ValueError("invalid, unknown or reordered source checkpoints")
    if code==0 and (timed_out or seq[-1]!="CONTRACT_PASSED"):
        raise ValueError("zero status without actual pressed/released controller contract")
    if (timed_out or code != 0) and seq[-1]=="CONTRACT_PASSED":
        raise ValueError("controller contract marker followed by timeout/nonzero process exit")
    return {
        "status":"timeout" if timed_out else ("zero" if code==0 else "nonzero"),
        "exit_signal":f"SIG{-code}" if code is not None and code<0 else None,
        "safe_rust_sdl3_subsystems_initialized":"SUBSYSTEMS_READY" in seq,
        "virtual_gamepad_opened":"VIRTUAL_GAMEPAD_OPENED" in seq,
        "real_sdl3_button_axis_readback":"BUTTON_AND_AXIS_OK" in seq,
        "real_sdl3_release_neutral_readback":"RELEASE_AND_NEUTRAL_OK" in seq,
        "virtual_device_cleaned":"DEVICE_CLEANED" in seq,
        "actual_rust_contract_passed":"CONTRACT_PASSED" in seq,
        "source_checkpoints":seq,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    binary=args.binary.resolve(strict=True)
    digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    outcomes={}
    for mode in ("direct-update","event-pump"):
        for i in (1,2):
            code=None
            timeout=False
            data=b""
            try:
                result=subprocess.run([str(binary),mode],stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,timeout=12)
                data=result.stdout[:100000]
                code=result.returncode
            except subprocess.TimeoutExpired as exc:
                data=(exc.stdout or b"")[:100000]
                timeout=True
            outcomes[f"{mode}-{i}"]=inspect(mode,code,
                data.decode("utf-8","replace"),timeout)
    report={
        "schema":"nexium-stage47-pinned-rust-sdl3-static-virtual-controller-intel/v1",
        "identical_real_intel_binary_sha256":digest,
        "authentic_native_rust_processes":len(outcomes),
        "sdl3_dependency_exact":"0.20.0",
        "static_source_feature":"build-from-source-static",
        "outcomes":outcomes,
        "not_original_nexium_InputSnapshot":True,
        "actual_physical_controller_verified":False,
        "gameplay_verified":False,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n","utf-8")
    print(json.dumps(report,sort_keys=True))
    if not all(x["status"]=="zero" and x["actual_rust_contract_passed"]
               for x in outcomes.values()):
        raise ValueError("one or more authentic Rust SDL3 virtual input roundtrips did not exit cleanly")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
