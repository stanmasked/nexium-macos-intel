#!/usr/bin/env python3
"""Stage59: read-only, fail-closed audit of the complete stacked Draft PR ancestry.

Checks the live GitHub PR base/head relationships and exact Git commit compares.
A passing audit establishes that the dependency graph has been classified, NOT
that the 28 PRs are cleared for merging. This script never changes GitHub refs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

SCHEMA = "nexium-intel-stack-audit/v1"
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_PRS = 100
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def _hexsha(value: object) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def audit_snapshot(snapshot: dict, *, top_pr: int, expected_head_sha: str,
                   min_depth: int = 28) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("schema") != SCHEMA:
        raise ValueError("integration snapshot schema mismatch")
    if not isinstance(top_pr, int) or isinstance(top_pr, bool) or top_pr < 1:
        raise ValueError("invalid top PR")
    if not _hexsha(expected_head_sha):
        raise ValueError("invalid expected PR head SHA")
    if not isinstance(min_depth, int) or min_depth < 2 or min_depth > MAX_PRS:
        raise ValueError("invalid minimum ancestry depth")
    repo = snapshot.get("repository")
    if not isinstance(repo, str) or REPO_RE.fullmatch(repo) is None:
        raise ValueError("invalid snapshot repository")
    if not _hexsha(snapshot.get("main_sha")):
        raise ValueError("main head SHA absent")
    pulls = snapshot.get("pulls")
    compares = snapshot.get("comparisons")
    if (not isinstance(pulls, list) or not isinstance(compares, list)
            or len(pulls) > MAX_PRS or len(compares) > MAX_PRS):
        raise ValueError("invalid bounded PR / compare collections")

    by_number = {}
    by_head = {}
    for pr in pulls:
        if not isinstance(pr, dict):
            raise ValueError("malformed pull request")
        num = pr.get("number")
        head, base = pr.get("head"), pr.get("base")
        if (type(num) is not int or num <= 0 or num in by_number
                or not isinstance(head, str) or not head.startswith("work/")
                or not isinstance(base, str) or not base
                or head in by_head or head == base
                or not _hexsha(pr.get("head_sha"))
                or not _hexsha(pr.get("base_sha"))
                or pr.get("state") != "open" or pr.get("draft") is not True):
            raise ValueError("missing, non-draft, duplicate, or invalid PR")
        by_number[num] = pr
        by_head[head] = pr

    head_pr = by_number.get(top_pr)
    if head_pr is None or head_pr["head_sha"] != expected_head_sha:
        raise ValueError("top PR head changed or was not found")
    if head_pr["base"] == "main":
        raise ValueError("top PR is not a stacked change")

    sequence = []
    seen = set()
    node = head_pr
    while True:
        number = node["number"]
        if number in seen:
            raise ValueError("cycle in stacked PR ancestry")
        seen.add(number)
        sequence.append(node)
        if len(sequence) > MAX_PRS:
            raise ValueError("PR ancestry exceeds audit bound")
        base = node["base"]
        if base == "main":
            if node["base_sha"] != snapshot["main_sha"]:
                raise ValueError("root PR is not based on inspected main revision")
            break
        ancestor = by_head.get(base)
        if ancestor is None:
            raise ValueError("stack has missing intermediate base PR")
        if node["base_sha"] != ancestor["head_sha"]:
            raise ValueError("base ref shifted during PR collection")
        node = ancestor

    if len(sequence) < min_depth:
        raise ValueError("stack unexpectedly shallow")
    if sequence[-1]["number"] != 1:
        raise ValueError("stack does not reach original bootstrap PR #1")

    compare_by_pr = {}
    for item in compares:
        if not isinstance(item, dict):
            raise ValueError("malformed compare entry")
        num = item.get("number")
        ahead, behind = item.get("ahead_by"), item.get("behind_by")
        if (type(num) is not int or num in compare_by_pr
                or type(ahead) is not int or ahead < 1
                or type(behind) is not int or behind < 0
                or not _hexsha(item.get("base_sha"))
                or not _hexsha(item.get("head_sha"))):
            raise ValueError("compare missing required refs or counters")
        if item.get("status") != ("ahead" if behind == 0 else "diverged"):
            raise ValueError("compare status disagrees with ahead/behind")
        compare_by_pr[num] = item
    if set(compare_by_pr) != seen:
        raise ValueError("not every ancestor has exactly one compare")

    divergence = []
    for node in sequence:
        compare = compare_by_pr[node["number"]]
        if (compare["base_sha"] != node["base_sha"]
                or compare["head_sha"] != node["head_sha"]):
            raise ValueError("compare does not match exact PR refs")
        if compare["behind_by"]:
            divergence.append({
                "pr": node["number"],
                "base_commits_missing": compare["behind_by"],
            })
    # The historical three divergent edges must always receive human review.
    # No automatic acceptance, retargeting, or Git ref changes take place.
    return {
        "schema": "nexium-intel-stack-audit-result/v1",
        "pr_chain_checked": len(sequence),
        "root_pr": sequence[-1]["number"],
        "top_pr": top_pr,
        "all_prs_open_draft": True,
        "base_head_sha_consistent": True,
        "base_branch_reaches_main": True,
        "diverged_edges": sorted(divergence, key=lambda x: x["pr"]),
        "integration_requires_review": True,
        "main_merge_approved": False,
        "raw_logs_uploaded": False,
        "physical_controller_verified": False,
        "production_release_verified": False,
    }


def _get_json(url: str, token: str):
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nexium-intel-readonly-integration-audit",
    })
    with urlopen(request, timeout=30) as response:
        contents = response.read(MAX_RESPONSE_BYTES + 1)
    if len(contents) > MAX_RESPONSE_BYTES:
        raise ValueError("GitHub response exceeds audit limit")
    return json.loads(contents.decode("utf-8"))


def collect_live(repository: str, token: str, *, top_pr: int) -> dict:
    if not REPO_RE.fullmatch(repository):
        raise ValueError("repository name invalid")
    if not token:
        raise ValueError("read-only GitHub token required")
    endpoint = "https://api.github.com/repos/" + repository
    page = 1
    pulls = []
    while True:
        result = _get_json(
            endpoint + "/pulls?state=open&per_page=100&page=" + str(page), token
        )
        if not isinstance(result, list):
            raise ValueError("unexpected GitHub pull-list response")
        for pr in result:
            pulls.append({
                "number": pr["number"],
                "head": pr["head"]["ref"],
                "head_sha": pr["head"]["sha"],
                "base": pr["base"]["ref"],
                "base_sha": pr["base"]["sha"],
                "state": pr["state"],
                "draft": pr["draft"],
            })
        if len(pulls) > MAX_PRS:
            raise ValueError("too many open PRs for bounded audit")
        if len(result) < 100:
            break
        page += 1
    branch = _get_json(endpoint + "/branches/main", token)
    main_sha = branch["commit"]["sha"]
    heads = {pr["head"]: pr for pr in pulls}
    root = next((pr for pr in pulls if pr["number"] == top_pr), None)
    if root is None:
        raise ValueError("top PR not found")
    sequence = []
    visited = set()
    while root is not None:
        if root["number"] in visited:
            raise ValueError("PR cycle discovered while collecting")
        visited.add(root["number"])
        sequence.append(root)
        if root["base"] == "main":
            break
        root = heads.get(root["base"])
        if root is None:
            raise ValueError("missing intermediate pull request")
    compares = []
    for item in sequence:
        # Compare by exact SHA, avoiding ambiguity in branch names containing '/'.
        pair = item["base_sha"] + "..." + item["head_sha"]
        result = _get_json(endpoint + "/compare/" + quote(pair, safe="."), token)
        compares.append({
            "number": item["number"],
            "base_sha": item["base_sha"],
            "head_sha": item["head_sha"],
            "ahead_by": result["ahead_by"],
            "behind_by": result["behind_by"],
            "status": result["status"],
        })
    return {
        "schema": SCHEMA,
        "repository": repository,
        "main_sha": main_sha,
        "pulls": pulls,
        "comparisons": compares,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--top-pr", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--min-depth", type=int, default=28)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.snapshot is None:
            snapshot = collect_live(
                args.repository, os.environ.get("GH_TOKEN", ""),
                top_pr=args.top_pr,
            )
        else:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if snapshot.get("repository") != args.repository:
            raise ValueError("mismatched repository")
        result = audit_snapshot(
            snapshot, top_pr=args.top_pr,
            expected_head_sha=args.expected_head_sha, min_depth=args.min_depth,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, sort_keys=True))
        # Success means read-only classification, not permission to merge!
        print("STAGE59_STACK_AUDIT_REVIEW_REQUIRED")
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError,
            json.JSONDecodeError) as exc:
        # Avoid emitting URLs, token values, or untrusted response text.
        print("STAGE59_STACK_AUDIT_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
