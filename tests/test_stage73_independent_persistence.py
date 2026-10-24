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
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_private_capture_drive import (
    upload_archive, write_private_handoff, persist_private_handoff,
)
from test_stage73_drive_readback import FakeTransport, PARENT, RECEIPTS, COMMIT, MACHO, NRO
from seal_private_capture import build_manifest, write_manifest
from verify_stage73_private_drive_persistence import (
    DriveArchiveRejected, audit_remote, audit_from_remote_handoff,
    read_independent_anchor, main, validate_remote_manifest,
)


class PersistentFakeTransport(FakeTransport):
    def call(self, method, path, body=b"", headers=None, limit=16384):
        u = urlsplit(path)
        if method == "GET" and u.path == "/drive/v3/files/folder00000001":
            return 200, {}, json.dumps({
                "id": "folder00000001", "name": "stage73-123-" + COMMIT[:12],
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": False, "shared": self.shared_capture, "parents": [PARENT],
                "permissions": [{"type": "user", "role": "owner"}],
            }).encode()
        if method == "GET" and u.path == "/drive/v3/files":
            q = parse_qs(u.query).get("q", [""])[0]
            parent_match = re.search(r"'([A-Za-z0-9_-]+)' in parents", q)
            name_match = re.search(r"name = '([^']+)'", q)
            parent = parent_match.group(1) if parent_match else None
            filename = name_match.group(1) if name_match else None
            records = []
            for file_id, (meta, content) in self.files.items():
                if parent not in meta["parents"]:
                    continue
                if filename and meta["name"] != filename:
                    continue
                records.append({
                    "id": file_id, "name": meta["name"],
                    "mimeType": meta["mimeType"], "parents": meta["parents"],
                    "trashed": False, "shared": self.shared_capture,
                    "permissions": [{"type": "user", "role": "owner"}],
                    "size": str(len(content)),
                })
            if getattr(self, "force_capture_run_collision", False) and parent == PARENT:
                expected = "stage73-123-" + COMMIT[:12]
                if filename == expected:
                    records.append({"id": "existingRunFolder123",
                                    "name": expected})
            if getattr(self, "force_incomplete_preflight_listing", False) and filename:
                return 200, {}, json.dumps({
                    "files": [], "nextPageToken": "morePrivateItems",
                }).encode()
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
        upload_result = upload_archive(
            report, self.manifest_path, PARENT, "123", self.transport
        )
        # Store a private handoff in a separate receipt folder, before deleting
        # all temporary capture/source files.
        with tempfile.TemporaryDirectory() as handoff_dir:
            receipt = Path(handoff_dir) / "handoff.json"
            write_private_handoff(
                receipt, report, PARENT, "123", COMMIT, upload_result
            )
            persist_private_handoff(
                self.transport, receipt, RECEIPTS, PARENT,
                "123", COMMIT, upload_result,
            )
            # This digest is obtained BEFORE source deletion and retained
            # outside the fake remote Drive. It is the trust anchor.
            self.external_receipt_sha256 = hashlib.sha256(receipt.read_bytes()).hexdigest()
        # Simulate expiry/deletion of the original temporary runner.
        self.tmp.cleanup()

    def check(self, **updates):
        values = {"transport": self.transport, "parent_id": PARENT,
                  "folder_id": "folder00000001", "run_id": "123",
                  "commit": COMMIT, "manifest_sha256": self.saved_sha}
        values.update(updates)
        return audit_remote(**values)

    def check_from_receipt(self, **updates):
        values = {"transport": self.transport, "receipt_parent_id": RECEIPTS,
                  "capture_parent_id": PARENT, "run_id": "123",
                  "commit": COMMIT,
                  "expected_receipt_sha256": self.external_receipt_sha256}
        values.update(updates)
        return audit_from_remote_handoff(**values)

    def test_receipt_anchor_is_mandatory(self):
        with self.assertRaisesRegex(DriveArchiveRejected, "invalid_handoff_anchor"):
            self.check_from_receipt(expected_receipt_sha256="")
        with self.assertRaisesRegex(DriveArchiveRejected, "invalid_handoff_anchor"):
            self.check_from_receipt(expected_receipt_sha256="f" * 63)

    def test_wrong_independent_receipt_digest_rejected(self):
        with self.assertRaisesRegex(DriveArchiveRejected, "receipt_anchor_digest_mismatch"):
            self.check_from_receipt(expected_receipt_sha256="f" * 64)

    def test_self_consistent_forged_receipt_rejected_by_external_anchor(self):
        """Malicious remote can change both contents and manifest references."""
        for file_id, (metadata, raw) in list(self.transport.files.items()):
            if metadata["parents"] == [RECEIPTS]:
                receipt = json.loads(raw)
                receipt["manifest_sha256"] = "a" * 64
                forged = json.dumps(receipt, sort_keys=True).encode()
                self.transport.files[file_id] = (metadata, forged)
        with self.assertRaisesRegex(DriveArchiveRejected, "receipt_anchor_digest_mismatch"):
            self.check_from_receipt()

    def make_external_anchor(self):
        from archive_private_capture_drive import (
            write_private_receipt_anchor,
        )
        # Trust anchor must be outside the original disposable source.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anchor.json"
            data = {
                "schema": "nexium-stage73-independent-receipt-anchor/v1",
                "privacy": "private", "source_commit": COMMIT,
                "run_id": "123", "capture_parent_id": PARENT,
                "receipt_parent_id": RECEIPTS,
                "receipt_sha256": self.external_receipt_sha256,
                "receipt_remote_readback_verified": True,
                "anchor_remote_retention_verified": False,
                "guest_gpu_frames_verified": False,
            }
            path.write_text(json.dumps(data))
            path.chmod(0o600)
            return path.read_bytes()

    def test_external_anchor_file_provides_receipt_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anchor.json"
            path.write_bytes(self.make_external_anchor())
            path.chmod(0o600)
            digest = read_independent_anchor(path, COMMIT, "123", PARENT, RECEIPTS)
            self.assertEqual(digest, self.external_receipt_sha256)
            self.assertTrue(self.check_from_receipt(
                expected_receipt_sha256=digest)["remote_independent_readback_verified"])

    def test_external_anchor_world_readable_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anchor.json"
            path.write_bytes(self.make_external_anchor())
            path.chmod(0o644)
            with self.assertRaisesRegex(DriveArchiveRejected, "anchor_unsafe"):
                read_independent_anchor(path, COMMIT, "123", PARENT, RECEIPTS)

    def test_external_anchor_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "original"
            original.write_bytes(self.make_external_anchor())
            original.chmod(0o600)
            alias = Path(tmp) / "alias"
            alias.symlink_to(original)
            with self.assertRaises(DriveArchiveRejected):
                read_independent_anchor(alias, COMMIT, "123", PARENT, RECEIPTS)

    def test_external_anchor_wrong_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anchor.json"
            path.write_bytes(self.make_external_anchor())
            path.chmod(0o600)
            with self.assertRaisesRegex(DriveArchiveRejected, "untrusted_anchor"):
                read_independent_anchor(path, "d" * 40, "123", PARENT, RECEIPTS)
            with self.assertRaisesRegex(DriveArchiveRejected, "untrusted_anchor"):
                read_independent_anchor(path, COMMIT, "999", PARENT, RECEIPTS)

    def test_external_anchor_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "absent"
            with self.assertRaisesRegex(DriveArchiveRejected, "anchor_unavailable"):
                read_independent_anchor(path, COMMIT, "123", PARENT, RECEIPTS)

    def test_shared_ancestor_blocks_post_runner_recovery(self):
        self.transport.shared_ancestor = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            self.check_from_receipt()

    def test_extra_parent_grant_blocks_post_runner_recovery(self):
        self.transport.extra_permission = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            self.check_from_receipt()

    def test_missing_parent_acl_blocks_post_runner_recovery(self):
        self.transport.missing_permissions = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            self.check_from_receipt()

    def test_receipt_independent_readback_after_runner_deleted(self):
        result = self.check_from_receipt()
        self.assertTrue(result["remote_receipt_readback_verified"])
        self.assertTrue(result["remote_independent_readback_verified"])
        self.assertFalse(result["retention_policy_verified"])

    def test_receipt_tamper_fails_independent_check(self):
        for file_id, (meta, content) in list(self.transport.files.items()):
            if meta["parents"] == [RECEIPTS]:
                self.transport.files[file_id] = (meta, b"altered-handoff")
        with self.assertRaises(DriveArchiveRejected):
            self.check_from_receipt()

    def test_receipt_missing_fails_independent_check(self):
        for file_id, (meta, _) in list(self.transport.files.items()):
            if meta["parents"] == [RECEIPTS]:
                self.transport.files.pop(file_id)
        with self.assertRaisesRegex(DriveArchiveRejected, "receipt_missing_or_ambiguous"):
            self.check_from_receipt()

    def test_duplicate_receipt_fails_independent_check(self):
        for _, (meta, content) in list(self.transport.files.items()):
            if meta["parents"] == [RECEIPTS]:
                self.transport.files["duplicateReceiptFile123"] = (meta, content)
                break
        with self.assertRaisesRegex(DriveArchiveRejected, "receipt_missing_or_ambiguous"):
            self.check_from_receipt()

    def test_shared_receipt_rejected(self):
        self.transport.shared_capture = True
        with self.assertRaises(DriveArchiveRejected):
            self.check_from_receipt()

    def test_remote_receipt_unmatched_commit_rejected(self):
        with self.assertRaises(DriveArchiveRejected):
            self.check_from_receipt(commit="d" * 40)

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
