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


def rehearsal(repo: Path, main_sha: str, ordered: list[dict],
              *, reviewed_blob: str = REVIEWED_BLOB,
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
                if (number != CONFLICT_PR or names != [CONFLICT_FILE]
                        or resolved):
                    classifications.append({
                        "pr": number, "result": "conflict",
                        "conflicted_files": names,
                    })
                    break
                tree_id = m.stdout.splitlines()[0]
                tree = substitute_one_reviewed_blob(
                    repo, tree_id, reviewed_blob, CONFLICT_FILE
                )
                result = "reviewed_local_resolution"
                resolved = True
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
        "combined_tree_complete": completed,
        "classification": classifications,
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
        result = rehearsal(args.git_repo, snapshot["main_sha"],
                           ordered, fetch_missing=True)
        print(json.dumps(result, sort_keys=True))
        if not result["combined_tree_complete"]:
            print("STAGE61_ADDITIONAL_CONFLICT_REVIEW_REQUIRED", file=sys.stderr)
            return 2
        if not result["reviewed_resolution_applied_locally"]:
            raise ValueError("expected known PR44 conflict not encountered")
        print("STAGE61_REHEARSAL_REVIEW_STILL_REQUIRED")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("STAGE61_REHEARSAL_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
