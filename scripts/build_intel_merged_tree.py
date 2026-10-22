#!/usr/bin/env python3
"""Stage64: compile the exact, reviewed virtual NeXium PR merge on native Intel.

Read-only GitHub PR API; temporary local merge objects; no changes to HEAD,
branches, tags, remote refs, source checkout, or main. The executable is
ephemeral research evidence, not a signed or certified game emulator.
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
from audit_intel_controller_proof_structure import validate_macho
from audit_intel_macho_segment_bounds import verify_segment_bounds
from rehearse_intel_pr_merge import git, valid_sha
from rehearse_intel_reviewed_conflict import REVIEWED_PR60_BLOBS, rehearsal
from test_intel_integrated_tree import (
    EXPECTED_MIN_TESTS, execute_integrated_tests, unpack_reviewed_tree,
)

PINNED_UPSTREAM_SHA = "089562567a0a8760dfdd8420e1f57c35159a9219"
MAX_BUILD_SECONDS = 4800
REQUIRED_FLAGS = (
    "NEXIUM_EXPERIMENT_AUDIO_ABLATION",
    "NEXIUM_EXPERIMENT_MINIMAL_EFRAME",
    "NEXIUM_EXPERIMENT_FULL_INIT_MINIMAL_APP",
    "NEXIUM_EXPERIMENT_HORIZON_CTOR_ONLY",
    "NEXIUM_EXPERIMENT_HORIZON_CTOR_PHASE_TRACE",
    "NEXIUM_EXPERIMENT_STAGE52_DEADZONE_JITTER",
    "NEXIUM_EXPERIMENT_STAGE53_DEADZONE_THRESHOLD",
)
# These come from the branch-neutral named source controller profile; no
# legacy per-branch 0 selectors may contradict it.
PROFILE_SELECTORS = (
    "NEXIUM_EXPERIMENT_SDL3_INPUT_ABLATION",
    "NEXIUM_EXPERIMENT_SDL3_PREWINIT",
    "NEXIUM_EXPERIMENT_INPUT_POLL_MARKERS",
    "NEXIUM_EXPERIMENT_VIRTUAL_INPUT_SNAPSHOT",
    "NEXIUM_EXPERIMENT_STAGE37_HID_BRIDGE",
    "NEXIUM_EXPERIMENT_STAGE40_GUEST_HID",
    "NEXIUM_EXPERIMENT_STAGE42_GUEST_AB",
    "NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD",
    "NEXIUM_EXPERIMENT_STAGE44_GUEST_STICK_X",
    "NEXIUM_EXPERIMENT_STAGE45_GUEST_STICK_Y",
    "NEXIUM_EXPERIMENT_STAGE46_GUEST_RIGHT_X",
    "NEXIUM_EXPERIMENT_STAGE47_GUEST_RIGHT_Y",
    "NEXIUM_EXPERIMENT_STAGE48_DUAL_STICK",
)


def validate_intel_host(system: str, arch: str, apple_arm_capable: bool) -> None:
    if system != "Darwin" or arch != "x86_64" or apple_arm_capable:
        raise ValueError("native physical Intel macOS runner required")


def native_environment(base: dict[str, str], work_dir: Path) -> dict[str, str]:
    """Strip credentials and branch-dependent experiment settings."""
    if not work_dir.is_absolute() or work_dir.is_symlink():
        raise ValueError("invalid disposable native build directory")
    env = {}
    for key, value in base.items():
        upper = key.upper()
        if ("TOKEN" in upper or "SECRET" in upper or "PASSWORD" in upper
                or "CREDENTIAL" in upper or "PRIVATE" in upper
                or upper.startswith("GITHUB_")
                or upper.startswith("NEXIUM_EXPERIMENT_")
                or upper.startswith("NEXIUM_INTEL_INPUT_PROFILE")
                or upper in ("NEXIUM_MAC_WORKDIR", "NEXIUM_CPU_BACKEND")):
            continue
        env[key] = value
    env.update({
        "NEXIUM_MAC_WORKDIR": str(work_dir),
        "NEXIUM_CPU_BACKEND": "rustarmic",
        "NEXIUM_INTEL_INPUT_PROFILE": "controller-diagnostics-v1",
        **{flag: "1" for flag in REQUIRED_FLAGS},
    })
    return env


def compute_virtual_tree(repo: Path, main_sha: str, ordered: list[dict],
                         exact_checkout_sha: str) -> str:
    check = git(repo, "rev-parse", "HEAD")
    if not valid_sha(exact_checkout_sha) or check.returncode != 0:
        raise ValueError("invalid exact checkout")
    if check.stdout.strip() != exact_checkout_sha:
        raise ValueError("checkout revision differs from requested PR head")
    result = rehearsal(
        repo, main_sha, ordered,
        reviewed_pr60_blobs=REVIEWED_PR60_BLOBS,
        fetch_missing=True,
    )
    if not (result["combined_tree_complete"]
            and result["reviewed_resolution_applied_locally"]
            and result["reviewed_pr60_three_files_applied_locally"]
            and result["reconciled_source_contracts_verified"]):
        raise ValueError("reviewed merged source failed ancestry checks")
    commit = result.pop("_temporary_commit_sha", None)
    if not valid_sha(commit):
        raise ValueError("temporary merged Git commit missing")
    return commit


def extract_virtual_source(repo: Path, commit: str, destination: Path) -> int:
    if not valid_sha(commit) or not destination.is_dir():
        raise ValueError("invalid virtual source destination")
    try:
        source = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", commit],
            capture_output=True, check=False, timeout=90,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("reviewed source Git archive timed out") from None
    if source.returncode != 0:
        raise ValueError("cannot obtain reviewed Git tree")
    return unpack_reviewed_tree(source.stdout, destination)


def compile_native_intel(source: Path, work_dir: Path, *,
                         host_system: str, host_arch: str,
                         apple_arm_capable: bool,
                         base_env: dict[str, str]) -> dict:
    validate_intel_host(host_system, host_arch, apple_arm_capable)
    script = source / "macos_probe.sh"
    if not script.is_file() or script.is_symlink() or not work_dir.is_dir():
        raise ValueError("merged macOS build entry point absent")
    text = script.read_text(encoding="utf-8")
    if 'REVISION="' + PINNED_UPSTREAM_SHA + '"' not in text:
        raise ValueError("upstream NeXium source pin differs")
    if "source \"$SELF/scripts/intel_controller_input_profile.sh\"" not in text:
        raise ValueError("branch-neutral controller profile missing")
    env = native_environment(base_env, work_dir)
    try:
        build = subprocess.run(
            ["bash", str(script)], cwd=source, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=MAX_BUILD_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("integrated native Intel build exceeded CI budget") from None
    if build.returncode != 0:
        raise ValueError("integrated native Intel build exited nonzero")
    path = (work_dir / "nexium" / "target" / "x86_64-apple-darwin"
            / "release" / "nexium")
    if not path.is_file() or path.is_symlink():
        raise ValueError("expected integrated Intel Mach-O is missing")
    load_commands = validate_macho(path)
    segment_report = verify_segment_bounds(path)
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(block)
    if path.stat().st_size < 1024 * 1024:
        raise ValueError("native Intel executable unexpectedly small")
    return {
        "native_intel_executable_compiled": True,
        "native_macho_load_commands": load_commands,
        "native_macho_segments_checked": segment_report["segments_checked"],
        "native_macho_sections_checked": segment_report["sections_checked"],
        "native_macho_sha256": sha.hexdigest(),
        "native_executable_bytes": path.stat().st_size,
        "nro_executed": False,
        "gui_render_verified": False,
        "physical_controller_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--top-pr", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--min-depth", type=int, default=33)
    parser.add_argument("--git-repo", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        system, arch = platform.system(), platform.machine()
        capable = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"], capture_output=True,
            text=True, check=False, timeout=10,
        )
        validate_intel_host(system, arch,
                            capable.returncode == 0 and capable.stdout.strip() == "1")
        snapshot = collect_live(
            args.repository, os.environ.get("GH_TOKEN", ""), top_pr=args.top_pr,
        )
        audit_snapshot(
            snapshot, top_pr=args.top_pr,
            expected_head_sha=args.expected_head_sha,
            min_depth=args.min_depth,
        )
        by_branch = {pr["head"]: pr for pr in snapshot["pulls"]}
        node = next(pr for pr in snapshot["pulls"]
                    if pr["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(node)
            if node["base"] == "main":
                break
            node = by_branch[node["base"]]
        ordered.reverse()

        merged_commit = compute_virtual_tree(
            args.git_repo, snapshot["main_sha"], ordered,
            args.expected_head_sha,
        )
        with tempfile.TemporaryDirectory(prefix="nexium-intel-merged-") as tmp:
            root = Path(tmp)
            source = root / "source"
            work = root / "native-build"
            source.mkdir()
            work.mkdir()
            count = extract_virtual_source(args.git_repo, merged_commit, source)
            tests = execute_integrated_tests(source, min_tests=EXPECTED_MIN_TESTS)
            compiled = compile_native_intel(
                source, work, host_system=system, host_arch=arch,
                apple_arm_capable=False, base_env=dict(os.environ),
            )
        final_head = git(args.git_repo, "rev-parse", "HEAD")
        if final_head.returncode != 0 or final_head.stdout.strip() != args.expected_head_sha:
            raise ValueError("Git checkout changed during integrated build")
        print(json.dumps({
            "schema": "nexium-intel-reviewed-native-merged-build/v1",
            "stacked_draft_prs": len(ordered),
            "integrated_source_files": count,
            **tests,
            **compiled,
            "native_runner_arch": "x86_64",
            "no_remote_ref_changed": True,
            "main_merge_approved": False,
            "human_integration_review_required": True,
            "production_release_verified": False,
        }, sort_keys=True))
        print("STAGE64_INTEGRATED_INTEL_BUILD_PASS_REVIEW_REQUIRED")
        return 0
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired, tarfile.TarError) as e:
        # Never echo raw private source/logs, tool paths, or credential contents.
        print("STAGE64_INTEGRATED_NATIVE_BLOCKED: " + type(e).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
