"""Stage60 no-network Git tree rehearsal: local repositories only."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse_intel_pr_merge import (
    git, local_merge_chain, check_reconciled_sources, conflicted_filenames,
)


def require(run):
    if run.returncode != 0:
        raise RuntimeError("synthetic git fixture operation failed")
    return run.stdout.strip()


class Stage60LocalMergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        require(git(self.root, "init", "-q"))
        self.seed = self.commit("seed.txt", "original\n")

    def commit(self, filename: str, value: str) -> str:
        f = self.root / filename
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(value, encoding="utf-8")
        require(git(self.root, "add", "--", filename))
        require(git(self.root, "commit", "-q", "-m", "fixture"))
        return require(git(self.root, "rev-parse", "HEAD"))

    def test_fast_forward_sequence(self):
        one = self.commit("one.txt", "first\n")
        two = self.commit("two.txt", "second\n")
        result = local_merge_chain(self.root, self.seed,
                                   [{"number": 1, "head_sha": one},
                                    {"number": 2, "head_sha": two}])
        self.assertTrue(result["merge_tree_complete"])
        self.assertEqual(result["_temporary_commit_sha"], two)
        self.assertEqual(
            [x["result"] for x in result["classification"]],
            ["fast_forward", "fast_forward"],
        )
        self.assertFalse(result["main_merge_approved"])

    def test_nonoverlapping_divergence_can_make_virtual_merge(self):
        left = self.commit("left.txt", "left\n")
        require(git(self.root, "checkout", "-q", "--detach", self.seed))
        right = self.commit("right.txt", "right\n")
        branch = require(git(self.root, "rev-parse", "HEAD"))
        result = local_merge_chain(
            self.root, self.seed,
            [{"number": 1, "head_sha": left},
             {"number": 2, "head_sha": right}],
        )
        self.assertTrue(result["merge_tree_complete"])
        self.assertEqual(result["classification"][-1]["result"], "automatic_merge")
        combined = result["_temporary_commit_sha"]
        self.assertEqual(require(git(self.root, "show", combined + ":left.txt")), "left")
        self.assertEqual(require(git(self.root, "show", combined + ":right.txt")), "right")
        self.assertEqual(require(git(self.root, "rev-parse", "HEAD")), branch)

    def test_conflicting_divergence_is_blocked_not_autoresolved(self):
        left = self.commit("seed.txt", "left\n")
        require(git(self.root, "checkout", "-q", "--detach", self.seed))
        right = self.commit("seed.txt", "right\n")
        result = local_merge_chain(
            self.root, self.seed,
            [{"number": 1, "head_sha": left},
             {"number": 2, "head_sha": right}],
        )
        self.assertFalse(result["merge_tree_complete"])
        self.assertEqual(result["classification"][-1],
                         {"pr": 2, "result": "conflict",
                          "conflicted_files": ["seed.txt"]})
        self.assertFalse(result["main_merge_approved"])
        self.assertEqual(require(git(self.root, "rev-parse", "HEAD")), right)

    def test_conflict_report_must_be_bounded_relative_public_path(self):
        fake_tree = "f" * 40
        for path in ("../secret.txt", "/tmp/log", "./file.txt",
                     "dir//file.txt", "bad\\x00name"):
            with self.subTest(path=repr(path)):
                with self.assertRaisesRegex(ValueError, "untrusted"):
                    conflicted_filenames(fake_tree + "\\n" + path + "\\n\\n")

    def test_missing_conflict_filename_blocks_report(self):
        with self.assertRaisesRegex(ValueError, "lacks unique filenames"):
            conflicted_filenames("f" * 40 + "\\n\\n")

    def test_already_included_commit_explicitly_classified(self):
        a = self.commit("a", "a")
        b = self.commit("b", "b")
        result = local_merge_chain(
            self.root, self.seed,
            [{"number": 1, "head_sha": b},
             {"number": 2, "head_sha": a}],
        )
        self.assertEqual(result["classification"][1]["result"], "already_included")
        self.assertFalse(result["main_merge_approved"])

    def test_wrong_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            local_merge_chain(self.root, self.seed,
                              [{"number": 1, "head_sha": "not-a-sha"}])

    def test_missing_git_object_rejected(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            local_merge_chain(self.root, self.seed,
                              [{"number": 1, "head_sha": "f" * 40}])

    def test_duplicate_pr_number_rejected(self):
        a = self.commit("a", "a")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            local_merge_chain(self.root, self.seed,
                              [{"number": 1, "head_sha": a},
                               {"number": 1, "head_sha": a}])

    def test_zero_pr_number_rejected(self):
        a = self.commit("a", "a")
        with self.assertRaisesRegex(ValueError, "malformed"):
            local_merge_chain(self.root, self.seed,
                              [{"number": 0, "head_sha": a}])

    def test_malformed_main_sha_rejected(self):
        a = self.commit("a", "a")
        with self.assertRaisesRegex(ValueError, "main revision"):
            local_merge_chain(self.root, "main",
                              [{"number": 1, "head_sha": a}])

    def test_reconciled_source_checker_blocks_incomplete_tree(self):
        with self.assertRaisesRegex(ValueError, "marker absent"):
            check_reconciled_sources(self.root, self.seed)

    def test_reconciled_source_checker_accepts_all_guarded_sources(self):
        sources = {
            ".github/workflows/nexium-macos-probe.yml":
                "audio_init_marker_01_intentionally_omitted\n"
                "Stage57 validate file-backed Mach-O segment and section bounds\n",
            "scripts/audit_npad_lifo_trace.py":
                "NO_NPAD_TICK_OBSERVED_NO_NRO\n"
                "NPAD_LIFO_TRACE_OBSERVED_B_ROUND_TRIP_NOT_CONFIRMED\n",
            "tests/test_npad_lifo_trace.py":
                "test_no_guest_tick_without_nro_is_classified_not_claimed_as_success\n"
                "test_guest_tick_without_round_trip_remains_unconfirmed\n",
            "scripts/audit_guest_hid_mapping_path.py":
                "has_zero_handle_warning = False\n"
                "if 'if handle == 0 {' in map_svc:\n",
            "scripts/audit_intel_macho_segment_bounds.py":
                "segment_bounds_passed\n",
            "scripts/audit_intel_pr_stack.py":
                "main_merge_approved\n",
        }
        for path, value in sources.items():
            self.commit(path, value)
        latest = require(git(self.root, "rev-parse", "HEAD"))
        check_reconciled_sources(self.root, latest)


if __name__ == "__main__":
    unittest.main()
