#!/usr/bin/env python3
"""Stage36: independent REAL homebrew guest-NRO startup in Intel NeXium.

Uses immutable Stage32 native Intel NeXium and immutable public Stage371
homebrew diagnostic NRO, not a commercial ROM. Strict original-file hashes
and process-lifecycle observation; no fabricated guest results. Private logs
and guest SD are deleted. This does not certify game boot unless guest files
or authoritative exit evidence are actually observed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time

EMULATOR_SHA = "4d40b18bb52b5a498f0efb1d00812643bc4062e18c6e27a4d2af6b208787be93"
NRO_SHA = "cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b"
NRO_SIZE = 299064
NRO_NAME = "vandal-hearts-prototype.nro"
SOURCE_GAME_RUN = 39501847103
SOURCE_MAC_RUN = 39588444239
MODES = ("original-homebrew-nro", "rustarmic-homebrew-nro", "rustarmic-svc-trace-nro", "no-guest-control")


def digest(path: Path) -> str:
    hasher=hashlib.sha256()
    with path.open("rb") as infile:
        for b in iter(lambda: infile.read(1024 * 1024),b""):
            hasher.update(b)
    return hasher.hexdigest()


def validate_source(exe: Path, nro: Path) -> None:
    if exe.name != "nexium" or not exe.is_file() or not os.access(exe, os.X_OK):
        raise ValueError("missing real compiled NeXium executable")
    if digest(exe)!=EMULATOR_SHA:
        raise ValueError("not original Stage32 Intel NeXium binary")
    if nro.name!=NRO_NAME or not nro.is_file() or nro.stat().st_size!=NRO_SIZE:
        raise ValueError("not original Stage371 diagnostic homebrew NRO")
    if digest(nro)!=NRO_SHA:
        raise ValueError("original Stage371 NRO SHA256 mismatch")
    with nro.open("rb") as infile:
        infile.seek(16)
        if infile.read(4)!=b"NRO0":
            raise ValueError("original homebrew NRO0 header invalid")


def sanitize(mode: str, state: dict) -> dict:
    if mode not in MODES:
        raise ValueError("invalid source-verified guest mode")
    # All raw log/path/SD bytes remain private. Never upload them.
    return {
        "mode":mode,
        "source_original_neXium_sha256":EMULATOR_SHA,
        "source_original_guest_nro_sha256":NRO_SHA if mode!=MODES[3] else None,
        "exact_command_line_nro_argument_supplied":mode!=MODES[3],
        "original_requested_cpu_backend":("rustarmic" if mode in (MODES[1],MODES[2]) else "dynarmic"),
        "process_alive_at_12s":bool(state.get("alive_at_deadline",False)),
        "process_exit_signal":state.get("exit_signal"),
        "process_exited_nonzero":bool(state.get("exited_nonzero",False)),
        "process_owned_visible_window":bool(state.get("window_found",False)),
        "source_nro_auto_load_log_marker_observed":
            bool(state.get("auto_loaded_nro",False)),
        "source_nro_failure_log_marker_observed":
            bool(state.get("failed_load_nro",False)),
        "runner_guest_boot_attempt_observed":
            bool(state.get("booting_nro",False)),
        "runner_guest_boot_failure_observed":
            bool(state.get("boot_failed",False)),
        "runner_guest_cpu_context_initialization_observed":
            bool(state.get("cpu_memory_policy",False)),
        "original_kernel_boot_phases_observed":
            state.get("kernel_boot_phases",[]),
        "last_original_kernel_boot_phase_observed":
            (state.get("kernel_boot_phases",[]) or [None])[-1],
        "boot_failure_safe_category":
            state.get("boot_failure_category","NO_BOOT_ERROR_OBSERVED"),
        "source_guest_sd_diagnostic_file_count":
            int(state.get("guest_files",0)),
        "guest_probe_file_content_validated":False,
        "guest_cpu_instructions_verified":False,
        "complete_guest_boot_verified":False,
        "actual_gameplay_verified":False,
        "actual_audio_output_verified":False,
        "private_game_paths_uploaded":False,
        "private_console_uploaded":False,
        "guest_sd_file_bytes_uploaded":False,
    }


# Pinned upstream nexium-kernel::boot::BootContext::new_nro phase texts.
# Only names are published; no addresses, paths, register values or raw log.
SOURCE_KERNEL_BOOT_PHASES=(
    ("00_LOADING_NRO", "Loading NRO from:"),
    ("01_ADDRESS_SPACE_CREATED", "Creating address space"),
    ("02_MAPPING_MEMORY", "Mapping memory regions"),
    ("03_MAPPING_HEAP", "Mapping heap @"),
    ("04_MAPPING_STACK", "Mapping stack @"),
    ("05_MAPPING_EXTRAS", "Mapping extras (env+tls+exit_stub+tls_pool)"),
    ("06_WRITING_NRO", "Writing NRO ("),
    ("07_INITIALIZING_ENV", "Initializing environment block @"),
    ("08_INITIALIZING_CPU", "Initializing CPU (backend:"),
    ("09_CPU_REGISTER_SETUP", "Setting up CPU registers"),
    ("10_BOOT_CONTEXT_READY", "Boot context ready"),
)


def boot_failure_category(text: str) -> str:
    """Only a bounded source-relevant enum; NEVER return the error or user path."""
    errors=[line.split("Boot failed:",1)[1].strip().lower()
            for line in text.splitlines() if "Boot failed:" in line]
    if not errors:
        return "NO_BOOT_ERROR_OBSERVED"
    reason=errors[-1]
    if "failed to init cpu" in reason or "cpu backend" in reason or "rustarmic" in reason:
        return "GUEST_CPU_INITIALIZATION"
    if any(k in reason for k in ("failed to map", "direct-mapped", "address space", "memory region")):
        return "GUEST_ADDRESS_MAPPING"
    if "failed to write nro" in reason or "failed to write" in reason:
        return "GUEST_MEMORY_WRITE"
    if any(k in reason for k in ("open ", "mmap ", "not found", "permission denied")):
        return "SOURCE_NRO_FILE_ACCESS"
    if any(k in reason for k in ("nro", "segment", "header", "unrecognized file format")):
        return "NRO_PARSING_OR_FORMAT"
    return "OTHER_UNCLASSIFIED_BOOT_ERROR"


def collect_private_source_evidence(root: Path, console: Path) -> dict:
    """Read real Nexium data_root logs and guest SD; return only nonprivate booleans/counts."""
    text_parts=[console.read_text(encoding="utf-8",errors="replace")]
    logs=root/"nexium-data"/"logs"
    if logs.is_dir():
        text_parts.extend(f.read_text(encoding="utf-8",errors="replace")
                          for f in sorted(logs.glob("nexium-*.log")) if f.is_file())
    text="\n".join(text_parts)
    guest_root=root/"nexium-data"/"sdmc"/"switch"/"vandal-hearts-remake"
    found=sum(1 for f in guest_root.rglob("*") if f.is_file() and f.stat().st_size>0)
    return {
        "auto_loaded_nro":"Auto-loaded NRO:" in text,
        "failed_load_nro":"Failed to load NRO:" in text,
        "booting_nro":"Booting NRO:" in text,
        "boot_failed":"Boot failed:" in text,
        "cpu_memory_policy":"cpu memory null policy:" in text,
        "kernel_boot_phases":[name for name,marker in SOURCE_KERNEL_BOOT_PHASES
                              if marker in text],
        "boot_failure_category":boot_failure_category(text),
        "guest_files":found,
    }


def run_mode(exe: Path, nro: Path, mode: str, seconds: int, window_helper: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="stage36-original-vh-homebrew-") as temp:
        root=Path(temp)
        home=root/"home"
        home.mkdir()
        env=dict(os.environ)
        env.update({
            "HOME":str(home), "XDG_CONFIG_HOME":str(root/"config"),
            "XDG_DATA_HOME":str(root/"data"),
            # The real pinned nexium-common::paths::data_root() honors this,
            # and FileLogger writes under NEXIUM_DATA_ROOT/logs.
            "NEXIUM_DATA_ROOT":str(root/"nexium-data"),
            "NEXIUM_LOG_LEVEL":"info",
            "NEXIUM_LOG_TRACE_TARGETS":("nexium_runner::boot" if mode==MODES[2] else ""),
            "NEXIUM_MACOS_NO_AUDIO":"1",
            "NEXIUM_MACOS_MINIMAL_EFRAME":"0",
            "NEXIUM_MACOS_FULL_INIT_MINIMAL_APP":"0",
            "NEXIUM_MACOS_HORIZON_CTOR_ONLY":"0",
            "NEXIUM_MACOS_SKIP_SDL3_INPUT":"0",
            "NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT":"1",
            "NEXIUM_CPU_BACKEND":"rustarmic" if mode in (MODES[1],MODES[2]) else "dynarmic",
            "RUST_BACKTRACE":"0",
        })
        argv=[str(exe)]+([str(nro)] if mode!=MODES[3] else [])
        private=root/"console-private.txt"
        with private.open("wb") as log:
            proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, env=env, cwd=root,
                                  start_new_session=True)
            try:
                time.sleep(seconds)
                alive=proc.poll() is None
                own=False
                if alive and window_helper.is_file():
                    window=subprocess.run([str(window_helper),str(proc.pid)],
                        capture_output=True,text=True,timeout=6,check=False)
                    own=window.returncode==0 and window.stdout.strip().isdigit() \
                        and int(window.stdout.strip())>0
                status=proc.returncode
            finally:
                if proc.poll() is None:
                    try: os.killpg(proc.pid,signal.SIGTERM)
                    except (ProcessLookupError,PermissionError): proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
        original=collect_private_source_evidence(root,private)
        state={
            "alive_at_deadline":alive,
            "window_found":own,
            "exit_signal":("SIGABRT" if status==-signal.SIGABRT else None),
            "exited_nonzero":status is not None and status!=0,
            **original,
        }
        return sanitize(mode,state)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--nro",type=Path,required=True)
    parser.add_argument("--window-helper",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seconds",type=int,default=12)
    args=parser.parse_args(argv)
    try:
        if platform.system()!="Darwin" or platform.machine()!="x86_64":
            raise ValueError("native macOS Intel mandatory")
        if not 5<=args.seconds<=30:
            raise ValueError("seconds must be 5..30")
        exe=args.exe.resolve()
        nro=args.nro.resolve()
        validate_source(exe,nro)
        data={m:run_mode(exe,nro,m,args.seconds,args.window_helper) for m in MODES}
        result={
            "schema":"nexium-stage36-original-vh-homebrew-cli-nro/v3",
            "result":"FOUR_AUTHENTIC_NATIVE_MAC_GUI_BACKEND_AND_SVC_PATHS_RECORDED",
            "source_mac_intel_ci_run":SOURCE_MAC_RUN,
            "source_original_game_nro_ci_run":SOURCE_GAME_RUN,
            "source_guest_nro_is_diagnostic_homebrew_not_commercial_rom":True,
            "modes":data,
            "gameplay_verified":False,
            "switch_hardware_audio_verified":False,
            "guest_boot_success_not_implied_by_process_survival":True,
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps(result,sort_keys=True))
    except (OSError,ValueError,subprocess.SubprocessError) as e:
        print("STAGE36_SOURCE_BOUND_GUEST_STARTUP_BLOCKED: "+str(e),file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
