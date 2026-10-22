#!/usr/bin/env python3
"""Stage71: fixed-vocabulary NeXium guest graphics boot diagnostics.

Classify ORIGINAL isolated FileLogger boot milestones when the compiled
public libnx graphics NRO cannot yet reach the framebuffer marker auditor.
Do not emit raw logs, filesystem paths, images, firmware or user data.
This is not guest graphics, boot, or application compatibility certification.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from observe_intel_integrated_window import read_bounded_json

MAX_LOG_BYTES = 4 * 1024 * 1024
SMOKE_STATES = frozenset({
    "exited_zero_unverified", "exited_nonzero",
    "timeout_alive_unverified", "launch_failed",
})
BOOT_EVIDENCE = {
    "original_nro_autoload_observed": "Auto-loaded NRO:",
    "original_guest_boot_started_observed": "Booting NRO:",
    "original_guest_context_ready_observed": "cpu memory null policy:",
    "original_guest_boot_failure_observed": "Boot failed:",
    "original_svc_debug_record_observed": "svcOutputDebugString",
    "original_graphics_svc_start_observed":
        "OutputDebugString: STAGE67_GUEST_GRAPHICS_START",
}


def inspect_original_graphics_boot(report: Path, macho_sha: str,
                                   nro_sha: str) -> dict:
    receipt = read_bounded_json(report / "smoke_result.json")
    if receipt.get("emulator_sha256") != macho_sha or receipt.get("nro_sha256") != nro_sha:
        raise ValueError("original graphics boot receipt binary/NRO mismatch")
    state = receipt.get("status")
    if state not in SMOKE_STATES or receipt.get("gameplay_verified") is not False:
        raise ValueError("original graphics boot receipt state untrusted")
    log_dir = report / "data-root" / "logs"
    paths = sorted(log_dir.glob("nexium-*.log")) if log_dir.is_dir() else []
    if len(paths) > 1:
        raise ValueError("ambiguous original guest FileLogger isolation")
    data = ""
    if paths:
        log = paths[0]
        if log.is_symlink() or not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
            raise ValueError("original guest FileLogger unsafe")
        data = log.read_text(encoding="utf-8", errors="replace")
    evidence = {name: bool(token in data) for name, token in BOOT_EVIDENCE.items()}
    if not paths:
        category = "original_filelogger_unavailable"
    elif evidence["original_guest_boot_failure_observed"]:
        category = "original_guest_boot_failed"
    elif not evidence["original_nro_autoload_observed"]:
        category = "nro_autoload_not_observed"
    elif not evidence["original_guest_boot_started_observed"]:
        category = "original_guest_boot_not_observed"
    elif not evidence["original_guest_context_ready_observed"]:
        category = "original_guest_context_not_observed"
    elif not evidence["original_graphics_svc_start_observed"]:
        category = "graphics_guest_svc_start_not_observed"
    else:
        category = "graphics_guest_svc_start_observed"
    return {
        "schema": "nexium-stage71-original-graphics-boot/v1",
        "observed_category": category,
        "probe_process_status": state,
        "isolated_original_filelogger_count": len(paths),
        **evidence,
        "guest_framebuffer_runtime_completed": False,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "physical_controller_verified": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--macho-sha256", required=True)
    parser.add_argument("--nro-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_original_graphics_boot(
            args.report_dir, args.macho_sha256, args.nro_sha256
        )
        print(json.dumps(result, sort_keys=True))
        print("STAGE71_PRIVATE_GUEST_BOOT_OBSERVATION_NOT_GRAPHICS_PASS")
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        print("STAGE71_GRAPHICS_BOOT_EVIDENCE_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
