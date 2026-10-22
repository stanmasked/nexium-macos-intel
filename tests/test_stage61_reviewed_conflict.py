"""Stage61 isolated Git fixtures for explicitly reviewed HID conflict handling."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse_intel_reviewed_conflict import (
    CONFLICT_FILE, REVIEWED_BLOB, rehearsal, substitute_one_reviewed_blob,
    verify_reviewed_blob,
)
from rehearse_intel_pr_merge import git


def good(run):
    if run.returncode != 0:
        raise RuntimeError("synthetic Git fixture failed")
    return run.stdout.strip()


class Stage61ReviewedConflictTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        good(git(self.repo, "init", "-q"))
        # Seed *only* public source markers used by the Stage60 merge audit.
        public_source = Path(__file__).resolve().parents[1] / CONFLICT_FILE
        source = public_source.read_text(encoding="utf-8")
        self.assertIn("has_zero_handle_warning = False", source)
        file = self.repo / CONFLICT_FILE
        file.parent.mkdir(parents=True)
        file.write_text(source, encoding="utf-8")
        placeholders = {
            ".github/workflows/nexium-macos-probe.yml":
                "audio_init_marker_01_intentionally_omitted\n"
                "Stage57 validate file-backed Mach-O segment and section bounds\n",
            "scripts/audit_npad_lifo_trace.py":
                "NO_NPAD_TICK_OBSERVED_NO_NRO\n"
                "NPAD_LIFO_TRACE_OBSERVED_B_ROUND_TRIP_NOT_CONFIRMED\n",
            "tests/test_npad_lifo_trace.py":
                "test_no_guest_tick_without_nro_is_classified_not_claimed_as_success\n"
                "test_guest_tick_without_round_trip_remains_unconfirmed\n",
            "scripts/audit_intel_macho_segment_bounds.py": "segment_bounds_passed\n",
            "scripts/audit_intel_pr_stack.py": "main_merge_approved\n",
        }
        for name, value in placeholders.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        good(git(self.repo, "add", "."))
        good(git(self.repo, "commit", "-q", "-m", "seed"))
        self.base = good(git(self.repo, "rev-parse", "HEAD"))
        blob = good(git(self.repo, "rev-parse", self.base + ":" + CONFLICT_FILE))
        self.assertEqual(blob, REVIEWED_BLOB)
        self.source = source

    def write_commit(self, path: str, contents: str) -> str:
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(contents, encoding="utf-8")
        good(git(self.repo, "add", "--", path))
        good(git(self.repo, "commit", "-q", "-m", "fixture"))
        return good(git(self.repo, "rev-parse", "HEAD"))

    def conflicting_heads(self):
        ours = self.write_commit(
            CONFLICT_FILE,
            self.source.replace(
                "has_zero_handle_warning = False",
                "has_zero_handle_warning = True", 1,
            ),
        )
        good(git(self.repo, "checkout", "-q", "--detach", self.base))
        theirs = self.write_commit(
            CONFLICT_FILE,
            self.source.replace(
                "has_zero_handle_warning = False",
                "has_zero_handle_warning = None", 1,
            ),
        )
        return ours, theirs

    def test_reviewed_exact_hid_resolution_passes_without_head_changes(self):
        ours, theirs = self.conflicting_heads()
        head_before = good(git(self.repo, "rev-parse", "HEAD"))
        result = rehearsal(self.repo, self.base, [
            {"number": 41, "head_sha": ours},
            {"number": 44, "head_sha": theirs},
        ])
        self.assertTrue(result["combined_tree_complete"])
        self.assertTrue(result["reviewed_resolution_applied_locally"])
        self.assertTrue(result["reconciled_source_contracts_verified"])
        self.assertEqual(result["classification"][-1]["result"],
                         "reviewed_local_resolution")
        self.assertFalse(result["main_merge_approved"])
        self.assertEqual(good(git(self.repo, "rev-parse", "HEAD")), head_before)

    def test_different_pr_conflict_is_not_resolved(self):
        ours, theirs = self.conflicting_heads()
        result = rehearsal(self.repo, self.base, [
            {"number": 41, "head_sha": ours},
            {"number": 45, "head_sha": theirs},
        ])
        self.assertFalse(result["combined_tree_complete"])
        self.assertFalse(result["reviewed_resolution_applied_locally"])
        self.assertEqual(result["classification"][-1]["conflicted_files"],
                         [CONFLICT_FILE])

    def test_wrong_reviewed_blob_identity_fails_closed(self):
        ours, theirs = self.conflicting_heads()
        with self.assertRaisesRegex(ValueError, "reviewed blob identity"):
            rehearsal(self.repo, self.base, [
                {"number": 41, "head_sha": ours},
                {"number": 44, "head_sha": theirs},
            ], reviewed_blob="a" * 40)

    def test_no_integration_claim_even_on_clean_lineage(self):
        first = self.write_commit("newfile.txt", "test\n")
        result = rehearsal(
            self.repo, self.base, [{"number": 1, "head_sha": first}],
        )
        self.assertTrue(result["combined_tree_complete"])
        self.assertFalse(result["reviewed_resolution_applied_locally"])
        self.assertFalse(result["main_merge_approved"])

    def test_wrong_candidate_file_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "unexpected conflict"):
            substitute_one_reviewed_blob(
                self.repo, self.base, REVIEWED_BLOB, "scripts/other.py"
            )

    def test_reviewer_rejects_wrong_sha_before_materialization(self):
        with self.assertRaisesRegex(ValueError, "reviewed blob identity"):
            verify_reviewed_blob(self.repo, "b" * 40)


if __name__ == "__main__":
    unittest.main()
