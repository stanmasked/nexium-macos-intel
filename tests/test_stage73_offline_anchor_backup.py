"""Stage73 private anchor offline recovery: synthetic only, never real logs."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_private_capture_drive import DriveArchiveRejected
from backup_stage73_private_anchor import (
    backup_offline_anchor, verify_offline_anchor, main,
)
from test_stage73_drive_readback import COMMIT, PARENT, RECEIPTS


class OfflineAnchorBackupTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.disposable = self.root / "disposable"
        self.disposable.mkdir()
        self.report = self.disposable / "report"
        self.report.mkdir()
        self.original_dir = self.root / "original-private"
        self.backup_dir = self.root / "backup-private"
        self.reference_dir = self.root / "reference-private"
        for p in (self.original_dir, self.backup_dir, self.reference_dir):
            p.mkdir()
        self.original = self.original_dir / "anchor.json"
        self.backup = self.backup_dir / "archive-anchor.json"
        self.reference = self.reference_dir / "digest-reference.json"
        self.anchor = {
            "schema": "nexium-stage73-independent-receipt-anchor/v1",
            "privacy": "private", "source_commit": COMMIT, "run_id": "123",
            "capture_parent_id": PARENT, "receipt_parent_id": RECEIPTS,
            "receipt_sha256": "a" * 64, "receipt_remote_readback_verified": True,
            "anchor_remote_retention_verified": False,
            "guest_gpu_frames_verified": False,
        }
        self.original.write_text(json.dumps(self.anchor))
        self.original.chmod(0o600)
        self.parameters = {
            "source_commit": COMMIT, "run_id": "123",
            "capture_parent": PARENT, "receipt_parent": RECEIPTS,
        }

    def save(self):
        return backup_offline_anchor(
            self.original, self.backup, self.reference,
            disposable_root=self.disposable, **self.parameters)

    def restore(self):
        return verify_offline_anchor(
            self.backup, self.reference, **self.parameters)

    def test_restores_after_original_deleted(self):
        saved = self.save()
        self.assertTrue(saved["independent_copy_readback_verified"])
        self.assertFalse(saved["remote_retention_verified"])
        self.original.unlink()
        self.assertTrue(self.restore()["independent_copy_readback_verified"])
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.reference.stat().st_mode & 0o777, 0o600)

    def test_backup_refuses_overwrite(self):
        self.backup.write_text("older private backup")
        with self.assertRaisesRegex(DriveArchiveRejected, "backup_collision"):
            self.save()
        self.assertEqual(self.backup.read_text(), "older private backup")

    def test_reference_refuses_overwrite(self):
        self.reference.write_text("older private reference")
        with self.assertRaisesRegex(DriveArchiveRejected, "backup_collision"):
            self.save()
        self.assertEqual(self.reference.read_text(), "older private reference")

    def test_forged_backup_detected(self):
        self.save()
        self.backup.write_text(json.dumps({**self.anchor, "receipt_sha256": "b" * 64}))
        with self.assertRaises(DriveArchiveRejected):
            self.restore()

    def test_forged_reference_detected(self):
        self.save()
        record = json.loads(self.reference.read_text())
        record["source_commit"] = "b" * 40
        self.reference.write_text(json.dumps(record))
        with self.assertRaises(DriveArchiveRejected):
            self.restore()

    def test_world_readable_copy_rejected(self):
        self.save()
        self.backup.chmod(0o644)
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_private_file"):
            self.restore()

    def test_symlinked_copy_rejected(self):
        self.save()
        self.backup.unlink()
        self.backup.symlink_to(self.original)
        with self.assertRaises(DriveArchiveRejected):
            self.restore()

    def test_shared_parent_directory_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            self.backup_dir.rmdir()
            self.backup_dir.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_private_parent"):
                self.save()

    def test_disposable_source_with_external_backups_is_valid(self):
        new_source_dir = self.disposable / "private-anchor"
        new_source_dir.mkdir()
        ephemeral_anchor = new_source_dir / "anchor.json"
        ephemeral_anchor.write_bytes(self.original.read_bytes())
        ephemeral_anchor.chmod(0o600)
        saved = backup_offline_anchor(
            ephemeral_anchor, self.backup, self.reference,
            disposable_root=self.disposable, **self.parameters,
        )
        self.assertTrue(saved["independent_copy_readback_verified"])
        ephemeral_anchor.unlink()
        self.assertTrue(self.restore()["independent_copy_readback_verified"])

    def test_copy_in_disposable_tree_rejected(self):
        backup = self.disposable / "forbidden"
        with self.assertRaisesRegex(DriveArchiveRejected, "backup_inside_disposable_workspace"):
            backup_offline_anchor(self.original, backup, self.reference,
                                  disposable_root=self.disposable, **self.parameters)

    def test_copy_and_reference_same_dir_rejected(self):
        reference = self.backup_dir / "reference"
        with self.assertRaisesRegex(DriveArchiveRejected, "not_independent_destinations"):
            backup_offline_anchor(self.original, self.backup, reference,
                                  disposable_root=self.disposable, **self.parameters)

    def test_source_symlink_rejected(self):
        shadow = self.original_dir / "symlink"
        shadow.symlink_to(self.original)
        with self.assertRaises(DriveArchiveRejected):
            backup_offline_anchor(shadow, self.backup, self.reference,
                                  disposable_root=self.disposable, **self.parameters)

    def test_reference_missing_after_source_deleted(self):
        self.save()
        self.original.unlink()
        self.reference.unlink()
        with self.assertRaises(DriveArchiveRejected):
            self.restore()

    def test_invalid_identity_fails_before_backup(self):
        with self.assertRaisesRegex(DriveArchiveRejected, "invalid_backup_identity"):
            backup_offline_anchor(self.original, self.backup, self.reference,
                                  disposable_root=self.disposable,
                                  **{**self.parameters, "source_commit": "not-a-commit"})
        self.assertFalse(self.backup.exists())

    def test_cli_fails_closed_inside_github_actions(self):
        args = ["backup", "--source", str(self.original),
                "--backup", str(self.backup), "--reference", str(self.reference),
                "--disposable-root", str(self.disposable),
                "--source-commit", COMMIT, "--run-id", "123",
                "--capture-parent", PARENT, "--receipt-parent", RECEIPTS]
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = main(args)
        self.assertEqual(rc, 1)
        self.assertEqual(err.getvalue(), "STAGE73_PRIVATE_ANCHOR_NOT_VERIFIED\n")
        self.assertFalse(self.backup.exists())


if __name__ == "__main__":
    unittest.main()
