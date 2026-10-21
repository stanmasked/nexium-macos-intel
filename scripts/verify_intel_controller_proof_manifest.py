#!/usr/bin/env python3
"""Stage55 independent, fail-closed replay of a Stage54 proof manifest.

Check the published, sanitized proof against the *actual* three local files,
the pinned upstream revision and the expected workflow commit/run. Never trust
a pass flag or the manifest's own hashes on their own. This is consistency
verification, not a cryptographic signature or evidence of real hardware.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import sys

from audit_intel_controller_proof_manifest import audit

MAX_MANIFEST_BYTES = 16384


def _reject_duplicate_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate proof manifest key")
        out[key] = value
    return out


def _reject_json_constant(_):
    raise ValueError("non-finite JSON value in proof manifest")


def _stat_identity(path: Path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("proof input is not a regular file")
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def verify(manifest_path: Path, binary: Path, nro: Path, receipt: Path,
           source_sha: str, repository_sha: str, run_id: str) -> dict:
    inputs = (manifest_path, binary, nro, receipt)
    before = tuple(_stat_identity(path) for path in inputs)
    if before[0][2] > MAX_MANIFEST_BYTES:
        raise ValueError("proof manifest exceeds sanitized size limit")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(manifest, dict):
        raise ValueError("proof manifest is not an object")

    # Regenerate ALL fields from independently supplied build files and CI
    # identity, instead of trusting the manifest's claimed hashes and flags.
    expected = audit(binary, nro, receipt, source_sha, repository_sha, run_id)
    if set(manifest) != set(expected):
        raise ValueError("proof manifest fields differ from exact schema")
    for key, correct in expected.items():
        value = manifest[key]
        # bool == 1 in Python: explicit type checking prevents this bypass.
        if type(value) is not type(correct) or value != correct:
            raise ValueError("proof manifest differs from exact input artifacts")

    if tuple(_stat_identity(path) for path in inputs) != before:
        raise ValueError("proof input changed during replay")
    return {
        "schema": "nexium-intel-controller-proof-replay/v1",
        "exact_triplet_replay_passed": True,
        "physical_controller_verified": False,
        "production_release_verified": False,
        "raw_logs_uploaded": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--intel-binary", type=Path, required=True)
    parser.add_argument("--guest-nro", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--repository-sha", required=True)
    parser.add_argument("--github-run-id", required=True)
    args = parser.parse_args(argv)
    try:
        verify(args.manifest, args.intel_binary, args.guest_nro,
               args.guest_receipt, args.source_sha, args.repository_sha,
               args.github_run_id)
        print("STAGE55_PROOF_REPLAY_PASSED")
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        print("STAGE55_PROOF_REPLAY_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
