#!/usr/bin/env python3
"""Stage63: test the *actual* isolated, reviewed 32-PR virtual combined tree.

Never checks out, changes, pushes or merges any real branch. Never uploads
source, logs or raw API data. Source is extracted to a disposable directory
after the existing Stage61/62 scoped-resolution and ancestry review.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

from audit_intel_pr_stack import audit_snapshot, collect_live
from rehearse_intel_pr_merge import git, valid_sha
from rehearse_intel_reviewed_conflict import REVIEWED_PR60_BLOBS, rehearsal

MAX_ARCHIVE = 48 * 1024 * 1024
MAX_MEMBERS = 5000
TEST_COUNT = re.compile(r"Ran (\d+) tests in ")
EXPECTED_MIN_TESTS = 450


def unpack_reviewed_tree(archive: bytes, output: Path) -> int:
    """Reject malformed, oversized, symlinked, or escaping Git archive paths."""
    if not isinstance(archive, bytes) or len(archive) > MAX_ARCHIVE:
        raise ValueError("oversized or malformed Git archive")
    count = 0
    expanded_bytes = 0
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise ValueError("too many Git archive entries")
        for member in members:
            name = member.name
            path = PurePosixPath(name)
            if (path.is_absolute() or not path.parts
                    or any(p in ("", ".", "..") for p in path.parts)
                    or "\x00" in name or len(name) > 1024):
                raise ValueError("unsafe Git archive pathname")
            if not (member.isfile() or member.isdir()):
                raise ValueError("unsupported Git archive object type")
            dest = output.joinpath(*path.parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            if member.size > MAX_ARCHIVE - expanded_bytes:
                raise ValueError("oversized expanded source tree")
            expanded_bytes += member.size
            count += 1
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("missing source archive member")
            with source, dest.open("xb") as sink:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    sink.write(chunk)
    return count


def execute_integrated_tests(directory: Path, *, min_tests: int = EXPECTED_MIN_TESTS) -> dict:
    if type(min_tests) is not int or min_tests < 1:
        raise ValueError("invalid test threshold")
    if not (directory / "scripts/rehearse_intel_reviewed_conflict.py").is_file():
        raise ValueError("reviewed integration source not found")
    # Important: the GitHub token and CI secrets are excluded from the
    # executed test environment. Only a minimal host runtime PATH is retained.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("RUNNER_TEMP", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C.UTF-8",
    }
    command = [
        sys.executable, "-m", "unittest", "discover",
        "-s", "tests", "-p", "test_*.py", "-q",
    ]
    try:
        test = subprocess.run(
            command, cwd=directory, env=env,
            text=True, capture_output=True, check=False, timeout=180,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("integrated Python suite exceeded runtime budget") from None
    combined = test.stdout + "\n" + test.stderr
    matched = TEST_COUNT.findall(combined)
    if len(matched) != 1 or test.returncode != 0:
        raise ValueError("integrated Python unittest suite did not pass")
    executed = int(matched[0])
    if executed < min_tests:
        raise ValueError("integrated Python suite unexpectedly reduced")
    if not re.search(r"(?m)^OK(?: \(skipped=\d+\))?$", combined):
        raise ValueError("integrated Python suite lacks final success marker")
    return {
        "integrated_python_tests_passed": True,
        "integrated_python_test_count": executed,
    }


def integrated_test_run(repo: Path, *, expected_commit: str, main_sha: str,
                        ordered: list[dict], min_tests: int = EXPECTED_MIN_TESTS) -> dict:
    starting_head = git(repo, "rev-parse", "HEAD")
    if starting_head.returncode != 0 or starting_head.stdout.strip() != expected_commit:
        raise ValueError("checkout does not match exact PR head")
    result = rehearsal(
        repo, main_sha, ordered,
        reviewed_pr60_blobs=REVIEWED_PR60_BLOBS,
        fetch_missing=True,
    )
    if not (result["combined_tree_complete"]
            and result["reviewed_resolution_applied_locally"]
            and result["reviewed_pr60_three_files_applied_locally"]
            and result["reconciled_source_contracts_verified"]):
        raise ValueError("reviewed combined Git tree incomplete")
    merged_commit = result.pop("_temporary_commit_sha", None)
    if not valid_sha(merged_commit):
        raise ValueError("missing private synthetic combined commit")
    tar = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", merged_commit],
        capture_output=True, check=False, timeout=90,
    )
    if tar.returncode != 0:
        raise ValueError("cannot archive reviewed synthetic Git tree")
    with tempfile.TemporaryDirectory(prefix="nexium-integrated-source-") as temp:
        temp_root = Path(temp)
        source_count = unpack_reviewed_tree(tar.stdout, temp_root)
        tests = execute_integrated_tests(temp_root, min_tests=min_tests)
    ending_head = git(repo, "rev-parse", "HEAD")
    if ending_head.returncode != 0 or ending_head.stdout.strip() != expected_commit:
        raise ValueError("checkout Git HEAD changed during integrated tests")
    return {
        "schema": "nexium-intel-reviewed-integrated-test/v1",
        "stacked_draft_prs": len(ordered),
        "temporary_tree_files_extracted": source_count,
        "reviewed_source_guards_preserved": True,
        **tests,
        "remote_ref_changed": False,
        "main_merge_approved": False,
        "human_integration_review_required": True,
        "physical_controller_verified": False,
        "production_release_verified": False,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repository", required=True)
    ap.add_argument("--top-pr", type=int, required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--min-depth", type=int, default=32)
    ap.add_argument("--git-repo", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        snapshot = collect_live(
            args.repository, os.environ.get("GH_TOKEN", ""),
            top_pr=args.top_pr,
        )
        audit_snapshot(snapshot, top_pr=args.top_pr,
                       expected_head_sha=args.expected_head_sha,
                       min_depth=args.min_depth)
        heads = {x["head"]: x for x in snapshot["pulls"]}
        current = next(x for x in snapshot["pulls"]
                       if x["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(current)
            if current["base"] == "main":
                break
            current = heads[current["base"]]
        ordered.reverse()
        output = integrated_test_run(
            args.git_repo, expected_commit=args.expected_head_sha,
            main_sha=snapshot["main_sha"], ordered=ordered,
        )
        print(json.dumps(output, sort_keys=True))
        print("STAGE63_INTEGRATED_TREE_TEST_PASS_REVIEW_REQUIRED")
        return 0
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired, tarfile.TarError) as error:
        # No private temp paths, test tracebacks, raw Git output or token values.
        print("STAGE63_INTEGRATED_TREE_TEST_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
