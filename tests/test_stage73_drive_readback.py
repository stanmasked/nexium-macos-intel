"""Synthetic Drive transport tests. No Google credentials or network access."""
import contextlib
import hashlib
import io
import json
import os
import re
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
    persist_private_handoff, write_private_receipt_anchor,
    check_private_parent_chain, main, HOST,
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
        self.shared_ancestor = False
        self.extra_permission = False
        self.missing_permissions = False
        self.ancestor_cycle = False
        self.parent_metadata_missing = False
        self.forged_root_identity = False
        self.shared_root_alias = False
        self.actual_root_without_parents = True
        self.created_folders = {}
        self.created_folder_readback_shared = False
        self.created_folder_readback_parent_wrong = False
        self.created_folder_readback_not_writable = False
        self.created_folder_readback_name_wrong = False
        self.created_folder_private_reads = 0
        self.created_folder_share_after_reads = None
        self.created_folder_parent_moved_after_reads = None
        self.created_folder_name_change_after_reads = None
        self.remote_file_metadata_reads = {}
        self.remote_file_share_after_reads = None
        self.remote_file_reparent_after_reads = None
        self.remote_file_rename_after_reads = None
        self.remote_file_trash_after_reads = None
        self.created_folder_share_on_upload_init = False
        self.created_folder_reparent_on_upload_init = False
        self.created_folder_rename_on_upload_init = False
        self.created_folder_readonly_on_upload_init = False
        self.incomplete_preflight_listing = False
        self.force_capture_identity_collision = False
        self.force_receipt_identity_collision = False
        self.concurrent_capture_duplicate_after_post = False
        self.concurrent_receipt_duplicate_after_upload = False
        self.invalid_name_listing_entry = False
        self.folder_post_response_id_only = False
        self.folder_post_response_bad_id = False
        self.created_folder_readback_permissions_missing = False
        self.calls = []

    def call(self, method, path, body=b"", headers=None, limit=16384):
        self.calls.append((method, path))
        url = urlsplit(path)
        query = parse_qs(url.query)
        if method == "GET" and url.path == "/drive/v3/files/root":
            return 200, {}, json.dumps({
                "id": "differentRoot123456" if self.forged_root_identity
                      else "syntheticAncestor123",
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": False, "shared": self.shared_root_alias,
                "permissions": [{"type": "user", "role": "owner"}],
            }).encode()
        if method == "GET" and url.path in (
                "/drive/v3/files/" + PARENT,
                "/drive/v3/files/" + RECEIPTS,
                "/drive/v3/files/syntheticAncestor123"):
            requested_id = url.path.rsplit("/", 1)[-1]
            ancestor = requested_id == "syntheticAncestor123"
            item = {"id": requested_id, "mimeType": "application/vnd.google-apps.folder",
                    "trashed": False,
                    "shared": self.shared_ancestor if ancestor else self.shared_parent,
                    "parents": (["syntheticAncestor123"] if not ancestor else
                                ([PARENT] if self.ancestor_cycle else [])),
                    "capabilities": {"canAddChildren": True},
                    "permissions": [{"type": "user", "role": "owner"}]}
            if self.extra_permission:
                item["permissions"].append({"type": "anyone", "role": "reader"})
            if self.missing_permissions:
                del item["permissions"]
            if (self.parent_metadata_missing and requested_id == PARENT
                    or self.actual_root_without_parents and ancestor
                    and not self.ancestor_cycle):
                del item["parents"]
            return 200, {}, json.dumps(item).encode()
        if method == "GET" and url.path == "/drive/v3/files":
            q = query.get("q", [""])[0]
            p = re.search(r"'([^']+)' in parents", q)
            n = re.search(r"name = '([^']+)'", q)
            if p is None or n is None:
                raise AssertionError("Unexpected Drive listing query")
            parent_id, filename = p.group(1), n.group(1)
            matches = [
                {"id": folder_id, "name": folder["name"]}
                for folder_id, folder in self.created_folders.items()
                if folder["parents"] == [parent_id] and folder["name"] == filename
            ]
            matches.extend(
                {"id": file_id, "name": metadata["name"]}
                for file_id, (metadata, _) in self.files.items()
                if metadata["parents"] == [parent_id]
                and metadata["name"] == filename
            )
            if ((self.force_capture_identity_collision and filename.endswith(COMMIT[:12]))
                    or (self.force_receipt_identity_collision and filename.endswith("-handoff.json"))
                    or (self.concurrent_capture_duplicate_after_post
                        and filename.endswith(COMMIT[:12])
                        and bool(self.created_folders))
                    or (self.concurrent_receipt_duplicate_after_upload
                        and filename.endswith("-handoff.json")
                        and any(info["parents"] == [RECEIPTS]
                                for info, _ in self.files.values()))):
                matches.append({"id": "priorArchive9999", "name": filename})
            if self.invalid_name_listing_entry:
                matches.append({"name": filename})
            result = {"files": matches}
            if self.incomplete_preflight_listing:
                result["nextPageToken"] = "moreUnknownPrivateItems"
            return 200, {}, json.dumps(result).encode()
        if method == "POST" and url.path == "/drive/v3/files":
            item = json.loads(body)
            self.sequence += 1
            folder_id = "folder" + str(self.sequence).zfill(8)
            self.created_folders[folder_id] = dict(item)
            if self.folder_post_response_bad_id:
                return 200, {}, json.dumps({"id": "!"}).encode()
            if self.folder_post_response_id_only:
                return 200, {}, json.dumps({"id": folder_id}).encode()
            return 200, {}, json.dumps({"id": folder_id, **item,
                                        "trashed": False, "shared": self.shared_capture,
                                        "permissions": [{"type": "user", "role": "owner"}]}).encode()
        if method == "GET" and url.path.startswith("/drive/v3/files/"):
            folder_id = url.path.rsplit("/", 1)[-1]
            if folder_id in self.created_folders:
                self.created_folder_private_reads += 1
                original = self.created_folders[folder_id]
                shifted_shared = (
                    self.created_folder_share_after_reads is not None
                    and self.created_folder_private_reads >
                    self.created_folder_share_after_reads
                )
                shifted_parent = (
                    self.created_folder_parent_moved_after_reads is not None
                    and self.created_folder_private_reads >
                    self.created_folder_parent_moved_after_reads
                )
                shifted_name = (
                    self.created_folder_name_change_after_reads is not None
                    and self.created_folder_private_reads >
                    self.created_folder_name_change_after_reads
                )
                item = {
                    "id": folder_id,
                    "name": ("wrong-staged-folder"
                             if self.created_folder_readback_name_wrong or shifted_name
                             else original["name"]),
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": (["unexpectedPrivateParent1"]
                                if (self.created_folder_readback_parent_wrong
                                    or shifted_parent)
                                else original["parents"]),
                    "trashed": False,
                    "shared": (self.shared_capture or
                               self.created_folder_readback_shared or shifted_shared),
                    "permissions": [{"type": "user", "role": "owner"}],
                    "capabilities": {
                        "canAddChildren": not self.created_folder_readback_not_writable,
                    },
                }
                if self.created_folder_readback_permissions_missing:
                    del item["permissions"]
                return 200, {}, json.dumps(item).encode()
        if method == "POST" and url.path == "/upload/drive/v3/files":
            # Simulate a concurrent Drive permission/placement change after
            # upload-session creation but before the content-bearing PUT.
            if self.created_folder_share_on_upload_init:
                self.created_folder_readback_shared = True
            if self.created_folder_reparent_on_upload_init:
                self.created_folder_readback_parent_wrong = True
            if self.created_folder_rename_on_upload_init:
                self.created_folder_readback_name_wrong = True
            if self.created_folder_readonly_on_upload_init:
                self.created_folder_readback_not_writable = True
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
            count = self.remote_file_metadata_reads.get(file_id, 0) + 1
            self.remote_file_metadata_reads[file_id] = count
            def after_first_metadata(threshold):
                return threshold is not None and count > threshold
            data = {
                "id": file_id,
                "name": ("renamed-after-media"
                         if after_first_metadata(self.remote_file_rename_after_reads)
                         else info["name"]),
                "parents": (["otherPrivateParent000"]
                            if (self.bad_parent or after_first_metadata(
                                self.remote_file_reparent_after_reads))
                            else info["parents"]),
                "mimeType": info["mimeType"],
                "trashed": after_first_metadata(self.remote_file_trash_after_reads),
                "shared": (self.shared_capture or after_first_metadata(
                    self.remote_file_share_after_reads)),
                "permissions": [{"type": "user", "role": "owner"}],
                "size": str(len(payload)),
            }
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

    def test_ancestry_requires_parent_metadata_not_guessing_root(self):
        tr = FakeTransport()
        tr.parent_metadata_missing = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_root_identity_unverified"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "POST" for m, _ in tr.calls))

    def test_terminal_parent_requires_real_drive_root_identity(self):
        tr = FakeTransport()
        tr.forged_root_identity = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_root_identity_unverified"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "POST" for m, _ in tr.calls))

    def test_shared_my_drive_root_blocks_upload(self):
        tr = FakeTransport()
        tr.shared_root_alias = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "POST" for m, _ in tr.calls))

    def test_real_root_without_parents_is_accepted_only_on_root_alias(self):
        tr = FakeTransport()
        # The root lacks parents in real My Drive metadata. Its identity
        # is independently confirmed using the reserved Drive root alias.
        check_private_parent_chain(tr, "syntheticAncestor123", writable=False)
        self.assertTrue(any(
            method == "GET" and path.startswith("/drive/v3/files/root?")
            for method, path in tr.calls
        ))

    def test_ancestry_checks_real_root_alias_before_upload(self):
        tr = FakeTransport()
        upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(any(
            method == "GET" and path.startswith("/drive/v3/files/root?")
            for method, path in tr.calls
        ))

    def test_shared_ancestor_blocks_upload_before_any_write(self):
        tr = FakeTransport()
        tr.shared_ancestor = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(method == "POST" for method, _ in tr.calls))

    def test_extra_grant_blocks_upload_before_any_write(self):
        tr = FakeTransport()
        tr.extra_permission = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(method == "POST" for method, _ in tr.calls))

    def test_unknown_permissions_block_upload_before_any_write(self):
        tr = FakeTransport()
        tr.missing_permissions = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(method == "POST" for method, _ in tr.calls))

    def test_parent_cycle_blocks_upload_before_any_write(self):
        tr = FakeTransport()
        tr.ancestor_cycle = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_parent_cycle"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(method == "POST" for method, _ in tr.calls))

    def test_shared_destination_rejected_before_remote_writes(self):
        t = FakeTransport()
        t.shared_parent = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)
        self.assertEqual(len(t.calls), 1)

    def test_new_folder_with_shared_permission_rejected(self):
        t = FakeTransport()
        t.shared_capture = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", t)


    def test_partial_folder_create_id_only_succeeds_after_private_get(self):
        tr = FakeTransport()
        tr.folder_post_response_id_only = True
        result = upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(result["readback_verified"])
        self.assertFalse(result["retention_verified"])
        created_get = next(
            index for index, (method, path) in enumerate(tr.calls)
            if method == "GET" and path.startswith("/drive/v3/files/folder00000001?")
        )
        payload_post = next(
            index for index, (method, path) in enumerate(tr.calls)
            if method == "POST" and path.startswith("/upload/drive/v3/files?")
        )
        self.assertLess(created_get, payload_post)

    def test_partial_folder_create_id_only_shared_readback_stops_payload(self):
        tr = FakeTransport()
        tr.folder_post_response_id_only = True
        tr.created_folder_readback_shared = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertEqual(tr.files, {})

    def test_partial_create_missing_get_permissions_refuses_payload(self):
        tr = FakeTransport()
        tr.folder_post_response_id_only = True
        tr.created_folder_readback_permissions_missing = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertFalse(tr.files)

    def test_invalid_folder_create_id_rejects_without_payload(self):
        tr = FakeTransport()
        tr.folder_post_response_bad_id = True
        with self.assertRaisesRegex(DriveArchiveRejected, "folder_creation_unverified"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))

    def test_created_folder_rechecked_after_post_before_content_upload(self):
        tr = FakeTransport()
        result = upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(result["readback_verified"])
        self.assertTrue(any(
            method == "GET" and path.startswith("/drive/v3/files/folder00000001?")
            for method, path in tr.calls
        ))
        self.assertTrue(any(
            method == "GET" and path.startswith("/drive/v3/files/root?")
            for method, path in tr.calls
        ))

    def test_created_folder_becomes_shared_before_first_payload_refused(self):
        tr = FakeTransport()
        tr.created_folder_readback_shared = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertFalse(tr.files)

    def test_created_folder_parent_swap_refused_before_payload(self):
        tr = FakeTransport()
        tr.created_folder_readback_parent_wrong = True
        with self.assertRaises(DriveArchiveRejected):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertFalse(tr.files)

    def test_created_folder_revoked_writability_refused_before_payload(self):
        tr = FakeTransport()
        tr.created_folder_readback_not_writable = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_folder_not_writable"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))

    def test_created_folder_wrong_name_on_readback_refused_before_payload(self):
        tr = FakeTransport()
        tr.created_folder_readback_name_wrong = True
        with self.assertRaisesRegex(DriveArchiveRejected, "created_folder_readback_invalid"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))


    def test_new_folder_reshared_after_creation_readback_blocks_first_upload(self):
        tr = FakeTransport()
        # Creation re-read and ancestry walk initially see owner-only ACL.
        # The next check, from upload_one, must reject the changed ACL.
        tr.created_folder_share_after_reads = 2
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertFalse(tr.files)

    def test_new_folder_moved_after_creation_readback_blocks_first_upload(self):
        tr = FakeTransport()
        tr.created_folder_parent_moved_after_reads = 2
        with self.assertRaises(DriveArchiveRejected):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertFalse(tr.files)

    def test_folder_reshared_during_first_remote_media_readback_rejected(self):
        tr = FakeTransport()
        # First check after folder creation occurs on a new upload, with
        # another check after SHA-256 media readback. The latter must notice
        # ACL drift even when all file bytes/hash checks passed.
        tr.created_folder_share_after_reads = 6
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)

    def test_per_file_acl_checks_cover_later_capture_files(self):
        tr = FakeTransport()
        # First file can verify; the second preflight must discover drift.
        tr.created_folder_share_after_reads = 8
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)
        self.assertTrue(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))

    def test_folder_reparented_after_first_verified_file_detected(self):
        tr = FakeTransport()
        tr.created_folder_parent_moved_after_reads = 8
        with self.assertRaisesRegex(DriveArchiveRejected, "run_folder_placement_changed"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)

    def test_folder_name_changed_before_second_upload_detected(self):
        tr = FakeTransport()
        tr.created_folder_name_change_after_reads = 8
        with self.assertRaisesRegex(DriveArchiveRejected, "run_folder_placement_changed"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)

    def test_remote_file_rechecked_after_media_sha256_success(self):
        tr = FakeTransport()
        result = upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(len(tr.files), 3)
        self.assertTrue(all(
            tr.remote_file_metadata_reads[file_id] == 2
            for file_id in tr.files
        ))

    def test_remote_file_reshared_after_media_readback_rejected(self):
        tr = FakeTransport()
        tr.remote_file_share_after_reads = 1
        with self.assertRaisesRegex(
                DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        # Bytes were uploaded; fail closed instead of declaring private
        # success. No second or manifest payload should have started.
        self.assertEqual(len(tr.files), 1)

    def test_remote_file_reparented_after_media_readback_rejected(self):
        tr = FakeTransport()
        tr.remote_file_reparent_after_reads = 1
        with self.assertRaisesRegex(DriveArchiveRejected, "wrong_remote_parent"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)

    def test_remote_file_renamed_after_media_readback_rejected(self):
        tr = FakeTransport()
        tr.remote_file_rename_after_reads = 1
        with self.assertRaisesRegex(DriveArchiveRejected, "wrong_remote_identity"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)

    def test_remote_file_trashed_after_media_readback_rejected(self):
        tr = FakeTransport()
        tr.remote_file_trash_after_reads = 1
        with self.assertRaisesRegex(DriveArchiveRejected, "wrong_remote_parent"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.files), 1)


    def test_folder_shared_after_resumable_init_blocks_payload_put(self):
        tr = FakeTransport()
        tr.created_folder_share_on_upload_init = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(any(
            m == "POST" and "/upload/drive/v3/files?" in p
            for m, p in tr.calls
        ))
        self.assertFalse(any(m == "PUT" for m, _ in tr.calls))
        self.assertFalse(tr.files)

    def test_folder_reparented_after_resumable_init_blocks_payload_put(self):
        tr = FakeTransport()
        tr.created_folder_reparent_on_upload_init = True
        with self.assertRaisesRegex(DriveArchiveRejected, "run_folder_placement_changed"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "PUT" for m, _ in tr.calls))
        self.assertFalse(tr.files)

    def test_folder_renamed_after_resumable_init_blocks_payload_put(self):
        tr = FakeTransport()
        tr.created_folder_rename_on_upload_init = True
        with self.assertRaisesRegex(DriveArchiveRejected, "run_folder_placement_changed"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "PUT" for m, _ in tr.calls))

    def test_folder_readonly_after_resumable_init_blocks_payload_put(self):
        tr = FakeTransport()
        tr.created_folder_readonly_on_upload_init = True
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_folder_not_writable"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "PUT" for m, _ in tr.calls))


    def test_first_private_archive_checks_unique_name_before_remote_post(self):
        tr = FakeTransport()
        result = upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(result["readback_verified"])
        preflight = [path for method, path in tr.calls
                     if method == "GET" and path.startswith("/drive/v3/files?")]
        self.assertTrue(any("name" in path for path in preflight))
        self.assertLess(
            tr.calls.index(next((method, path) for method, path in tr.calls
                                if method == "GET" and path.startswith("/drive/v3/files?"))),
            tr.calls.index(next((method, path) for method, path in tr.calls
                                if method == "POST"))
        )

    def test_duplicate_private_run_id_refused_before_any_new_post(self):
        tr = FakeTransport()
        upload_archive(self.report, self.manifest, PARENT, "123", tr)
        previous_post_count = sum(m == "POST" for m, _ in tr.calls)
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(previous_post_count,
                         sum(m == "POST" for m, _ in tr.calls))
        self.assertEqual(len(tr.files), 3)

    def test_existing_capture_collision_blocks_all_writes(self):
        tr = FakeTransport()
        tr.force_capture_identity_collision = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "POST" for m, _ in tr.calls))

    def test_incomplete_private_listing_blocks_all_writes(self):
        tr = FakeTransport()
        tr.incomplete_preflight_listing = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(m == "POST" for m, _ in tr.calls))

    def test_duplicate_handoff_receipt_refused_without_new_upload(self):
        tr, uploaded, receipt = self.make_receipt()
        tr.force_receipt_identity_collision = True
        prior_writes = sum(m in ("POST", "PUT") for m, _ in tr.calls)
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            persist_private_handoff(
                tr, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        self.assertEqual(prior_writes,
                         sum(m in ("POST", "PUT") for m, _ in tr.calls))

    def test_real_uploader_preflights_receipt_conflict_before_capture(self):
        from unittest.mock import patch
        tr = FakeTransport()
        tr.force_receipt_identity_collision = True
        with tempfile.TemporaryDirectory() as private_dir:
            with patch.dict("os.environ", {
                "GITHUB_ACTIONS": "false",
                "NEXIUM_PRIVATE_ARCHIVE_ARMED": "true",
                "NEXIUM_DRIVE_ACCESS_TOKEN": "fake-testing-only",
            }), patch("archive_private_capture_drive.GoogleTransport", return_value=tr):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main([
                        "--report", str(self.report), "--manifest", str(self.manifest),
                        "--parent-id", PARENT, "--run-id", "123",
                        "--receipt-parent-id", RECEIPTS,
                        "--receipt-path", str(Path(private_dir) / "handoff.json"),
                        "--anchor-path", str(Path(private_dir) / "anchor.json"),
                    ])
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "STAGE73_PRIVATE_DRIVE_ARCHIVE_BLOCKED\n")
        self.assertFalse(any(m == "POST" for m, _ in tr.calls))


    def test_created_capture_folder_must_be_only_matching_remote_name(self):
        tr = FakeTransport()
        tr.concurrent_capture_duplicate_after_post = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertEqual(len(tr.created_folders), 1)
        self.assertFalse(any(
            method == "POST" and path.startswith("/upload/drive/v3/files?")
            for method, path in tr.calls
        ))
        self.assertFalse(tr.files)

    def test_uploaded_receipt_duplicate_name_invalidates_verified_handoff(self):
        tr, uploaded, receipt = self.make_receipt()
        tr.concurrent_receipt_duplicate_after_upload = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            persist_private_handoff(
                tr, receipt, RECEIPTS, PARENT, "123", COMMIT, uploaded)
        self.assertEqual(len(tr.files), 4)
        self.assertEqual(sum(
            metadata["parents"] == [RECEIPTS]
            for metadata, _ in tr.files.values()
        ), 1)

    def test_invalid_remote_listing_item_blocks_capture_before_post(self):
        tr = FakeTransport()
        tr.invalid_name_listing_entry = True
        with self.assertRaisesRegex(DriveArchiveRejected,
                                    "remote_archive_identity_not_unique"):
            upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertFalse(any(method == "POST" for method, _ in tr.calls))

    def test_postcreate_recheck_does_not_claim_remote_retention(self):
        tr = FakeTransport()
        outcome = upload_archive(self.report, self.manifest, PARENT, "123", tr)
        self.assertTrue(outcome["readback_verified"])
        self.assertFalse(outcome["retention_verified"])
        folder_queries = [
            path for method, path in tr.calls
            if method == "GET" and path.startswith("/drive/v3/files?")
        ]
        self.assertGreaterEqual(len(folder_queries), 2)

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
        with self.assertRaisesRegex(DriveArchiveRejected, "remote_acl_not_owner_only"):
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
