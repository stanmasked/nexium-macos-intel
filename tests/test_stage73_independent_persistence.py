"""Synthetic independent Drive audit: no credentials or network access."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_private_capture_drive import upload_archive
from test_stage73_drive_readback import FakeTransport, PARENT, COMMIT, MACHO, NRO
from seal_private_capture import build_manifest, write_manifest
from verify_stage73_private_drive_persistence import (
    DriveArchiveRejected, audit_remote, main, validate_remote_manifest,
)


class PersistentFakeTransport(FakeTransport):
    def call(self, method, path, body=b"", headers=None, limit=16384):
        u = urlsplit(path)
        if method == "GET" and u.path == "/drive/v3/files/folder00000001":
            return 200, {}, json.dumps({
                "id": "folder00000001", "name": "stage73-123-" + COMMIT[:12],
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": False, "shared": self.shared_capture, "parents": [PARENT],
            }).encode()
        if method == "GET" and u.path == "/drive/v3/files":
            records = []
            for file_id, (meta, content) in self.files.items():
                records.append({
                    "id": file_id, "name": meta["name"],
                    "mimeType": meta["mimeType"], "parents": meta["parents"],
                    "trashed": False, "shared": self.shared_capture,
                    "size": str(len(content)),
                })
            return 200, {}, json.dumps({"files": records}).encode()
        return super().call(method, path, body=body, headers=headers, limit=limit)


class IndependentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        report = self.root / "report"
        report.mkdir()
        log = report / "data-root/logs/nexium-synthetic.log"
        log.parent.mkdir(parents=True)
        log.write_bytes(b"synthetic original log")
        (report / "smoke_result.json").write_text("{}")
        self.manifest_path = self.root / "private-manifest.json"
        write_manifest(self.manifest_path,
                       build_manifest(report, COMMIT, MACHO, NRO), report)
        self.saved_sha = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        self.transport = PersistentFakeTransport()
        upload_archive(report, self.manifest_path, PARENT, "123", self.transport)
        # Simulate expiry/deletion of the original temporary runner.
        self.tmp.cleanup()

    def check(self, **updates):
        values = {"transport": self.transport, "parent_id": PARENT,
                  "folder_id": "folder00000001", "run_id": "123",
                  "commit": COMMIT, "manifest_sha256": self.saved_sha}
        values.update(updates)
        return audit_remote(**values)

    def test_independent_readback_after_original_deleted(self):
        result = self.check()
        self.assertTrue(result["remote_independent_readback_verified"])
        self.assertFalse(result["retention_policy_verified"])
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_remote_tamper_rejected_after_original_deleted(self):
        first = next(iter(self.transport.files))
        meta, _ = self.transport.files[first]
        self.transport.files[first] = (meta, b"altered bytes")
        with self.assertRaises(DriveArchiveRejected):
            self.check()

    def test_expected_manifest_digest_must_match(self):
        with self.assertRaisesRegex(DriveArchiveRejected, "manifest_digest_mismatch"):
            self.check(manifest_sha256="f" * 64)

    def test_source_commit_is_independent(self):
        with self.assertRaises(DriveArchiveRejected):
            self.check(commit="d" * 40)

    def test_wrong_parent_rejected(self):
        with self.assertRaises(DriveArchiveRejected):
            self.check(parent_id="differentParent1234")

    def test_shared_remote_content_rejected(self):
        self.transport.shared_capture = True
        with self.assertRaises(DriveArchiveRejected):
            self.check()

    def test_unexpected_remote_file_rejected(self):
        self.transport.files["roguefile0000001"] = (
            {"name": "rogue", "mimeType": "application/octet-stream",
             "parents": ["folder00000001"]}, b"rogue")
        with self.assertRaisesRegex(DriveArchiveRejected, "unexpected_remote_files"):
            self.check()

    def test_missing_remote_file_rejected(self):
        self.transport.files.pop(next(iter(self.transport.files)))
        with self.assertRaises(DriveArchiveRejected):
            self.check()

    def test_manifest_invalid_forged_size_rejected(self):
        sample = {"schema": "nexium-stage73-private-capture/v1",
                  "source_commit": COMMIT, "native_macho_sha256": MACHO,
                  "guest_nro_sha256": NRO, "privacy": "private",
                  "remote_verified": False, "files": [
                      {"path": "smoke_result.json", "bytes": True, "sha256": "e" * 64},
                      {"path": "data-root/logs/nexium-synthetic.log",
                       "bytes": 10, "sha256": "d" * 64}],
                  "file_count": 2, "total_bytes": 11}
        with self.assertRaises(DriveArchiveRejected):
            validate_remote_manifest(sample, COMMIT)

    def test_unauthorized_cli_blocks_without_creds(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true",
                                      "NEXIUM_PRIVATE_ARCHIVE_ARMED": "true"}):
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                result = main([
                    "--parent-id", PARENT, "--folder-id", "folder00000001",
                    "--run-id", "123", "--source-commit", COMMIT,
                    "--expected-manifest-sha256", self.saved_sha])
            self.assertEqual(result, 1)
            self.assertEqual(error.getvalue(),
                             "STAGE73_PRIVATE_REMOTE_PERSISTENCE_UNVERIFIED\n")


if __name__ == "__main__":
    unittest.main()
