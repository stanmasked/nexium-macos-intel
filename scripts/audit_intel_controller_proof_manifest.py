#!/usr/bin/env python3
"""Fail-closed, privacy-safe provenance of an exact Intel libnx proof triplet.

Stage54: tie the SAME GitHub Actions run's native Intel Mach-O, public
homebrew NRO, and sanitized Stage53 guest threshold receipt together by
content hashes and the pinned upstream NeXium source revision. This does
not certify a production release, real controller, game or Switch hardware.
Never embeds file paths, guest logs, memory or proprietary content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

PINNED_UPSTREAM = "089562567a0a8760dfdd8420e1f57c35159a9219"
EXPECTED_SCHEMA = "nexium-stage53-guest-deadzone-threshold/v1"
REQUIRED_TRUE = (
    "same_process_guest_deadzone_threshold_passed",
    "original_guest_hid_map_and_svc_observed",
    "original_host_b_surrounds_below_above_pulses",
    "original_host_sdl3_below_above_pulses_ordered",
    "original_source_below_zero_above_signed_all_four_axes",
    "guest_above_threshold_both_sticks_in_order",
    "original_npad_b_pressed_then_released",
)
REQUIRED_FALSE = (
    "guest_incomplete_or_unexpected_button_observed",
    "original_sdl3_virtual_set_failure_observed",
    "physical_controller_verified",
    "gameplay_verified",
    "real_switch_verified",
    "raw_logs_uploaded",
    "frame_images_uploaded",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_RE = re.compile(r"^[1-9][0-9]{5,19}$")


def sha256(path: Path) -> str:
    hash_object = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hash_object.update(chunk)
    return hash_object.hexdigest()


def require_intel_macho(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(32)
    if len(header) < 32:
        raise ValueError("native Mach-O header truncated")
    # The workflow's exact native Intel NeXium artifact must be thin x86_64.
    # A fat/universal app is not accepted without a separately validated slice.
    if header[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("not a thin little-endian 64-bit Intel Mach-O")
    cputype = struct.unpack_from("<I", header, 4)[0]
    if cputype != 0x01000007:
        raise ValueError("Mach-O CPU is not x86_64")


def require_public_nro(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(0x20)
    if len(header) < 0x20 or header[0x10:0x14] != b"NRO0":
        raise ValueError("public guest libnx NRO header invalid")
    if path.stat().st_size < 0x200:
        raise ValueError("homebrew NRO truncated")


def read_sanitized_receipt(path: Path) -> tuple[dict, int]:
    if path.stat().st_size > 16384:
        raise ValueError("receipt is not small sanitized JSON")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("guest receipt schema mismatch")
    if any(receipt.get(key) is not True for key in REQUIRED_TRUE):
        raise ValueError("required source-authentic guest proof missing")
    if any(receipt.get(key) is not False for key in REQUIRED_FALSE):
        raise ValueError("guest error or privacy boundary not satisfied")
    samples = receipt.get("original_npad_serialized_sample_count")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise ValueError("original NPad source samples missing")
    if not all(
        isinstance(value, (str, bool, int)) and not isinstance(value, float)
        for value in receipt.values()
    ):
        raise ValueError("receipt contains unapproved structured/raw data")
    if set(receipt) != {
        "schema", "original_npad_serialized_sample_count",
        *REQUIRED_TRUE, *REQUIRED_FALSE,
    }:
        raise ValueError("unexpected guest receipt keys")
    return receipt, samples


def audit(binary: Path, nro: Path, receipt_path: Path,
          source_sha: str, repository_sha: str, run_id: str) -> dict:
    if source_sha != PINNED_UPSTREAM:
        raise ValueError("upstream NeXium source revision mismatch")
    if not SHA_RE.fullmatch(repository_sha):
        raise ValueError("source repository commit SHA malformed")
    if not RUN_RE.fullmatch(run_id):
        raise ValueError("GitHub Actions run ID malformed")

    require_intel_macho(binary)
    require_public_nro(nro)
    receipt, samples = read_sanitized_receipt(receipt_path)

    return {
        "schema": "nexium-intel-controller-proof-manifest/v1",
        "provenance_passed": True,
        "upstream_source_sha": source_sha,
        "controller_pipeline_commit_sha": repository_sha,
        "github_actions_run_id": run_id,
        "intel_macho_sha256": sha256(binary),
        "public_guest_nro_sha256": sha256(nro),
        "sanitized_guest_receipt_sha256": sha256(receipt_path),
        "intel_macho_bytes": binary.stat().st_size,
        "public_guest_nro_bytes": nro.stat().st_size,
        "original_npad_samples": samples,
        "guest_source_bound_passed": receipt["same_process_guest_deadzone_threshold_passed"],
        "physical_controller_verified": False,
        "production_release_verified": False,
        "commercial_gameplay_verified": False,
        "raw_logs_uploaded": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intel-binary", type=Path, required=True)
    parser.add_argument("--guest-nro", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--repository-sha", required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(
            args.intel_binary, args.guest_nro, args.guest_receipt,
            args.source_sha, args.repository_sha, args.github_run_id,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        print("STAGE54_PROOF_MANIFEST_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
