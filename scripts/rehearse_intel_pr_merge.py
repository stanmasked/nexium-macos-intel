#!/usr/bin/env python3
"""Stage60: local merge-tree rehearsal of the entire NeXium Intel Draft stack.

No remote writes, merges, ref moves, or automatic conflict resolution. The
only synthetic Git commit objects are unreachable temporary objects made in
the disposable CI checkout; user files and raw Git logs are not published.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from audit_intel_pr_stack import audit_snapshot, collect_live

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TREE_RE = re.compile(r"^[0-9a-f]{40}$")


def git(repo: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "NeXium Integration Dry Run",
        "GIT_AUTHOR_EMAIL": "nexium-rehearsal@localhost",
        "GIT_COMMITTER_NAME": "NeXium Integration Dry Run",
        "GIT_COMMITTER_EMAIL": "nexium-rehearsal@localhost",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00 +0000",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00 +0000",
        "GIT_OPTIONAL_LOCKS": "0",
    })
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text, text=True, capture_output=True, check=False,
        env=env, timeout=90,
    )


def valid_sha(s: str) -> bool:
    return isinstance(s, str) and SHA_RE.fullmatch(s) is not None


def ensure_object(repo: Path, sha: str, *, fetch_missing: bool) -> None:
    if not valid_sha(sha):
        raise ValueError("malformed Git revision")
    probe = git(repo, "cat-file", "-e", sha + "^{commit}")
    if probe.returncode == 0:
        return
    if fetch_missing:
        # Fetch exact SHA only. No branch/ref update, no shell interpolation.
        fetched = git(repo, "fetch", "--no-tags", "--no-write-fetch-head",
                      "origin", sha)
        if fetched.returncode == 0 and git(
            repo, "cat-file", "-e", sha + "^{commit}"
        ).returncode == 0:
            return
    raise ValueError("expected commit object unavailable")


def ancestor(repo: Path, possible_parent: str, descendant: str) -> bool:
    ret = git(repo, "merge-base", "--is-ancestor",
              possible_parent, descendant)
    if ret.returncode not in (0, 1):
        raise ValueError("Git merge-base could not classify ancestry")
    return ret.returncode == 0


def conflicted_filenames(output: str) -> list[str]:
    """Extract only safe repo-relative conflicted names from Git --name-only.

    Git --write-tree --name-only prints a tree ID on the first line, followed
    by one conflicting pathname per line until a blank separator. Never expose
    merge messages, file contents, object IDs, or arbitrary command errors.
    """
    lines = output.splitlines()
    if not lines or not TREE_RE.fullmatch(lines[0]):
        raise ValueError("Git conflict report missing merge-tree identity")
    paths = []
    for line in lines[1:]:
        if not line:
            break
        parts = line.split("/")
        if (len(paths) >= 64 or len(line) > 512 or not line
                or line.startswith("/") or chr(0) in line
                or any(part in ("", ".", "..") for part in parts)
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in line)):
            raise ValueError("untrusted conflict filename")
        paths.append(line)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Git conflict report lacks unique filenames")
    return sorted(paths)


def local_merge_chain(repo: Path, main_sha: str, ordered: list[dict],
                      *, fetch_missing: bool = False) -> dict:
    if not valid_sha(main_sha) or not ordered:
        raise ValueError("main revision or ordered ancestors missing")
    if len(ordered) > 100:
        raise ValueError("too many PRs in rehearsal")
    ensure_object(repo, main_sha, fetch_missing=fetch_missing)
    current = main_sha
    classifications = []
    visited = set()
    for entry in ordered:
        number, head = entry.get("number"), entry.get("head_sha")
        if (type(number) is not int or number <= 0 or number in visited
                or not valid_sha(head)):
            raise ValueError("duplicate or malformed ordered PR")
        visited.add(number)
        ensure_object(repo, head, fetch_missing=fetch_missing)
        if ancestor(repo, current, head):
            result = "fast_forward"
            current = head
        elif ancestor(repo, head, current):
            result = "already_included"
        else:
            simulation = git(repo, "merge-tree", "--write-tree",
                             "--name-only", current, head)
            if simulation.returncode == 1:
                classifications.append({
                    "pr": number, "result": "conflict",
                    "conflicted_files": conflicted_filenames(simulation.stdout),
                })
                break
            if simulation.returncode != 0:
                raise ValueError("Git merge-tree execution failed")
            tree = simulation.stdout.strip()
            if not TREE_RE.fullmatch(tree):
                raise ValueError("Git produced an unexpected merge tree")
            # Do not update HEAD, branch references or the working tree.
            new = git(repo, "commit-tree", tree, "-p", current, "-p", head,
                      "-m", "Stage60 local synthetic merge of PR " + str(number))
            if new.returncode != 0 or not valid_sha(new.stdout.strip()):
                raise ValueError("cannot create temporary merge parent")
            current = new.stdout.strip()
            result = "automatic_merge"
        classifications.append({"pr": number, "result": result})

    complete = len(classifications) == len(ordered) and all(
        item["result"] != "conflict" for item in classifications
    )
    return {
        "schema": "nexium-intel-local-merge-rehearsal/v1",
        "ancestors_requested": len(ordered),
        "ancestors_checked": len(classifications),
        "merge_tree_complete": complete,
        "classification": classifications,
        "_temporary_commit_sha": current if complete else None,
        "integration_requires_review": True,
        "main_merge_approved": False,
        "remote_ref_changed": False,
        "physical_controller_verified": False,
        "production_release_verified": False,
    }


def check_reconciled_sources(repo: Path, commit: str) -> None:
    # Structural proof that the four omitted historical fixes survive the
    # generated combined tree. This does not assert their runtime semantics.
    expected = {
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
        "scripts/audit_guest_hid_mapping_path.py": (
            "has_zero_handle_warning = False",
            "if 'if handle == 0 {' in map_svc:",
        ),
        "scripts/audit_intel_macho_segment_bounds.py": (
            "segment_bounds_passed",
        ),
        "scripts/audit_intel_pr_stack.py": (
            "main_merge_approved",
        ),
    }
    for path, markers in expected.items():
        result = git(repo, "show", commit + ":" + path)
        if result.returncode != 0 or any(m not in result.stdout for m in markers):
            raise ValueError("reconciled audit source marker absent")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repository", required=True)
    ap.add_argument("--top-pr", type=int, required=True)
    ap.add_argument("--expected-head-sha", required=True)
    ap.add_argument("--min-depth", type=int, default=29)
    ap.add_argument("--git-repo", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        snapshot = collect_live(args.repository, os.environ.get("GH_TOKEN", ""),
                                top_pr=args.top_pr)
        audit_snapshot(snapshot, top_pr=args.top_pr,
                       expected_head_sha=args.expected_head_sha,
                       min_depth=args.min_depth)
        chain = {p["head"]: p for p in snapshot["pulls"]}
        node = next(p for p in snapshot["pulls"]
                    if p["number"] == args.top_pr)
        ordered = []
        while True:
            ordered.append(node)
            if node["base"] == "main":
                break
            node = chain[node["base"]]
        ordered.reverse()
        result = local_merge_chain(args.git_repo, snapshot["main_sha"], ordered,
                                   fetch_missing=True)
        if result["merge_tree_complete"]:
            check_reconciled_sources(
                args.git_repo, result["_temporary_commit_sha"])
            result["reconciled_sources_preserved"] = True
        else:
            result["reconciled_sources_preserved"] = False
        # The virtual SHA is local-only, never a repository/PR head revision.
        result.pop("_temporary_commit_sha", None)
        print(json.dumps(result, sort_keys=True))
        if not result["merge_tree_complete"]:
            print("STAGE60_REHEARSAL_CONFLICT_REVIEW_REQUIRED", file=sys.stderr)
            return 2
        print("STAGE60_REHEARSAL_PASS_REVIEW_STILL_REQUIRED")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print("STAGE60_REHEARSAL_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
