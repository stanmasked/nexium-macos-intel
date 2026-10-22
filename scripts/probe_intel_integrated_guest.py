#!/usr/bin/env python3
"""Stage65: real libnx guest readback on the *same* virtual-merged Intel binary.

The input NRO is public, compiled from our probe source on this same PR.
Original NeXium guest runtime uses its authentic SDL3/HidState/NPad pipeline;
no guest-memory injection. All raw output, snapshots and binaries stay within
one disposable runner directory and are never uploaded. All Git refs unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile

from audit_guest_deadzone_threshold import audit as audit_deadzone
from audit_intel_controller_proof_manifest import (
    PINNED_UPSTREAM, audit as build_manifest,
)
from audit_intel_controller_proof_structure import (
    _identity, audit_structure, validate_nro,
)
from audit_intel_pr_stack import audit_snapshot, collect_live
from build_intel_merged_tree import (
    compile_native_intel, compute_virtual_tree, extract_virtual_source,
    native_environment, validate_intel_host,
)
from rehearse_intel_pr_merge import git
from test_intel_integrated_tree import execute_integrated_tests
from verify_intel_controller_proof_manifest import verify as replay_manifest

GUEST_PROBE_ENV = {
    "NEXIUM_CPU_BACKEND": "rustarmic",
    "NEXIUM_MACOS_NO_AUDIO": "1",
    "NEXIUM_MACOS_MINIMAL_EFRAME": "0",
    "NEXIUM_MACOS_FULL_INIT_MINIMAL_APP": "0",
    "NEXIUM_MACOS_HORIZON_CTOR_ONLY": "0",
    "NEXIUM_MACOS_SKIP_SDL3_INPUT": "0",
    "NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT": "1",
    "NEXIUM_MACOS_INPUT_POLL_TRACE": "1",
    "NEXIUM_MACOS_VIRTUAL_BUTTON_TEST": "1",
    "NEXIUM_MACOS_GUEST_HID_PROBE": "1",
    "NEXIUM_MACOS_GUEST_AB_PROBE": "0",
    "NEXIUM_MACOS_GUEST_DPAD_PROBE": "0",
    "NEXIUM_MACOS_GUEST_STICK_X_PROBE": "0",
    "NEXIUM_MACOS_GUEST_STICK_Y_PROBE": "0",
    "NEXIUM_MACOS_GUEST_RIGHT_X_PROBE": "0",
    "NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE": "0",
    "NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE": "0",
    "NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE": "0",
    "NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE": "1",
    "NEXIUM_MACOS_STAGE37_HID_BRIDGE_TRACE": "1",
    "NEXIUM_HID_TRACE": "1",
    "NEXIUM_DIAG": "lite",
    "NEXIUM_LOG_LEVEL": "debug",
}
EXPECTED_GUEST_SCHEMA = "nexium-stage53-guest-deadzone-threshold/v1"
EXPECTED_MANIFEST_SCHEMA = "nexium-intel-controller-proof-manifest/v1"


def probe_environment(base: dict[str, str]) -> dict[str, str]:
    """Discard tokens and build-stage experiment flags from guest process."""
    scrubbed = native_environment(
        base, Path(tempfile.gettempdir()).resolve()
    )
    for key in tuple(scrubbed):
        if (key.startswith("NEXIUM_EXPERIMENT_")
                or key.startswith("NEXIUM_INTEL_INPUT_PROFILE")
                or key.startswith("NEXIUM_MAC_WORKDIR")):
            del scrubbed[key]
    scrubbed.update(GUEST_PROBE_ENV)
    return scrubbed


def validate_public_probe(nro: Path) -> int:
    if nro.suffix != ".nro" or nro.is_symlink() or not nro.is_file():
        raise ValueError("missing regular public guest NRO")
    before = _identity(nro)
    declared = validate_nro(nro)
    if before != _identity(nro):
        raise ValueError("public guest NRO changed while checking")
    return declared


def run_integrated_guest(
    *, source: Path, binary: Path, guest_nro: Path, report_dir: Path,
    repository_sha: str, run_id: str, base_env: dict[str, str],
) -> dict:
    # Check the original path before canonicalizing: symlinked inputs are
    # never accepted. The smoke harness runs from a different working directory
    # (the extracted virtual merge), so pass an absolute, still-direct path.
    validate_public_probe(guest_nro)
    guest_nro = guest_nro.absolute()
    validate_public_probe(guest_nro)
    print("STAGE65_GATE_PUBLIC_NRO_ABSOLUTE_OK", flush=True)
    if binary.is_symlink() or not binary.is_file():
        raise ValueError("integrated native Mach-O unavailable")
    before = (_identity(binary), _identity(guest_nro))
    smoke = source / "scripts/nro_smoke_test.py"
    if not smoke.is_file() or smoke.is_symlink():
        raise ValueError("original NRO smoke harness unavailable")

    env = probe_environment(base_env)
    command = [
        sys.executable, str(smoke),
        "--exe", str(binary),
        "--nro", str(guest_nro),
        "--output", str(report_dir),
        "--seconds", "80",
        "--snapshot-ms", "5000",
    ]
    try:
        run = subprocess.run(
            command, cwd=source, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=105, check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("original libnx guest readback timed out") from None
    if run.returncode != 0:
        raise ValueError("original libnx guest readback failed to start")
    print("STAGE65_GATE_ORIGINAL_NRO_SMOKE_FINISHED", flush=True)

    receipt = audit_deadzone(report_dir)
    if (receipt.get("schema") != EXPECTED_GUEST_SCHEMA
            or receipt.get("same_process_guest_deadzone_threshold_passed") is not True
            or receipt.get("physical_controller_verified") is not False
            or receipt.get("raw_logs_uploaded") is not False):
        raise ValueError("original guest deadzone audit did not pass")
    print("STAGE65_GATE_GUEST_DEADZONE_AUDIT_PASSED", flush=True)
    # Keep only pre-allowlisted source/guest observations in proof; do not
    # print or upload console logs, snapshots or private guest memory.
    receipt_path = report_dir / "stage65-sanitized-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    structures = audit_structure(binary, guest_nro, receipt_path)
    manifest = build_manifest(
        binary, guest_nro, receipt_path,
        PINNED_UPSTREAM, repository_sha, run_id,
    )
    if manifest.get("schema") != EXPECTED_MANIFEST_SCHEMA:
        raise ValueError("integrated triplet provenance schema mismatch")
    manifest_path = report_dir / "stage65-sanitized-proof.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    verified = replay_manifest(
        manifest_path, binary, guest_nro, receipt_path,
        PINNED_UPSTREAM, repository_sha, run_id,
    )
    if (verified.get("exact_triplet_replay_passed") is not True
            or structures.get("structure_audit_passed") is not True
            or before != (_identity(binary), _identity(guest_nro))):
        raise ValueError("integrated proof altered or independent replay failed")
    print("STAGE65_GATE_INDEPENDENT_TRIPLET_REPLAY_PASSED", flush=True)
    return {
        "same_integrated_intel_macho_and_original_guest_nro_verified": True,
        "original_npad_samples": receipt["original_npad_serialized_sample_count"],
        "intel_macho_load_commands": structures["intel_macho_load_commands"],
        "nro_declared_bytes": structures["nro_declared_bytes"],
        "source_bound_triplet_replay_passed": True,
        "native_macho_sha256": manifest["intel_macho_sha256"],
        "public_guest_nro_sha256": manifest["public_guest_nro_sha256"],
        "physical_controller_verified": False,
        "commercial_gameplay_verified": False,
        "real_switch_verified": False,
        "raw_logs_uploaded": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--top-pr", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--min-depth", type=int, default=34)
    parser.add_argument("--git-repo", type=Path, required=True)
    parser.add_argument("--guest-nro", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        system, arch = platform.system(), platform.machine()
        check = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        validate_intel_host(
            system, arch,
            check.returncode == 0 and check.stdout.strip() == "1",
        )
        # Check the original path before following any filesystem links.
        guest_nro = args.guest_nro
        validate_public_probe(guest_nro)
        snapshot = collect_live(
            args.repository, os.environ.get("GH_TOKEN", ""), top_pr=args.top_pr,
        )
        audit_snapshot(
            snapshot, top_pr=args.top_pr,
            expected_head_sha=args.expected_head_sha, min_depth=args.min_depth,
        )
        heads = {x["head"]: x for x in snapshot["pulls"]}
        node = next(x for x in snapshot["pulls"]
                    if x["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(node)
            if node["base"] == "main":
                break
            node = heads[node["base"]]
        ordered.reverse()
        combined = compute_virtual_tree(
            args.git_repo, snapshot["main_sha"], ordered,
            args.expected_head_sha,
        )
        print("STAGE65_GATE_LIVE_ANCESTRY_AND_VIRTUAL_MERGE_PASSED", flush=True)
        with tempfile.TemporaryDirectory(prefix="nexium-integrated-guest-") as tmp:
            root = Path(tmp)
            src, work, report = root/"source", root/"native-build", root/"guest"
            src.mkdir()
            work.mkdir()
            extracted = extract_virtual_source(args.git_repo, combined, src)
            python_suite = execute_integrated_tests(src, min_tests=450)
            print("STAGE65_GATE_VIRTUAL_PYTHON_SUITE_PASSED", flush=True)
            intel = compile_native_intel(
                src, work, host_system=system, host_arch=arch,
                apple_arm_capable=False, base_env=dict(os.environ),
            )
            print("STAGE65_GATE_NATIVE_INTEL_MACHO_VALIDATED", flush=True)
            binary = work/"nexium"/"target"/"x86_64-apple-darwin"/"release"/"nexium"
            guest = run_integrated_guest(
                source=src, binary=binary, guest_nro=guest_nro,
                report_dir=report, repository_sha=args.expected_head_sha,
                run_id=os.environ["GITHUB_RUN_ID"], base_env=dict(os.environ),
            )
            if guest["native_macho_sha256"] != intel["native_macho_sha256"]:
                raise ValueError("guest ran a different Intel binary")
        final = git(args.git_repo, "rev-parse", "HEAD")
        if final.returncode != 0 or final.stdout.strip() != args.expected_head_sha:
            raise ValueError("Git checkout changed while testing integrated guest")
        print(json.dumps({
            "schema": "nexium-stage65-integrated-intel-guest/v1",
            "linked_draft_prs": len(ordered),
            "integrated_source_files": extracted,
            **python_suite,
            "native_intel_binary_compiled": intel["native_intel_executable_compiled"],
            **guest,
            "remote_ref_changed": False,
            "main_merge_approved": False,
            "human_integration_review_required": True,
            "production_release_verified": False,
        }, sort_keys=True))
        print("STAGE65_INTEGRATED_INTEL_GUEST_READBACK_PASS")
        return 0
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired, tarfile.TarError) as exc:
        print("STAGE65_INTEGRATED_GUEST_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
