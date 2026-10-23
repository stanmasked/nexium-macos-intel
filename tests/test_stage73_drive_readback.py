"""Synthetic Drive transport tests. No Google credentials or network access."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from seal_private_capture import build_manifest, write_manifest
from archive_private_capture_drive import (
    DriveArchiveRejected, upload_archive, upload_one, main, HOST,
)

PARENT = "privateParent123456"
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
        if method == "GET" and url.path == "/drive/v3/files/" + PARENT:
            item = {"id": PARENT, "mimeType": "application/vnd.google-apps.folder",
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
