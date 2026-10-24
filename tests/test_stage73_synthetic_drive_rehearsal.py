"""Mock-transport validation of the protected Stage73 synthetic rehearsal."""
import contextlib
import io
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse_stage73_private_drive import run_synthetic_rehearsal, main, PREFLIGHT_MARKER
from archive_private_capture_drive import DriveArchiveRejected
from test_stage73_drive_readback import PARENT, RECEIPTS, COMMIT
from test_stage73_independent_persistence import PersistentFakeTransport


class Stage73SyntheticRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.a = root / "offline-A"
        self.b = root / "offline-B"
        self.a.mkdir()
        self.b.mkdir()
        self.backup = self.a / "anchor.json"
        self.reference = self.b / "digest.json"
        self.transport = PersistentFakeTransport()
        self.args = (self.transport, PARENT, RECEIPTS, "123",
                     COMMIT, self.backup, self.reference)

    def test_synthetic_full_roundtrip_after_runner_expiry(self):
        result = run_synthetic_rehearsal(*self.args)
        self.assertTrue(result["synthetic_only"])
        self.assertTrue(result["independent_remote_readback_verified"])
        self.assertTrue(result["producer_workspace_deleted"])
        self.assertFalse(result["retention_policy_verified"])
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertTrue(self.backup.is_file())
        self.assertTrue(self.reference.is_file())
        self.assertEqual(len(self.transport.files), 4)

    def test_read_only_cli_preflight_creates_no_remote_or_local_objects(self):
        opts = [
            "--capture-parent-id", PARENT,
            "--receipt-parent-id", RECEIPTS,
            "--run-id", "123", "--source-commit", COMMIT,
            "--backup", str(self.backup), "--reference", str(self.reference),
            "--preflight-only",
        ]
        env = {
            "GITHUB_ACTIONS": "",
            "NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
            "NEXIUM_DRIVE_ACCESS_TOKEN": "fake",
        }
        out = io.StringIO()
        with patch.dict(os.environ, env):
            with patch("rehearse_stage73_private_drive.GoogleTransport",
                       return_value=self.transport):
                with contextlib.redirect_stdout(out):
                    outcome = main(opts)
        self.assertEqual(outcome, 0)
        self.assertEqual(out.getvalue(), PREFLIGHT_MARKER + "\n")
        self.assertTrue(self.transport.calls)
        # The preflight is strictly read-only: no create, update, upload, or delete request.
        self.assertTrue(all(method == "GET" for method, _ in self.transport.calls))
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.reference.exists())

    def test_preflight_rejects_symlinked_ancestor_before_drive_requests(self):
        redirect = self.a.parent / "redirect"
        redirect.symlink_to(self.a.parent, target_is_directory=True)
        redirected_backup = redirect / self.a.name / "redirected-anchor.json"
        opts = [
            "--capture-parent-id", PARENT,
            "--receipt-parent-id", RECEIPTS,
            "--run-id", "123", "--source-commit", COMMIT,
            "--backup", str(redirected_backup), "--reference", str(self.reference),
            "--preflight-only",
        ]
        env = {
            "GITHUB_ACTIONS": "",
            "NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
            "NEXIUM_DRIVE_ACCESS_TOKEN": "fake",
        }
        err = io.StringIO()
        with patch.dict(os.environ, env):
            with patch("rehearse_stage73_private_drive.GoogleTransport",
                       return_value=self.transport):
                with contextlib.redirect_stderr(err):
                    outcome = main(opts)
        self.assertEqual(outcome, 1)
        self.assertEqual(
            err.getvalue(), "STAGE73_PRIVATE_SYNTHETIC_DRIVE_REHEARSAL_BLOCKED\n")
        self.assertFalse(self.transport.calls)
        self.assertFalse(redirected_backup.exists())

    def test_shared_parent_rejected_without_remote_writes(self):
        self.transport.shared_ancestor = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            run_synthetic_rehearsal(*self.args)
        self.assertFalse(self.backup.exists())
        self.assertFalse(any(method == "POST" for method, path in self.transport.calls))

    def test_missing_parent_acl_rejected_without_remote_writes(self):
        self.transport.missing_permissions = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            run_synthetic_rehearsal(*self.args)
        self.assertFalse(any(method == "POST" for method, path in self.transport.calls))

    def test_existing_backup_rejected_before_network(self):
        self.backup.write_bytes(b"do not replace my backup")
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_synthetic_backup_paths"):
            run_synthetic_rehearsal(*self.args)
        self.assertEqual(self.backup.read_bytes(), b"do not replace my backup")
        self.assertFalse(self.transport.calls)

    def test_existing_reference_rejected_before_network(self):
        self.reference.write_bytes(b"earlier reference")
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_synthetic_backup_paths"):
            run_synthetic_rehearsal(*self.args)
        self.assertEqual(self.reference.read_bytes(), b"earlier reference")
        self.assertFalse(self.transport.calls)

    def test_same_dir_rejected_before_network(self):
        reference = self.a / "reference.json"
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_synthetic_backup_paths"):
            run_synthetic_rehearsal(
                self.transport, PARENT, RECEIPTS, "123",
                COMMIT, self.backup, reference)
        self.assertFalse(self.transport.calls)

    def test_bad_parent_identity_rejected_before_network(self):
        with self.assertRaisesRegex(DriveArchiveRejected, "invalid_synthetic_rehearsal_inputs"):
            run_synthetic_rehearsal(
                self.transport, PARENT, PARENT, "123",
                COMMIT, self.backup, self.reference)
        self.assertFalse(self.transport.calls)

    def test_tampered_uploaded_payload_fails_closed(self):
        self.transport.bad_media = True
        with self.assertRaises(DriveArchiveRejected):
            run_synthetic_rehearsal(*self.args)
        self.assertFalse(self.backup.exists())

    def test_independent_remote_recheck_failure_not_success(self):
        import rehearse_stage73_private_drive as module
        with patch.object(module, "audit_from_remote_handoff",
                          side_effect=DriveArchiveRejected("synthetic_remote_failed")):
            with self.assertRaises(DriveArchiveRejected):
                run_synthetic_rehearsal(*self.args)
        self.assertTrue(self.backup.exists())
        self.assertTrue(self.reference.exists())

    def test_second_run_id_rejected_before_any_new_remote_write(self):
        self.assertTrue(run_synthetic_rehearsal(*self.args)["synthetic_only"])
        first_remote_writes = sum(method == "POST"
                                  for method, _ in self.transport.calls)
        second_backup = self.a / "different-backup.json"
        second_reference = self.b / "different-reference.json"
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "synthetic_run_identity_not_unique"):
            run_synthetic_rehearsal(
                self.transport, PARENT, RECEIPTS, "123", COMMIT,
                second_backup, second_reference,
            )
        self.assertEqual(first_remote_writes, sum(
            method == "POST" for method, _ in self.transport.calls))
        self.assertFalse(second_backup.exists())
        self.assertFalse(second_reference.exists())

    def test_existing_capture_folder_rejected_before_remote_write(self):
        self.transport.force_capture_run_collision = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "synthetic_run_identity_not_unique"):
            run_synthetic_rehearsal(*self.args)
        self.assertFalse(any(method == "POST"
                             for method, _ in self.transport.calls))

    def test_incomplete_collision_search_is_not_assumed_empty(self):
        self.transport.force_incomplete_preflight_listing = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "synthetic_run_identity_not_unique"):
            run_synthetic_rehearsal(*self.args)
        self.assertFalse(any(method == "POST"
                             for method, _ in self.transport.calls))

    def test_preflight_checks_both_destination_acls_before_writes(self):
        self.transport.shared_parent = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            run_synthetic_rehearsal(*self.args)
        self.assertFalse(any(method == "POST"
                             for method, _ in self.transport.calls))

    def test_cli_disabled_on_github_actions_even_with_arm(self):
        opts = [
            "--capture-parent-id", PARENT,
            "--receipt-parent-id", RECEIPTS,
            "--run-id", "123", "--source-commit", COMMIT,
            "--backup", str(self.backup), "--reference", str(self.reference),
        ]
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true",
                                      "NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
                                      "NEXIUM_DRIVE_ACCESS_TOKEN": "fake"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                outcome = main(opts)
        self.assertEqual(outcome, 1)
        self.assertEqual(err.getvalue(), "STAGE73_PRIVATE_SYNTHETIC_DRIVE_REHEARSAL_BLOCKED\n")
        self.assertFalse(self.transport.calls)


if __name__ == "__main__":
    unittest.main()
