#!/usr/bin/env python3
"""Stage61: opt-in reviewed resolution of ONE exact virtual-merge conflict.

The original Stage60 rehearsal stays red/fail-closed. In this independent,
disposable local-Git rehearsal only, explicitly substitute a previously audited
Stage58 blob for the sole Stage42/PR44 conflict in the HID source auditor.
Do not move refs, change working-tree/index state, push, or approve a main merge.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from audit_intel_pr_stack import audit_snapshot, collect_live
from rehearse_intel_pr_merge import (
    ancestor, check_reconciled_sources, conflicted_filenames,
    ensure_object, git, valid_sha,
)

CONFLICT_PR = 44
CONFLICT_FILE = "scripts/audit_guest_hid_mapping_path.py"
REVIEWED_BLOB = "3bae901b585bde27a2d55c82faf4366b5c99d74d"
CANONICAL_MARKERS = (
    "has_zero_handle_warning = False",
    "if 'if handle == 0 {' in map_svc:",
    "expected current size-based mapping/handle-validation behavior changed",
)

REVIEWED_PR60_BLOBS = {
    ".github/workflows/nexium-macos-probe.yml":
        "f67d32cb789d23cc5b27792068f1e18e5f51da66",
    "scripts/audit_npad_lifo_trace.py":
        "4137d95716fe4b1fa0e0f5c1b2267ece1627d51a",
    "tests/test_npad_lifo_trace.py":
        "16743d717d20328cfc6dd464133828fb17d23a05",
}
REVIEWED_PR60_MARKERS = {
    ".github/workflows/nexium-macos-probe.yml": (
        "audio_init_marker_01_intentionally_omitted",
        "Stage57 validate file-backed Mach-O segment and section bounds",
    ),
    "scripts/audit_npad_lifo_trace.py": (
        "NO_NPAD_TICK_OBSERVED_NO_NRO",
        "NPAD_LIFO_TRACE_OBSERVED_B_ROUND_TRIP_NOT_CONFIRMED",
    ),
    "tests/test_npad_lifo_trace.py": (
        "test_no_guest_tick_without_nro_is_classified_not_claimed_as_success",
        "test_guest_tick_without_round_trip_remains_unconfirmed",
    ),
}


def _index_git(repo: Path, temp_index: Path, *args: str) -> str:
    """Use a disposable alternate index, never the checked-out repository's."""
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = str(temp_index)
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True, check=False, timeout=90, env=env,
    )
    if p.returncode != 0:
        raise ValueError("virtual merge index operation failed")
    return p.stdout.strip()


def verify_reviewed_blob(repo: Path, expected: str) -> None:
    if not valid_sha(expected) or expected != REVIEWED_BLOB:
        raise ValueError("reviewed blob identity changed")
    blob_type = git(repo, "cat-file", "-t", expected)
    if blob_type.returncode != 0 or blob_type.stdout.strip() != "blob":
        raise ValueError("reviewed source blob missing")
    original = git(repo, "cat-file", "-p", expected)
    if original.returncode != 0:
        raise ValueError("cannot inspect reviewed source blob")
    if (any(marker not in original.stdout for marker in CANONICAL_MARKERS)
            or "if 'if handle == 0 {' not in map_svc:" in original.stdout):
        raise ValueError("reviewed blob no longer matches Stage58 safeguards")


def substitute_one_reviewed_blob(
    repo: Path, conflicted_tree: str, blob: str, path: str
) -> str:
    if not valid_sha(conflicted_tree) or path != CONFLICT_FILE:
        raise ValueError("unexpected conflict tree or source path")
    verify_reviewed_blob(repo, blob)
    # Git produced a tree even with the conflict; edit ONLY the alternate
    # index to replace the one known-conflicted path with reviewed blob.
    with tempfile.TemporaryDirectory(prefix="nexium-review-index-") as tmp:
        index = Path(tmp) / "index"
        _index_git(repo, index, "read-tree", conflicted_tree)
        _index_git(repo, index, "update-index", "--add", "--cacheinfo",
                   "100644," + blob + "," + path)
        result = _index_git(repo, index, "write-tree")
    if not valid_sha(result):
        raise ValueError("invalid isolated reviewed tree")
    # Confirm the file is exactly the approved blob, not conflict markers.
    verify = git(repo, "rev-parse", result + ":" + path)
    if verify.returncode != 0 or verify.stdout.strip() != blob:
        raise ValueError("reviewed resolution failed to preserve exact blob")
    return result


