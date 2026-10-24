#!/usr/bin/env python3
"""Stage68: attempt original public libnx Framebuffer calls in integrated Intel NeXium.

Runs a *real* guest NRO, not synthetic marker bytes or guest memory injection.
Audits only original guest OutputDebugString markers and private PID-bound
macOS-window observations; no raw logs or images leave the disposable runner.

A returned framebufferEnd() call is not proof of guest GPU presentation or
correct graphics. Expected unsupported guest services are reported as specific
failure stages, not silently converted into rendering success.
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
import tarfile
import tempfile

from audit_guest_framebuffer_build import validate_compiled_public_probe
from classify_intel_guest_graphics_boot import inspect_original_graphics_boot
from classify_guest_display_ipc_path import inspect_guest_display_ipc_path
from audit_intel_pr_stack import audit_snapshot, collect_live
from build_intel_merged_tree import (
    compile_native_intel, compute_virtual_tree, extract_virtual_source,
    validate_intel_host,
)
from observe_intel_integrated_window import inspect_gui_evidence, read_bounded_json
from probe_intel_integrated_guest import probe_environment
from rehearse_intel_pr_merge import git
from test_intel_integrated_tree import execute_integrated_tests

MARKER_PREFIX = "OutputDebugString: "
PROGRESS_MARKERS = (
    "STAGE67_GUEST_GRAPHICS_START",
    "STAGE67_GUEST_DEFAULT_WINDOW_OBTAINED",
    "STAGE67_GUEST_FRAMEBUFFER_CREATED",
    "STAGE67_GUEST_LINEAR_BUFFER_READY",
    "STAGE67_GUEST_CHECKERBOARD_A_WRITTEN",
    "STAGE67_GUEST_FRAME_A_PRESENTED_CALL_RETURNED",
    "STAGE67_GUEST_CHECKERBOARD_B_WRITTEN",
    "STAGE67_GUEST_FRAME_B_PRESENTED_CALL_RETURNED",
    "STAGE67_GUEST_FOUR_FRAMEBUFFER_CALLS_COMPLETE",
)
FAILURE_MARKERS = (
    "STAGE67_GUEST_WINDOW_UNAVAILABLE",
    "STAGE67_GUEST_FRAMEBUFFER_CREATE_FAILED",
    "STAGE67_GUEST_FRAMEBUFFER_LINEAR_FAILED",
    "STAGE67_GUEST_APPLET_EXIT_BEFORE_FRAMES",
    "STAGE67_GUEST_FRAMEBUFFER_BEGIN_FAILED",
)
GUEST_LOG_MAX = 4 * 1024 * 1024
EXPECTED_NRO_MAX = 2 * 1024 * 1024

SAFE_FAILURE_PHASES = frozenset({
    "validate_intel_host", "validate_public_guest_nro",
    "audit_reviewed_pr_stack", "build_virtual_merge",
    "extract_virtual_source", "integrated_python_tests",
    "compile_native_intel", "run_original_graphics_guest",
    "inspect_original_graphics_boot", "inspect_guest_display_ipc_path",
    "audit_original_guest_progress", "inspect_owned_window_evidence",
    "verify_checkout_head", "emit_runtime_report",
})


def safe_runtime_blocked_marker(phase: str, error: BaseException) -> str:
    """Emit only a fixed phase and broad exception category, never exception text."""
    safe_phase = phase if phase in SAFE_FAILURE_PHASES else "unknown"
    if isinstance(error, subprocess.TimeoutExpired):
        reason = "TimeoutExpired"
    elif isinstance(error, tarfile.TarError):
        reason = "TarError"
    elif isinstance(error, UnicodeError):
        reason = "UnicodeError"
    elif isinstance(error, OSError):
        reason = "OSError"
    elif isinstance(error, ValueError):
        reason = "ValueError"
    elif isinstance(error, KeyError):
        reason = "KeyError"
    elif isinstance(error, TypeError):
        reason = "TypeError"
    else:
        reason = "OtherError"
    return (
        "STAGE68_GUEST_GRAPHICS_RUNTIME_BLOCKED "
        f"phase={safe_phase} reason={reason}"
    )

# The guest C source dictates which progress prefix may immediately precede
# each terminal error. This makes impossible success/failure combinations
# fail closed rather than merely accepting an ordered *subset* of markers.
FAILURE_PREFIX_LENGTHS = {
    "STAGE67_GUEST_WINDOW_UNAVAILABLE": frozenset({1}),
    "STAGE67_GUEST_FRAMEBUFFER_CREATE_FAILED": frozenset({2}),
    "STAGE67_GUEST_FRAMEBUFFER_LINEAR_FAILED": frozenset({3}),
    "STAGE67_GUEST_APPLET_EXIT_BEFORE_FRAMES": frozenset({4, 6, 8}),
    "STAGE67_GUEST_FRAMEBUFFER_BEGIN_FAILED": frozenset({4, 6, 8}),
}


def source_graphics_audit(
    report: Path, binary_sha: str, nro_sha: str, *,
    emit_progress_diagnostic: bool = False,
) -> dict:
    """Audit guest markers separately from the lifetime of the host emulator."""
    smoke = read_bounded_json(report / "smoke_result.json")
    if smoke.get("emulator_sha256") != binary_sha or smoke.get("nro_sha256") != nro_sha:
        raise ValueError("source-bound guest graphic identity mismatch")
    if smoke.get("status") not in (
        "exited_zero_unverified", "exited_nonzero", "timeout_alive_unverified"
    ):
        raise ValueError("original libnx guest process did not launch correctly")
    if smoke.get("gameplay_verified") is not False:
        raise ValueError("guest smoke made an unsupported gameplay assertion")

    logs = report / "data-root" / "logs"
    found = sorted(logs.glob("nexium-*.log")) if logs.is_dir() else []
    if len(found) != 1 or found[0].is_symlink() or not found[0].is_file():
        raise ValueError("exactly one private original guest FileLogger required")
    if found[0].stat().st_size > GUEST_LOG_MAX:
        raise ValueError("original guest log exceeded bounded audit budget")
    text = found[0].read_text(encoding="utf-8", errors="replace")
    hits = []
    for line in text.splitlines():
        if MARKER_PREFIX not in line:
            continue
        marker = line.split(MARKER_PREFIX, 1)[1].strip()
        if marker in PROGRESS_MARKERS or marker in FAILURE_MARKERS:
            hits.append(marker)
    positive = [p for p in PROGRESS_MARKERS if p in hits]
    failure = [p for p in FAILURE_MARKERS if p in hits]
    expected = list(PROGRESS_MARKERS[:len(positive)])
    if emit_progress_diagnostic:
        diagnostic = {
            "schema": "nexium-stage73-original-guest-progress/v2",
            "original_guest_progress_markers": len(positive),
            "last_original_guest_marker": hits[-1] if hits else None,
            "first_marker_is_graphics_start": bool(hits and hits[0] == PROGRESS_MARKERS[0]),
            "ordered_progress_prefix_valid": positive == expected,
            "duplicate_marker_observed": len(hits) != len(set(hits)),
            "marker_sequence_exact": hits == positive + failure,
            "failure_marker_count": len(failure),
            "emulator_process_status": smoke["status"],
            "guest_exit_status_observed": False,
            "raw_logs_uploaded": False,
        }
        print("STAGE73_ORIGINAL_GUEST_PROGRESS_DIAGNOSTIC "
              + json.dumps(diagnostic, sort_keys=True), flush=True)
    if not hits or hits[0] != PROGRESS_MARKERS[0]:
        raise ValueError("original libnx graphics guest start was not observed")
    if len(hits) != len(set(hits)):
        raise ValueError("duplicate original guest graphics output marker")
    if len(failure) > 1:
        raise ValueError("ambiguous guest graphics terminal failure markers")
    # Every progress marker prior to the last observed one must be present,
    # and the exact serialized original guest event order must hold.
    if positive != expected:
        raise ValueError("original guest graphics markers skip expected stages")
    if hits != positive + failure:
        raise ValueError("original guest graphics markers in impossible order")
    if failure and PROGRESS_MARKERS[-1] in positive:
        raise ValueError("successful and failed terminal graphics states overlap")
    status = smoke.get("status")
    if failure:
        name = failure[0]
        if len(positive) not in FAILURE_PREFIX_LENGTHS[name]:
            raise ValueError("guest framebuffer failure impossible at observed API stage")
        # These are guest-originated OutputDebugString markers. The smoke
        # status belongs to the host emulator process and cannot veto or
        # confirm the guest's framebuffer failure state.
        classified = "explicit_guest_framebuffer_failure"
    elif PROGRESS_MARKERS[-1] in positive:
        # The last guest marker is emitted after framebufferClose and all
        # framebuffer API calls. It does not prove GPU presentation or the
        # guest's actual return status, and the emulator may remain alive.
        classified = "all_guest_framebuffer_api_calls_returned"
    elif status == "timeout_alive_unverified":
        # The emulator is still alive and the guest emitted only a partial
        # marker prefix. This is diagnostic only, never a rendering pass.
        classified = "partial_guest_progress_timeout_unverified"
    else:
        # The host emulator exited before the guest's terminal marker. Do not
        # infer a guest exit code or turn incomplete evidence into a hard error.
        classified = "partial_guest_progress_emulator_exited_without_terminal_marker"
    api_calls_complete = PROGRESS_MARKERS[-1] in positive
    emulator_status = status
    return {
        "schema": "nexium-stage68-original-guest-framebuffer-markers/v2",
        "original_libnx_graphics_guest_started": True,
        "original_guest_progress_markers": len(positive),
        "graphics_guest_runtime_classification": classified,
        "guest_framebuffer_runtime_completed": api_calls_complete,
        "guest_framebuffer_api_calls_completed_observed": api_calls_complete,
        "emulator_process_timeout_unverified": (
            emulator_status == "timeout_alive_unverified"
        ),
        "guest_exit_status": "not_observed",
        "emulator_process_status": emulator_status,
        "last_original_guest_marker": hits[-1],
        "original_guest_failure_marker": failure[0] if failure else None,
        "guest_framebuffer_created_observed":
            "STAGE67_GUEST_FRAMEBUFFER_CREATED" in positive,
        "guest_framebuffer_end_call_returned_observed":
            "STAGE67_GUEST_FRAME_B_PRESENTED_CALL_RETURNED" in positive,
        "guest_framebuffer_api_loop_complete_observed": api_calls_complete,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "physical_controller_verified": False,
    }


def run_graphics_guest(source: Path, binary: Path, nro: Path, report: Path) -> None:
    command = [
        sys.executable, str(source / "scripts" / "nro_smoke_test.py"),
        "--exe", str(binary), "--nro", str(nro), "--output", str(report),
        "--seconds", "25", "--snapshot-ms", "5000", "--capture-window",
    ]
    env = probe_environment(dict(os.environ))
    # Keep normal DEBUG logging. Stage73 elevates only the single IPC-request
    # log call in the disposable build, avoiding global per-SVC TRACE flooding.
    env["NEXIUM_LOG_LEVEL"] = "debug"
    # Same original NeXium startup profile as the proven Stage65 diagnostic,
    # but the analog-input deadzone stimulus is not a graphics prerequisite.
    env["NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE"] = "0"
    try:
        child = subprocess.run(
            command, cwd=source, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=48,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("original graphics NRO smoke harness exceeded budget") from None
    # This child return code belongs to the smoke harness/host emulator, not
    # to the guest NRO. Guest framebuffer failures are classified only from
    # authenticated private guest markers in source_graphics_audit().
    if child.returncode not in (0, 2):
        raise ValueError("original graphics NRO smoke harness failed unexpectedly")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--top-pr", type=int, required=True)
    parser.add_argument("--min-depth", type=int, default=36)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--git-repo", required=True, type=Path)
    parser.add_argument("--guest-nro", required=True, type=Path)
    parser.add_argument("--guest-source", required=True, type=Path)
    args = parser.parse_args(argv)
    phase = "validate_intel_host"
    try:
        intel = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        validate_intel_host(
            platform.system(), platform.machine(),
            intel.returncode == 0 and intel.stdout.strip() == "1",
        )
        # Reject symlinks on caller paths BEFORE making absolute.
        phase = "validate_public_guest_nro"
        compiled = validate_compiled_public_probe(args.guest_nro, args.guest_source)
        nro = args.guest_nro.absolute()
        phase = "audit_reviewed_pr_stack"
        snapshot = collect_live(
            args.repository, os.environ.get("GH_TOKEN", ""), top_pr=args.top_pr,
        )
        audit_snapshot(snapshot, top_pr=args.top_pr,
                       expected_head_sha=args.expected_head_sha,
                       min_depth=args.min_depth)
        heads = {x["head"]: x for x in snapshot["pulls"]}
        node = next(p for p in snapshot["pulls"] if p["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(node)
            if node["base"] == "main":
                break
            node = heads[node["base"]]
        ordered.reverse()
        phase = "build_virtual_merge"
        combined = compute_virtual_tree(
            args.git_repo, snapshot["main_sha"], ordered,
            args.expected_head_sha,
        )
        print("STAGE68_GATE_REVIEWED_VIRTUAL_MERGE_PASS", flush=True)
        with tempfile.TemporaryDirectory(prefix="nexium-graphics-original-") as tmp:
            root = Path(tmp)
            src, work, report = root / "source", root / "native", root / "report"
            src.mkdir()
            work.mkdir()
            phase = "extract_virtual_source"
            files = extract_virtual_source(args.git_repo, combined, src)
            phase = "integrated_python_tests"
            tests = execute_integrated_tests(src, min_tests=497)
            print("STAGE68_GATE_INTEGRATED_PYTHON_PASS", flush=True)
            build_env = dict(os.environ)
            build_env["NEXIUM_DISPLAY_IPC_TRACE"] = "1"
            phase = "compile_native_intel"
            intel_binary = compile_native_intel(
                src, work,
                host_system=platform.system(), host_arch=platform.machine(),
                apple_arm_capable=False, base_env=build_env,
            )
            print("STAGE68_GATE_REAL_INTEL_MACHO_PASS", flush=True)
            if intel_binary.get("display_ipc_trace_patch_applied") is not True:
                raise ValueError("Stage73 scoped IPC request log patch not bound to Intel build")
            print("STAGE73_SCOPED_IPC_REQUEST_LOG_PATCH_VERIFIED", flush=True)
            binary = work / "nexium" / "target" / "x86_64-apple-darwin" / "release" / "nexium"
            guest_run_error = None
            phase = "run_original_graphics_guest"
            try:
                run_graphics_guest(src, binary, nro, report)
            except (OSError, ValueError, KeyError, TypeError, UnicodeError,
                    subprocess.TimeoutExpired, tarfile.TarError) as error:
                guest_run_error = error
            finally:
                # Print ONLY pre-allowlisted original boot category and booleans.
                # The raw emulator console, FileLogger and PNGs remain private.
                if (report / "smoke_result.json").is_file():
                    phase = "inspect_original_graphics_boot"
                    boot = inspect_original_graphics_boot(
                        report, intel_binary["native_macho_sha256"],
                        compiled["nro_sha256"],
                    )
                    print("STAGE71_ORIGINAL_GRAPHICS_BOOT_DIAGNOSTIC "
                          + json.dumps(boot, sort_keys=True), flush=True)
                    phase = "inspect_guest_display_ipc_path"
                    try:
                        ipc = inspect_guest_display_ipc_path(
                            report, intel_binary["native_macho_sha256"],
                            compiled["nro_sha256"],
                        )
                        print("STAGE73_GUEST_DISPLAY_IPC_DIAGNOSTIC "
                              + json.dumps(ipc, sort_keys=True), flush=True)
                    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
                        print("STAGE73_GUEST_DISPLAY_IPC_DIAGNOSTIC_BLOCKED",
                              flush=True)
                else:
                    print("STAGE71_ORIGINAL_GRAPHICS_SMOKE_RECEIPT_UNAVAILABLE",
                          flush=True)
                    print("STAGE73_GUEST_DISPLAY_IPC_RECEIPT_UNAVAILABLE",
                          flush=True)
            if guest_run_error is not None:
                phase = "run_original_graphics_guest"
                raise guest_run_error
            phase = "audit_original_guest_progress"
            guest = source_graphics_audit(
                report, intel_binary["native_macho_sha256"], compiled["nro_sha256"],
                emit_progress_diagnostic=True,
            )
            print("STAGE68_GATE_ORIGINAL_GUEST_MARKER_SEQUENCE_AUDITED", flush=True)
            phase = "inspect_owned_window_evidence"
            pixels = inspect_gui_evidence(
                report, intel_binary["native_macho_sha256"], compiled["nro_sha256"],
                allow_nonzero_guest=True,
            )
        phase = "verify_checkout_head"
        check = git(args.git_repo, "rev-parse", "HEAD")
        if check.returncode != 0 or check.stdout.strip() != args.expected_head_sha:
            raise ValueError("original checked out Git HEAD changed")
        phase = "emit_runtime_report"
        print(json.dumps({
            "schema": "nexium-stage68-integrated-original-guest-graphics/v1",
            "stacked_draft_prs": len(ordered),
            "merged_source_files": files,
            **tests,
            **guest,
            **pixels,
            "native_macho_sha256": intel_binary["native_macho_sha256"],
            "public_graphics_nro_sha256": compiled["nro_sha256"],
            "source_bound_graphics_nro_observed": True,
            "remote_ref_changed": False,
            "main_merge_approved": False,
            "production_graphics_verified": False,
            "human_integration_review_required": True,
        }, sort_keys=True))
        print("STAGE68_GUEST_GRAPHICS_RUNTIME_DIAGNOSTIC_PASS_NOT_GPU_CERTIFICATION")
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError,
            subprocess.TimeoutExpired, tarfile.TarError) as error:
        print(safe_runtime_blocked_marker(phase, error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
