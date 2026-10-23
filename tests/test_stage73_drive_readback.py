"""Synthetic Drive transport tests. No Google credentials or network access."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from seal_private_capture import build_manifest, write_manifest
from archive_private_capture_drive import (
    DriveArchiveRejected, upload_archive, upload_one, read_sealed_file,
    read_private_manifest_bytes, write_private_handoff,
    persist_private_handoff, write_private_receipt_anchor, main, HOST,
)

PARENT = "privateParent123456"
RECEIPTS = "privateReceipts123456"
COMMIT = "a" * 40
NRO = "b" * 64
MACHO = "c" * 64


class FakeTransport:
    def __init__(self):
        self.files = {}
        self.sequence = 0
        self.bad_media = False
        self.bad_parent = False
        self.shared_parent = False
        self.shared_capture = False
        self.calls = []

    def call(self, method, path, body=b"", headers=None, limit=16384):
        self.calls.append((method, path))
        url = urlsplit(path)
        query = parse_qs(url.query)
        if method == "GET" and url.path in (
                "/drive/v3/files/" + PARENT,
                "/drive/v3/files/" + RECEIPTS):
            requested_id = url.path.rsplit("/", 1)[-1]
            item = {"id": requested_id, "mimeType": "application/vnd.google-apps.folder",
                    "trashed": False, "shared": self.shared_parent,
                    "capabilities": {"canAddChildren": True}}
            return 200, {}, json.dumps(item).encode()
        if method == "POST" and url.path == "/drive/v3/files":
            item = json.loads(body)
            self.sequence += 1
            folder_id = "folder" + str(self.sequence).zfill(8)
            return 200, {}, json.dumps({"id": folder_id, **item,
                                        "trashed": False, "shared": self.shared_capture}).encode()
        if method == "POST" and url.path == "/upload/drive/v3/files":
            self.pending = json.loads(body)
            self.sequence += 1
            return 200, {"Location": "https://" + HOST +
                    "/upload/drive/v3/files?uploadType=resumable&upload_id=" +
                    str(self.sequence)}, b""
        if method == "PUT" and url.path == "/upload/drive/v3/files":
            file_id = "remote" + str(self.sequence).zfill(8)
            self.files[file_id] = (self.pending, body)
            return 200, {}, json.dumps({"id": file_id}).encode()
        if method == "GET" and url.path.startswith("/drive/v3/files/"):
            file_id = url.path.rsplit("/", 1)[-1]
            info, payload = self.files[file_id]
            if query.get("alt") == ["media"]:
                if self.bad_media:
                    payload = b"tampered" + payload
                return 200, {}, payload
            data = {"id": file_id, "name": info["name"],
                    "parents": ["otherPrivateParent000"] if self.bad_parent else info["parents"],
                    "mimeType": info["mimeType"], "trashed": False,
                    "shared": self.shared_capture,
                    "size": str(len(payload))}
            return 200, {}, json.dumps(data).encode()
        raise AssertionError("Unexpected fake HTTP call")


class Stage73DriveReadbackTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.report = self.root / "report"
        self.report.mkdir()
        logs = self.report / "data-root/logs"
        logs.mkdir(parents=True)
        self.log = logs / "nexium-synthetic.log"
        self.log.write_bytes(b"synthetic transcript")
        (self.report / "smoke_result.json").write_text("{}")
        self.manifest = self.root / "manifest.json"
        write_manifest(self.manifest,
                       build_manifest(self.report, COMMIT, MACHO, NRO), self.report)

    def test_all_files_and_manifest_read_back(self):
        t = FakeTransport()
        result = upload_archive(self.report, self.manifest, PARENT, "123", t)
        self.assertTrue(result["readback_verified"])
        self.assertFalse(result["retention_verified"])
        self.assertEqual(result["uploaded_files"], 3)
        self.assertEqual(len(t.files), 3)

    def test_modified_remote_media_fails(self):
        t = FakeTransport()
        t.bad_media = True
        with self.assertRaisesRegex(DriveArchiveRejected, "readback_mismatch"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)

    def test_wrong_remote_parent_fails(self):
        t = FakeTransport()
        t.bad_parent = True
        with self.assertRaisesRegex(DriveArchiveRejected, "wrong_remote_parent"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)

    def test_shared_destination_rejected_before_remote_writes(self):
        t = FakeTransport()
        t.shared_parent = True
        with self.assertRaisesRegex(DriveArchiveRejected, "not_writable"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)
        self.assertEqual(len(t.calls), 1)

    def test_new_folder_with_shared_permission_rejected(self):
        t = FakeTransport()
        t.shared_capture = True
        with self.assertRaisesRegex(DriveArchiveRejected, "folder_creation_unverified"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)

    def test_local_tamper_before_upload_fails_without_network(self):
        self.log.write_bytes(b"torn")
        t = FakeTransport()
        with self.assertRaises(DriveArchiveRejected):
            upload_archive(self.report, self.manifest, PARENT, "123", t)
        self.assertEqual(t.calls, [])

    def test_refuse_bad_run_id(self):
        with self.assertRaises(DriveArchiveRejected):
            upload_archive(self.report, self.manifest, PARENT, "../evil", FakeTransport())

    def test_never_activate_on_pr_without_explicit_arm(self):
        import os
        old = os.environ.pop("NEXIUM_PRIVATE_ARCHIVE_ARMED", None)
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = main(["--report", str(self.report),
                               "--manifest", str(self.manifest),
                               "--parent-id", PARENT, "--run-id", "123"])
            self.assertEqual(status, 1)
            self.assertEqual(stderr.getvalue(), "STAGE73_PRIVATE_DRIVE_ARCHIVE_BLOCKED\n")
        finally:
            if old is not None:
                os.environ["NEXIUM_PRIVATE_ARCHIVE_ARMED"] = old

    def test_mismatched_local_hash_does_not_start_upload(self):
        t = FakeTransport()
        with self.assertRaises(DriveArchiveRejected):
            upload_one(t, "folder00000001", "synthetic.log", b"fake", "a" * 64)
        self.assertEqual(t.calls, [])

    def test_descriptor_read_rejects_swapped_log_symlink(self):
        import os
        data = self.log.read_bytes()
        other = self.root / "outside-private-synthetic.txt"
        other.write_bytes(data)
        self.log.unlink()
        self.log.symlink_to(other)
        with self.assertRaises(DriveArchiveRejected):
            read_sealed_file(self.report, "data-root/logs/nexium-synthetic.log",
                             len(data), hashlib.sha256(data).hexdigest())

    def test_descriptor_read_rejects_swapped_parent_symlink(self):
        old = self.report / "data-root/logs"
        backup = self.root / "original-synthetic-logs"
        data = self.log.read_bytes()
        old.rename(backup)
        old.symlink_to(backup, target_is_directory=True)
        with self.assertRaises(DriveArchiveRejected):
            read_sealed_file(self.report, "data-root/logs/nexium-synthetic.log",
                             len(data), hashlib.sha256(data).hexdigest())

    def test_descriptor_read_rejects_hardlink(self):
        import os
        outside = self.root / "second-hardlink"
        os.link(self.log, outside)
        data = self.log.read_bytes()
        with self.assertRaises(DriveArchiveRejected):
            read_sealed_file(self.report, "data-root/logs/nexium-synthetic.log",
                             len(data), hashlib.sha256(data).hexdigest())

    def test_descriptor_read_checks_exact_size_and_digest(self):
        data = self.log.read_bytes()
        path = "data-root/logs/nexium-synthetic.log"
        self.assertEqual(read_sealed_file(self.report, path, len(data),
                                         hashlib.sha256(data).hexdigest()), data)
        with self.assertRaises(DriveArchiveRejected):
            read_sealed_file(self.report, path, len(data), "f" * 64)
        with self.assertRaises(DriveArchiveRejected):
            read_sealed_file(self.report, path, len(data) + 1,
                             hashlib.sha256(data).hexdigest())

    def test_traversal_never_reads_local_file(self):
        with self.assertRaises(DriveArchiveRejected):
            read_sealed_file(self.report, "../outside", 1, "f" * 64)

    def test_github_actions_env_blocks_even_when_armed(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {
            "GITHUB_ACTIONS": "true",
            "NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
            "NEXIUM_DRIVE_ACCESS_TOKEN": "synthetic-token",
        }):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = main(["--report", str(self.report),
                               "--manifest", str(self.manifest),
                               "--parent-id", PARENT, "--run-id", "123"])
            self.assertEqual(status, 1)
            self.assertEqual(stderr.getvalue(), "STAGE73_PRIVATE_DRIVE_ARCHIVE_BLOCKED\n")

    def test_private_handoff_outside_disposable_runner(self):
        result = upload_archive(self.report, self.manifest, PARENT, "123", FakeTransport())
        # Separate from the disposable work tree rooted at self.root.
        with tempfile.TemporaryDirectory() as private_dir:
            path = Path(private_dir) / "handoff.json"
            write_private_handoff(path, self.report, PARENT, "123", COMMIT, result)
            record = json.loads(path.read_text())
            self.assertEqual(record["manifest_sha256"], result["private_manifest_sha256"])
            self.assertEqual(record["run_folder_id"], result["private_run_folder_id"])
            self.assertFalse(record["independent_persistence_verified"])
            self.assertFalse(record["retention_policy_verified"])
            self.assertFalse(record["guest_gpu_frames_verified"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_private_handoff_cannot_lie_inside_disposable_tree(self):
        result = upload_archive(self.report, self.manifest, PARENT, "123", FakeTransport())
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_private_handoff_path"):
            write_private_handoff(self.root / "handoff.json", self.report,
                                  PARENT, "123", COMMIT, result)

    def test_private_handoff_cannot_overwrite(self):
        result = upload_archive(self.report, self.manifest, PARENT, "123", FakeTransport())
        with tempfile.TemporaryDirectory() as private_dir:
            path = Path(private_dir) / "handoff.json"
            path.write_text("existing private archive receipt")
            with self.assertRaises(DriveArchiveRejected):
                write_private_handoff(path, self.report, PARENT, "123", COMMIT, result)
            self.assertEqual(path.read_text(), "existing private archive receipt")

    def test_private_handoff_atomic_collision_does_not_overwrite(self):
        from unittest.mock import patch
        transport = FakeTransport()
        upload = upload_archive(self.report, self.manifest, PARENT, "123", transport)
        with tempfile.TemporaryDirectory() as private_dir:
            target = Path(private_dir) / "handoff.json"
            actual_link = os.link

            def late_writer(src, dest, *args, **kwargs):
                Path(dest).write_bytes(b"previous secure receipt")
                return actual_link(src, dest, *args, **kwargs)

            with patch("archive_private_capture_drive.os.link", side_effect=late_writer):
                with self.assertRaisesRegex(DriveArchiveRejected, "private_handoff_collision"):
                    write_private_handoff(target, self.report, PARENT,
                                          "123", COMMIT, upload)
            self.assertEqual(target.read_bytes(), b"previous secure receipt")
            self.assertEqual(list(Path(private_dir).glob(".stage73-private-*")), [])

    def test_private_handoff_dangling_symlink_not_followed(self):
        transport = FakeTransport()
        upload = upload_archive(self.report, self.manifest, PARENT, "123", transport)
        with tempfile.TemporaryDirectory() as private_dir:
            target = Path(private_dir) / "handoff.json"
            target.symlink_to(Path(private_dir) / "missing")
            with self.assertRaises(DriveArchiveRejected):
                write_private_handoff(target, self.report, PARENT, "123",
                                      COMMIT, upload)
            self.assertTrue(target.is_symlink())

    def test_private_manifest_reader_uses_sealed_bytes(self):
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(read_private_manifest_bytes(self.manifest, manifest),
                         self.manifest.read_bytes())
        with self.assertRaises(DriveArchiveRejected):
            read_private_manifest_bytes(self.manifest, {"source_commit": "forged"})

    def test_private_manifest_reader_refuses_link(self):
        manifest = json.loads(self.manifest.read_text())
        outside = self.root / "outside-manifest"
        outside.write_bytes(self.manifest.read_bytes())
        self.manifest.unlink()
        self.manifest.symlink_to(outside)
        with self.assertRaises(DriveArchiveRejected):
            read_private_manifest_bytes(self.manifest, manifest)

    def make_receipt(self, transport=None):
        transport = transport or FakeTransport()
        uploaded = upload_archive(self.report, self.manifest, PARENT, "123", transport)
        private_temp = tempfile.TemporaryDirectory()
        self.addCleanup(private_temp.cleanup)
        receipt = Path(private_temp.name) / "stage73-handoff.json"
        write_private_handoff(receipt, self.report, PARENT, "123", COMMIT, uploaded)
        return transport, uploaded, receipt

    def test_private_handoff_persisted_to_distinct_drive_folder(self):
        transport, uploaded, receipt = self.make_receipt()
        result = persist_private_handoff(
            transport, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        self.assertTrue(result["private_receipt_readback_verified"])
        self.assertEqual(result["private_receipt_sha256"],
                         hashlib.sha256(receipt.read_bytes()).hexdigest())
        self.assertFalse(result["retention_policy_verified"])
        self.assertEqual(len(transport.files), 4)
        receipt_meta = [
            (meta, content) for meta, content in transport.files.values()
            if meta["parents"] == [RECEIPTS]
        ]
        self.assertEqual(len(receipt_meta), 1)
        self.assertEqual(json.loads(receipt_meta[0][1])["run_folder_id"],
                         uploaded["private_run_folder_id"])

    def test_private_receipt_folder_must_differ_from_capture(self):
        transport, uploaded, receipt = self.make_receipt()
        before = len(transport.calls)
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_receipt_destination"):
            persist_private_handoff(
                transport, receipt, PARENT, PARENT, "123", COMMIT, uploaded)
        self.assertEqual(len(transport.calls), before)

    def test_private_receipt_tamper_blocks_network(self):
        transport, uploaded, receipt = self.make_receipt()
        receipt.write_bytes(b"forged private receipt")
        before = len(transport.calls)
        with self.assertRaises(DriveArchiveRejected):
            persist_private_handoff(
                transport, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        self.assertEqual(len(transport.calls), before)

    def test_private_receipt_symlink_blocks_network(self):
        transport, uploaded, receipt = self.make_receipt()
        other = receipt.parent / "other"
        other.write_bytes(receipt.read_bytes())
        receipt.unlink()
        receipt.symlink_to(other)
        before = len(transport.calls)
        with self.assertRaises(DriveArchiveRejected):
            persist_private_handoff(
                transport, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        self.assertEqual(len(transport.calls), before)

    def test_shared_private_receipt_folder_blocks_upload(self):
        transport, uploaded, receipt = self.make_receipt()
        transport.shared_parent = True
        before = len(transport.files)
        with self.assertRaisesRegex(DriveArchiveRejected, "not_writable"):
            persist_private_handoff(
                transport, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        self.assertEqual(len(transport.files), before)

    def test_private_receipt_readback_mismatch_fails(self):
        transport, uploaded, receipt = self.make_receipt()
        transport.bad_media = True
        with self.assertRaisesRegex(DriveArchiveRejected, "readback_mismatch"):
            persist_private_handoff(
                transport, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)

    def make_anchored_receipt(self):
        transport, uploaded, receipt = self.make_receipt()
        handoff = persist_private_handoff(
            transport, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        dest = tempfile.TemporaryDirectory()
        self.addCleanup(dest.cleanup)
        anchor = Path(dest.name) / "trusted-anchor.json"
        return transport, uploaded, receipt, handoff, anchor

    def test_exclusive_private_anchor_with_receipt_digest(self):
        transport, uploaded, receipt, handoff, anchor = self.make_anchored_receipt()
        write_private_receipt_anchor(
            anchor, self.report, receipt, PARENT, RECEIPTS,
            "123", COMMIT, uploaded, handoff)
        record = json.loads(anchor.read_text())
        self.assertEqual(record["receipt_sha256"], handoff["private_receipt_sha256"])
        self.assertTrue(record["receipt_remote_readback_verified"])
        self.assertFalse(record["anchor_remote_retention_verified"])
        self.assertFalse(record["guest_gpu_frames_verified"])
        self.assertEqual(anchor.stat().st_mode & 0o777, 0o600)

    def test_existing_anchor_never_overwritten(self):
        transport, uploaded, receipt, handoff, anchor = self.make_anchored_receipt()
        anchor.write_text("immutable anchor")
        with self.assertRaisesRegex(DriveArchiveRejected, "anchor_collision"):
            write_private_receipt_anchor(
                anchor, self.report, receipt, PARENT, RECEIPTS,
                "123", COMMIT, uploaded, handoff)
        self.assertEqual(anchor.read_text(), "immutable anchor")

    def test_anchor_cannot_be_inside_disposable_guest_tree(self):
        transport, uploaded, receipt, handoff, _ = self.make_anchored_receipt()
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_anchor_path"):
            write_private_receipt_anchor(
                self.root / "anchor.json", self.report, receipt, PARENT,
                RECEIPTS, "123", COMMIT, uploaded, handoff)

    def test_anchor_cannot_replace_private_receipt(self):
        transport, uploaded, receipt, handoff, _ = self.make_anchored_receipt()
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_anchor_path"):
            write_private_receipt_anchor(
                receipt, self.report, receipt, PARENT, RECEIPTS,
                "123", COMMIT, uploaded, handoff)

    def test_anchor_rejects_unverified_readback(self):
        transport, uploaded, receipt, handoff, anchor = self.make_anchored_receipt()
        handoff["private_receipt_readback_verified"] = False
        with self.assertRaisesRegex(DriveArchiveRejected, "untrusted_anchor_contents"):
            write_private_receipt_anchor(
                anchor, self.report, receipt, PARENT, RECEIPTS,
                "123", COMMIT, uploaded, handoff)
        self.assertFalse(anchor.exists())

    def test_private_server_resumable_url_only(self):
        t = FakeTransport()
        original = t.call

        def wrong_location(method, path, body=b"", headers=None, limit=16384):
            if method == "POST" and path.startswith("/upload/"):
                return 200, {"Location": "https://untrusted.example/upload"}, b""
            return original(method, path, body, headers, limit)
        t.call = wrong_location
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)


if __name__ == "__main__":
    unittest.main()