def substitute_reviewed_pr60_blobs(
    repo: Path, conflicted_tree: str, conflicted_paths: list[str],
    proposed: dict[str, str]
) -> str:
    """Exact Stage58 sources, local temporary Git index, no blanket strategy."""
    if (not valid_sha(conflicted_tree)
            or conflicted_paths != sorted(REVIEWED_PR60_BLOBS)
            or proposed != REVIEWED_PR60_BLOBS):
        raise ValueError("unexpected Stage58 conflict file set or blob policy")
    for path, expected in proposed.items():
        if not valid_sha(expected):
            raise ValueError("reviewed Stage58 blob malformed")
        t = git(repo, "cat-file", "-t", expected)
        data = git(repo, "cat-file", "-p", expected)
        if t.returncode != 0 or t.stdout.strip() != "blob" or data.returncode != 0:
            raise ValueError("reviewed Stage58 blob unavailable")
        if any(marker not in data.stdout
               for marker in REVIEWED_PR60_MARKERS[path]):
            raise ValueError("reviewed Stage58 source invariants missing")
    with tempfile.TemporaryDirectory(prefix="nexium-stage62-index-") as d:
        idx = Path(d) / "index"
        _index_git(repo, idx, "read-tree", conflicted_tree)
        for path, blob in sorted(proposed.items()):
            _index_git(repo, idx, "update-index", "--add", "--cacheinfo",
                       "100644," + blob + "," + path)
        tree = _index_git(repo, idx, "write-tree")
    if not valid_sha(tree):
        raise ValueError("invalid reviewed Stage58 merged tree")
    for path, blob in proposed.items():
        check = git(repo, "rev-parse", tree + ":" + path)
        if check.returncode != 0 or check.stdout.strip() != blob:
            raise ValueError("reviewed Stage58 blob changed in virtual tree")
    return tree


