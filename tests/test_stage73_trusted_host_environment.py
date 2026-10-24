"""Stage73 private CLI guards: no network, credentials or original data."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stage73_trusted_host_guard import CI_ENV_MARKERS, is_known_ci_host
import archive_private_capture_drive as upload
import verify_stage73_private_drive_persistence as audit
import rehearse_stage73_private_drive as rehearsal
import backup_stage73_private_anchor as backup


class KnownCIEnvironmentTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        commit = "a" * 40
        a, b = "A" * 24, "B" * 24
        self.cases = (
            (rehearsal.main, [
                "--capture-parent-id", a, "--receipt-parent-id", b,
                "--run-id", "123", "--source-commit", commit,
                "--backup", str(self.root / "copy"), "--reference", str(self.root / "hash"),
            ], "STAGE73_PRIVATE_SYNTHETIC_DRIVE_REHEARSAL_BLOCKED"),
            (upload.main, [
                "--report", str(self.root / "report"), "--manifest", str(self.root / "manifest"),
                "--parent-id", a, "--run-id", "123", "--receipt-parent-id", b,
                "--receipt-path", str(self.root / "receipt"), "--anchor-path", str(self.root / "anchor"),
            ], "STAGE73_PRIVATE_DRIVE_ARCHIVE_BLOCKED"),
            (audit.main, [
                "--parent-id", a, "--receipt-parent-id", b, "--run-id", "123",
                "--source-commit", commit, "--expected-receipt-sha256", "b" * 64,
            ], "STAGE73_PRIVATE_REMOTE_PERSISTENCE_UNVERIFIED"),
            (backup.main, [
                "backup", "--source", str(self.root / "source"),
                "--backup", str(self.root / "copy"), "--reference", str(self.root / "hash"),
                "--source-commit", commit, "--run-id", "123",
                "--capture-parent", a, "--receipt-parent", b,
                "--disposable-root", str(self.root / "producer"),
            ], "STAGE73_PRIVATE_ANCHOR_NOT_VERIFIED"),
        )

    def test_markers_fail_closed_even_if_text_says_false(self):
        for key in CI_ENV_MARKERS:
            with self.subTest(key=key):
                self.assertTrue(is_known_ci_host({key: "true"}))
                self.assertTrue(is_known_ci_host({key: "false"}))
                self.assertFalse(is_known_ci_host({key: ""}))

    def test_no_marker_not_a_trust_assertion(self):
        self.assertFalse(is_known_ci_host({}))

    def test_four_private_clis_reject_other_ci_before_io(self):
        for key in ("CI", "CIRCLECI", "GITLAB_CI", "BUILDKITE", "JENKINS_URL"):
            for entry, args, marker in self.cases:
                with self.subTest(key=key, entry=entry.__module__):
                    env = {"NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
                           "NEXIUM_DRIVE_ACCESS_TOKEN": "synthetic-only", key: "true"}
                    err = io.StringIO()
                    with patch.dict(os.environ, env, clear=True):
                        with patch("rehearse_stage73_private_drive.GoogleTransport") as drive_rehearsal, \
                             patch("archive_private_capture_drive.GoogleTransport") as drive_upload, \
                             patch("verify_stage73_private_drive_persistence.GoogleTransport") as drive_audit, \
                             patch("backup_stage73_private_anchor.backup_offline_anchor") as write_copy:
                            with contextlib.redirect_stderr(err):
                                outcome = entry(args)
                            drive_rehearsal.assert_not_called()
                            drive_upload.assert_not_called()
                            drive_audit.assert_not_called()
                            write_copy.assert_not_called()
                    self.assertEqual(outcome, 1)
                    self.assertEqual(err.getvalue(), marker + "\n")
                    self.assertFalse(any(self.root.iterdir()))

    def test_preflight_mode_refuses_circleci_before_transport(self):
        entry, args, marker = self.cases[0]
        err = io.StringIO()
        env = {"NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
               "NEXIUM_DRIVE_ACCESS_TOKEN": "synthetic-only", "CIRCLECI": "true"}
        with patch.dict(os.environ, env, clear=True):
            with patch("rehearse_stage73_private_drive.GoogleTransport") as transport:
                with contextlib.redirect_stderr(err):
                    outcome = entry(args + ["--preflight-only"])
                transport.assert_not_called()
        self.assertEqual(outcome, 1)
        self.assertEqual(err.getvalue(), marker + "\n")


if __name__ == "__main__":
    unittest.main()
