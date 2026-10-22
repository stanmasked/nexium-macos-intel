"""Stage73 exact scoped IPC request logging patch and source identity checks."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_display_ipc_trace import (
    ANCHOR, REPLACEMENT, PINNED_UPSTREAM_COMMIT, SOURCE_RELATIVE_PATH,
    git_blob_sha, patch_scoped_ipc_request_log,
)


class Stage73ScopedIpcPatchTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.path = self.root / SOURCE_RELATIVE_PATH
        self.path.parent.mkdir(parents=True)
        self.receipt = self.root / "receipt" / "display-ipc.json"
        self.original = (
            "fn send_sync_request() {\n" + ANCHOR +
            "\n        dispatch_request();\n"
            "        log::trace!(\"SVC {:#04x}\", imm);\n"
            "}\n"
        )
        self.path.write_text(self.original)

    def patch(self, expected=None):
        if expected is None:
            expected = git_blob_sha(self.path.read_bytes())
        return patch_scoped_ipc_request_log(
            self.root, self.receipt, expected_blob_sha=expected
        )

    def test_only_one_ipc_request_log_level_changes(self):
        report = self.patch()
        changed = self.path.read_text()
        self.assertEqual(changed.count(REPLACEMENT), 1)
        self.assertNotIn(ANCHOR, changed)
        self.assertIn('log::trace!("SVC {:#04x}", imm);', changed)
        self.assertEqual(report["upstream_commit"], PINNED_UPSTREAM_COMMIT)
        self.assertTrue(report["only_ipc_request_log_level_changed"])
        self.assertFalse(report["guest_or_service_behavior_changed"])
        self.assertFalse(report["main_merge_approved"])
        self.assertEqual(json.loads(self.receipt.read_text()), report)

    def test_wrong_source_blob_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            self.patch("f" * 40)
        self.assertEqual(self.path.read_text(), self.original)
        self.assertFalse(self.receipt.exists())

    def test_missing_anchor_rejected(self):
        self.path.write_text("fn send_sync_request() {}\n")
        with self.assertRaisesRegex(ValueError, "anchor must match"):
            self.patch()

    def test_duplicate_anchor_rejected(self):
        self.path.write_text(self.original + ANCHOR + "\n")
        with self.assertRaisesRegex(ValueError, "anchor must match"):
            self.patch()

    def test_symlinked_source_rejected(self):
        other = self.root / "svc-real.rs"
        other.write_text(self.original)
        self.path.unlink()
        self.path.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "missing, linked"):
            self.patch()

    def test_linked_source_root_rejected(self):
        alias = self.root / "source-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "root is missing or linked"):
            patch_scoped_ipc_request_log(
                alias, self.receipt, expected_blob_sha=git_blob_sha(self.path.read_bytes())
            )

    def test_unexpected_upstream_blob_does_not_mutate_file(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            self.patch("0" * 40)
        self.assertEqual(self.path.read_bytes(), before)

    def test_receipt_does_not_claim_runtime_or_gpu_success(self):
        report = self.patch()
        self.assertFalse(report.get("guest_gpu_frames_verified", False))
        self.assertFalse(report.get("main_merge_approved", False))
        self.assertFalse(report.get("raw_logs_uploaded", True))


if __name__ == "__main__":
    unittest.main()