def rehearsal(repo: Path, main_sha: str, ordered: list[dict],
              *, reviewed_blob: str = REVIEWED_BLOB,
              reviewed_pr60_blobs: dict[str, str] | None = None,
              fetch_missing: bool = False) -> dict:
    if not valid_sha(main_sha) or not ordered or len(ordered) > 100:
        raise ValueError("invalid source tree or ancestor count")
    # Also ensure running this stage does not switch the Git HEAD.
    starting_head = git(repo, "rev-parse", "HEAD")
    if starting_head.returncode != 0 or not valid_sha(starting_head.stdout.strip()):
        raise ValueError("Git HEAD missing")
    ensure_object(repo, main_sha, fetch_missing=fetch_missing)
    current = main_sha
    classifications = []
    seen = set()
    resolved = False
    resolved_pr60 = False
    for entry in ordered:
        number, head = entry.get("number"), entry.get("head_sha")
        if (type(number) is not int or number <= 0
                or number in seen or not valid_sha(head)):
            raise ValueError("duplicate or malformed ancestor")
        seen.add(number)
        ensure_object(repo, head, fetch_missing=fetch_missing)
        if ancestor(repo, current, head):
            current = head
            result = "fast_forward"
        elif ancestor(repo, head, current):
            result = "already_included"
        else:
            m = git(repo, "merge-tree", "--write-tree",
                    "--name-only", current, head)
            if m.returncode == 1:
                names = conflicted_filenames(m.stdout)
                tree_id = m.stdout.splitlines()[0]
                if number == CONFLICT_PR and names == [CONFLICT_FILE] and not resolved:
                    tree = substitute_one_reviewed_blob(
                        repo, tree_id, reviewed_blob, CONFLICT_FILE
                    )
                    result = "reviewed_local_resolution"
                    resolved = True
                elif (number == 60 and not resolved_pr60
                      and reviewed_pr60_blobs is not None
                      and names == sorted(REVIEWED_PR60_BLOBS)):
                    tree = substitute_reviewed_pr60_blobs(
                        repo, tree_id, names, reviewed_pr60_blobs
                    )
                    result = "reviewed_three_file_resolution"
                    resolved_pr60 = True
                else:
                    classifications.append({
                        "pr": number, "result": "conflict",
                        "conflicted_files": names,
                    })
                    break
            elif m.returncode == 0:
                tree = m.stdout.strip()
                if not valid_sha(tree):
                    raise ValueError("invalid clean virtual Git tree")
                result = "automatic_merge"
            else:
                raise ValueError("Git merge-tree execution failed")
            c = git(repo, "commit-tree", tree,
                    "-p", current, "-p", head,
                    "-m", "Stage61 disposable review-only merge PR " + str(number))
            if c.returncode != 0 or not valid_sha(c.stdout.strip()):
                raise ValueError("temporary virtual merge commit failed")
            current = c.stdout.strip()
        classifications.append({"pr": number, "result": result})
    completed = len(classifications) == len(ordered) and all(
        c["result"] != "conflict" for c in classifications
    )
    if completed:
        check_reconciled_sources(repo, current)
    end_head = git(repo, "rev-parse", "HEAD")
    if end_head.returncode != 0 or end_head.stdout.strip() != starting_head.stdout.strip():
        raise ValueError("Git HEAD changed during virtual rehearsal")
    return {
        "schema": "nexium-intel-reviewed-merge-rehearsal/v1",
        "ancestors_requested": len(ordered),
        "ancestors_checked": len(classifications),
        "approved_reviewed_path": CONFLICT_FILE if resolved else None,
        "reviewed_resolution_applied_locally": resolved,
        "reviewed_pr60_three_files_applied_locally": resolved_pr60,
        "combined_tree_complete": completed,
        "classification": classifications,
        "_temporary_commit_sha": current if completed else None,
        "reconciled_source_contracts_verified": completed,
        "main_merge_approved": False,
        "human_integration_review_required": True,
        "remote_ref_changed": False,
        "physical_controller_verified": False,
        "production_release_verified": False,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repository", required=True)
    ap.add_argument("--top-pr", type=int, required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--min-depth", type=int, default=30)
    ap.add_argument("--git-repo", type=Path, required=True)
    ap.add_argument("--review-pr44-hid-blob", action="store_true")
    ap.add_argument("--review-pr60-three-blobs", action="store_true")
    args = ap.parse_args(argv)
    try:
        if not args.review_pr44_hid_blob:
            raise ValueError("explicit scoped reviewed resolution flag missing")
        snapshot = collect_live(
            args.repository, os.environ.get("GH_TOKEN", ""), top_pr=args.top_pr,
        )
        audit_snapshot(
            snapshot, top_pr=args.top_pr,
            expected_head_sha=args.expected_head_sha, min_depth=args.min_depth,
        )
        heads = {p["head"]: p for p in snapshot["pulls"]}
        node = next(p for p in snapshot["pulls"]
                    if p["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(node)
            if node["base"] == "main":
                break
            node = heads[node["base"]]
        ordered.reverse()
        result = rehearsal(
            args.git_repo, snapshot["main_sha"], ordered,
            reviewed_pr60_blobs=(
                REVIEWED_PR60_BLOBS if args.review_pr60_three_blobs else None
            ),
            fetch_missing=True,
        )
        # Never expose the local-only synthetic commit hash in job logs.
        result.pop("_temporary_commit_sha", None)
        print(json.dumps(result, sort_keys=True))
        if not result["combined_tree_complete"]:
            print("STAGE61_ADDITIONAL_CONFLICT_REVIEW_REQUIRED", file=sys.stderr)
            return 2
        if not result["reviewed_resolution_applied_locally"]:
            raise ValueError("expected known PR44 conflict not encountered")
        if (args.review_pr60_three_blobs
                and not result["reviewed_pr60_three_files_applied_locally"]):
            raise ValueError("expected Stage58 three-file conflict not encountered")
        print("STAGE61_REHEARSAL_REVIEW_STILL_REQUIRED")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("STAGE61_REHEARSAL_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
