#!/usr/bin/env python3
"""Stage66: classify NeXium-owned GUI window evidence after actual libnx readback.

Visual telemetry is NOT proof of correct guest GPU rendering, game frames,
production quality, graphics/audio accuracy, or commercial-game support.
Screenshots and raw process logs never leave the disposable CI runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile

from audit_intel_pr_stack import audit_snapshot, collect_live
from build_intel_merged_tree import (
    compile_native_intel, compute_virtual_tree, extract_virtual_source,
    validate_intel_host,
)
from capture_macos_window import png_dimensions
from probe_intel_integrated_guest import (
    run_integrated_guest, validate_public_probe,
)
from rehearse_intel_pr_merge import git
from test_intel_integrated_tree import execute_integrated_tests
from stage73_safe_evidence_read import read_bounded_regular_bytes

MAX_JSON_BYTES = 128 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 64
FRAME_NAME_RE = re.compile(r"^emulator-window-[0-9]{3}\.png$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VALID_STATUSES = ("timeout_alive_unverified", "exited_zero_unverified")


def reject_duplicates(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate GUI evidence property")
        record[key] = value
    return record


def read_bounded_json(path: Path) -> dict:
    raw = read_bounded_regular_bytes(path, MAX_JSON_BYTES)
    record = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite GUI JSON")),
    )
    if not isinstance(record, dict):
        raise ValueError("GUI evidence must be an object")
    return record


def inspect_gui_evidence(report_dir: Path, expected_macho_sha: str,
                         expected_nro_sha: str,
                         *, allow_nonzero_guest: bool = False) -> dict:
    """Report verified own-window pixels separately from guest source proof."""
    if (not SHA256_RE.fullmatch(expected_macho_sha)
            or not SHA256_RE.fullmatch(expected_nro_sha)):
        raise ValueError("invalid expected binary identity")
    smoke = read_bounded_json(report_dir / "smoke_result.json")
    if (smoke.get("emulator_sha256") != expected_macho_sha
            or smoke.get("nro_sha256") != expected_nro_sha):
        raise ValueError("GUI capture not bound to current integrated binary and NRO")
    allowed = VALID_STATUSES
    # A public graphics probe may intentionally exit nonzero when NeXium
    # lacks a guest framebuffer service. Stage68 separately requires actual
    # guest OutputDebugString state proof before enabling this exception.
    if allow_nonzero_guest is True:
        allowed = (*allowed, "exited_nonzero")
    elif allow_nonzero_guest is not False:
        raise ValueError("GUI observation mode must be Boolean")
    if (smoke.get("status") not in allowed
            or smoke.get("gameplay_verified") is not False):
        raise ValueError("GUI capture not from valid source-bound smoke run")
    capture = smoke.get("window_capture")
    if not isinstance(capture, dict) or capture.get("requested") is not True:
        raise ValueError("owned-window capture was not explicitly requested")
    path = report_dir / "window-capture" / "window_capture_result.json"
    if not path.is_file():
        if capture.get("frames") != 0:
            raise ValueError("missing detailed report for reported frames")
        return {
            "schema": "nexium-intel-own-window-observation/v1",
            "observation": "no_capture_report",
            "owned_window_frames": 0,
            "unique_owned_window_hashes": 0,
            "owned_window_visible_observed": False,
            "window_frame_changes_observed": False,
            "guest_gpu_frames_verified": False,
            "commercial_gameplay_verified": False,
            "physical_controller_verified": False,
            "raw_frames_uploaded": False,
            "main_merge_approved": False,
        }

    details = read_bounded_json(path)
    if details.get("capture_type") != "macos_pid_owned_window_only":
        raise ValueError("window capture was not restricted to NeXium PID")
    smoke_pid, capture_pid = smoke.get("emulator_pid"), details.get("pid")
    if (type(smoke_pid) is not int or smoke_pid <= 0
            or type(capture_pid) is not int or capture_pid != smoke_pid):
        raise ValueError("window capture PID not bound to exact smoke process")
    frames = details.get("frames")
    if not isinstance(frames, list) or len(frames) > MAX_FRAMES:
        raise ValueError("unbounded GUI frame collection")
    if capture.get("frames") != len(frames):
        raise ValueError("smoke and PID-bound window frame counts disagree")
    hashes = set()
    seen = set()
    frame_dir = path.parent
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("invalid owned-window frame record")
        name, claimed, dimensions, size = (
            frame.get("file"), frame.get("sha256"),
            frame.get("dimensions"), frame.get("bytes"),
        )
        if (not isinstance(name, str) or not FRAME_NAME_RE.fullmatch(name)
                or name in seen or not isinstance(claimed, str)
                or not SHA256_RE.fullmatch(claimed)
                or type(size) is not int or not 24 <= size <= MAX_PNG_BYTES
                or not isinstance(dimensions, list) or len(dimensions) != 2
                or any(type(x) is not int or not 100 <= x <= 8192 for x in dimensions)):
            raise ValueError("malformed owned-window image metadata")
        seen.add(name)
        file = frame_dir / name
        if file.is_symlink() or not file.is_file() or file.stat().st_size != size:
            raise ValueError("owned-window image missing, changed or linked")
        if png_dimensions(file) != dimensions:
            raise ValueError("owned-window PNG dimensions differ from capture")
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != claimed:
            raise ValueError("owned-window PNG digest differs from capture")
        hashes.add(digest)
    if (capture.get("unique_hashes") != len(hashes)
            or details.get("unique_hashes") != len(hashes)):
        raise ValueError("owned-window frame uniqueness counts inconsistent")
    visible = bool(frames)
    changing = len(hashes) >= 2
    return {
        "schema": "nexium-intel-own-window-observation/v1",
        "observation": (
            "owned_window_frames_changed" if changing else
            "owned_window_static_frame" if visible else
            "no_owned_window_frames"
        ),
        "owned_window_frames": len(frames),
        "unique_owned_window_hashes": len(hashes),
        "owned_window_visible_observed": visible,
        "window_frame_changes_observed": changing,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "physical_controller_verified": False,
        "raw_frames_uploaded": False,
        "main_merge_approved": False,
    }


def run_observation(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repository", required=True)
    ap.add_argument("--top-pr", type=int, required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--min-depth", type=int, default=35)
    ap.add_argument("--git-repo", type=Path, required=True)
    ap.add_argument("--guest-nro", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        intel = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"],
            text=True, capture_output=True, timeout=10, check=False,
        )
        validate_intel_host(
            platform.system(), platform.machine(),
            intel.returncode == 0 and intel.stdout.strip() == "1",
        )
        validate_public_probe(args.guest_nro)
        nro = args.guest_nro.absolute()
        validate_public_probe(nro)
        snapshot = collect_live(
            args.repository, os.environ.get("GH_TOKEN", ""), top_pr=args.top_pr,
        )
        audit_snapshot(
            snapshot, top_pr=args.top_pr, expected_head_sha=args.expected_head_sha,
            min_depth=args.min_depth,
        )
        by_head = {p["head"]: p for p in snapshot["pulls"]}
        node = next(p for p in snapshot["pulls"] if p["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(node)
            if node["base"] == "main":
                break
            node = by_head[node["base"]]
        ordered.reverse()
        combined = compute_virtual_tree(
            args.git_repo, snapshot["main_sha"], ordered, args.expected_head_sha
        )
        print("STAGE66_GATE_LIVE_MERGE_PASSED", flush=True)
        with tempfile.TemporaryDirectory(prefix="nexium-integrated-gui-") as temp:
            root = Path(temp)
            source, native, report = root/"source", root/"native", root/"private-guest"
            source.mkdir()
            native.mkdir()
            extracted = extract_virtual_source(args.git_repo, combined, source)
            test_result = execute_integrated_tests(source, min_tests=481)
            print("STAGE66_GATE_INTEGRATED_PYTHON_PASSED", flush=True)
            built = compile_native_intel(
                source, native,
                host_system=platform.system(), host_arch=platform.machine(),
                apple_arm_capable=False, base_env=dict(os.environ),
            )
            print("STAGE66_GATE_NATIVE_INTEL_MACHO_PASSED", flush=True)
            binary = native/"nexium"/"target"/"x86_64-apple-darwin"/"release"/"nexium"
            guest = run_integrated_guest(
                source=source, binary=binary, guest_nro=nro, report_dir=report,
                repository_sha=args.expected_head_sha,
                run_id=os.environ["GITHUB_RUN_ID"],
                base_env=dict(os.environ),
                capture_window=True,
            )
            if guest.get("native_macho_sha256") != built["native_macho_sha256"]:
                raise ValueError("GUI observer and guest ran different native Mach-O")
            print("STAGE66_GATE_SOURCE_BOUND_GUEST_REPLAY_PASSED", flush=True)
            visual = inspect_gui_evidence(
                report, built["native_macho_sha256"], guest["public_guest_nro_sha256"]
            )
        after = git(args.git_repo, "rev-parse", "HEAD")
        if after.returncode != 0 or after.stdout.strip() != args.expected_head_sha:
            raise ValueError("real source Git checkout changed")
        result = {
            "schema": "nexium-stage66-integrated-intel-window-observation/v1",
            "stacked_draft_prs": len(ordered),
            "merged_source_files": extracted,
            **test_result,
            "same_integrated_native_guest_readback_passed":
                guest["same_integrated_intel_macho_and_original_guest_nro_verified"],
            "source_bound_triplet_replay_passed": guest["source_bound_triplet_replay_passed"],
            "native_macho_sha256": guest["native_macho_sha256"],
            **visual,
            "remote_ref_changed": False,
            "human_integration_review_required": True,
            "production_release_verified": False,
        }
        print(json.dumps(result, sort_keys=True))
        print("STAGE66_WINDOW_OBSERVATION_REPORTED_GUEST_PROOF_PASS")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.TimeoutExpired, tarfile.TarError):
        print("STAGE66_INTEGRATED_GUI_OBSERVATION_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(run_observation())
