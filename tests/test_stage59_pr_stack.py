"""Stage59 synthetic tests for read-only, fail-closed stacked PR ancestry audit."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_intel_pr_stack import audit_snapshot, normalize_current_bases, SCHEMA

IDS = [61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51, 45, 44, 41,
       39, 38, 36, 34, 26, 22, 16, 15, 12, 10, 6, 4, 2, 1]
REPO = "stanmasked/nexium-macos-intel"


def sha(n: int) -> str:
    return f"{n:040x}"


def fixture():
    prs = []
    compares = []
    for index, n in enumerate(IDS):
        next_n = IDS[index + 1] if index + 1 < len(IDS) else None
        prs.append({
            "number": n,
            "head": f"work/pr-{n}",
            "head_sha": sha(n),
            "base": f"work/pr-{next_n}" if next_n is not None else "main",
            "base_sha": sha(next_n) if next_n is not None else sha(999),
            "state": "open",
            "draft": True,
        })
        behind = {16: 1, 39: 2, 41: 1}.get(n, 0)
        compares.append({
            "number": n, "head_sha": sha(n),
            "base_sha": sha(next_n) if next_n is not None else sha(999),
            "ahead_by": 3, "behind_by": behind,
            "status": "diverged" if behind else "ahead",
        })
    return {
        "schema": SCHEMA, "repository": REPO,
        "main_sha": sha(999), "pulls": prs, "comparisons": compares,
    }


class Stage59StackAuditTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = fixture()

    def check(self):
        return audit_snapshot(
            self.snapshot, top_pr=61, expected_head_sha=sha(61),
            min_depth=28,
        )

    def test_all_28_ancestors_classified_but_merge_not_approved(self):
        result = self.check()
        self.assertEqual(result["pr_chain_checked"], 28)
        self.assertEqual(result["root_pr"], 1)
        self.assertEqual(result["top_pr"], 61)
        self.assertEqual(result["diverged_edges"], [
            {"pr": 16, "base_commits_missing": 1},
            {"pr": 39, "base_commits_missing": 2},
            {"pr": 41, "base_commits_missing": 1},
        ])
        self.assertTrue(result["integration_requires_review"])
        self.assertFalse(result["main_merge_approved"])

    def test_no_divergence_still_never_authorizes_merge(self):
        for item in self.snapshot["comparisons"]:
            item["behind_by"] = 0
            item["status"] = "ahead"
        result = self.check()
        self.assertEqual(result["diverged_edges"], [])
        self.assertFalse(result["main_merge_approved"])

    def test_unrelated_non_draft_pr_is_irrelevant_to_stack(self):
        self.snapshot["pulls"].append({
            "number": 700, "head": "external-feature",
            "head_sha": sha(700), "base": "main",
            "base_sha": sha(999), "state": "open", "draft": False,
        })
        self.assertEqual(self.check()["pr_chain_checked"], 28)

    def test_missing_ancestor_rejected(self):
        self.snapshot["pulls"] = [
            pr for pr in self.snapshot["pulls"] if pr["number"] != 39
        ]
        with self.assertRaisesRegex(ValueError, "missing intermediate"):
            self.check()

    def test_unexpected_closed_ancestor_rejected(self):
        self.snapshot["pulls"][4]["state"] = "closed"
        with self.assertRaisesRegex(ValueError, "not an open Draft"):
            self.check()

    def test_non_draft_ancestor_rejected(self):
        self.snapshot["pulls"][4]["draft"] = False
        with self.assertRaisesRegex(ValueError, "not an open Draft"):
            self.check()

    def test_stale_github_pr_base_sha_is_normalized_to_live_parent(self):
        # GitHub pull-list base.sha may be the historical PR diff baseline.
        child = self.snapshot["pulls"][13]  # #41, base of #39
        self.assertEqual(child["number"], 41)
        child["base_sha"] = sha(888)
        normalize_current_bases(self.snapshot["pulls"], sha(999))
        self.assertEqual(child["reported_base_sha"], sha(888))
        self.assertEqual(child["base_sha"], sha(39))
        self.assertEqual(self.check()["pr_chain_checked"], 28)

    def test_current_parent_comparison_still_exposes_old_branch_divergence(self):
        for child in self.snapshot["pulls"]:
            child["base_sha"] = sha(777)
        normalize_current_bases(self.snapshot["pulls"], sha(999))
        result = self.check()
        self.assertEqual(
            [x["pr"] for x in result["diverged_edges"]], [16, 39, 41]
        )
        self.assertFalse(result["main_merge_approved"])

    def test_wrong_base_head_sha_rejected(self):
        self.snapshot["pulls"][0]["base_sha"] = sha(888)
        with self.assertRaisesRegex(ValueError, "base ref shifted"):
            self.check()

    def test_wrong_root_main_head_rejected(self):
        self.snapshot["main_sha"] = sha(777)
        with self.assertRaisesRegex(ValueError, "root PR"):
            self.check()

    def test_cycle_rejected(self):
        self.snapshot["pulls"][-1]["base"] = self.snapshot["pulls"][0]["head"]
        self.snapshot["pulls"][-1]["base_sha"] = self.snapshot["pulls"][0]["head_sha"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.check()

    def test_top_head_commit_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "top PR head changed"):
            audit_snapshot(self.snapshot, top_pr=61,
                           expected_head_sha=sha(888), min_depth=28)

    def test_missing_compare_rejected(self):
        self.snapshot["comparisons"].pop()
        with self.assertRaisesRegex(ValueError, "every ancestor"):
            self.check()

    def test_duplicate_compare_rejected(self):
        self.snapshot["comparisons"].append(
            copy.deepcopy(self.snapshot["comparisons"][0])
        )
        with self.assertRaisesRegex(ValueError, "required refs or counters"):
            self.check()

    def test_compare_refs_must_match_pr(self):
        self.snapshot["comparisons"][0]["head_sha"] = sha(888)
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.check()

    def test_negative_behind_rejected(self):
        self.snapshot["comparisons"][0]["behind_by"] = -1
        with self.assertRaises(ValueError):
            self.check()

    def test_boolean_ahead_rejected(self):
        self.snapshot["comparisons"][0]["ahead_by"] = True
        with self.assertRaises(ValueError):
            self.check()

    def test_compare_status_mismatch_rejected(self):
        self.snapshot["comparisons"][0]["status"] = "diverged"
        with self.assertRaisesRegex(ValueError, "status disagrees"):
            self.check()

    def test_unexpected_new_divergence_not_silenced(self):
        item = self.snapshot["comparisons"][0]
        item["behind_by"] = 7
        item["status"] = "diverged"
        result = self.check()
        self.assertIn({"pr": 61, "base_commits_missing": 7},
                      result["diverged_edges"])
        self.assertFalse(result["main_merge_approved"])

    def test_shallow_depth_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpectedly shallow"):
            audit_snapshot(self.snapshot, top_pr=61,
                           expected_head_sha=sha(61), min_depth=29)

    def test_duplicate_pr_head_rejected(self):
        self.snapshot["pulls"][3]["head"] = self.snapshot["pulls"][2]["head"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.check()

    def test_wrong_snapshot_schema_rejected(self):
        self.snapshot["schema"] = "unknown"
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            self.check()


if __name__ == "__main__":
    unittest.main()
