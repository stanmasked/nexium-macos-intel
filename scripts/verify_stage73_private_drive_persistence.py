#!/usr/bin/env python3
"""Independent, read-only Stage73 Drive persistence audit.

This does not run in PR Actions and cannot certify retention policies, graphics
or gameplay. It must receive a manifest SHA-256 saved outside the upload folder.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlencode

from archive_private_capture_drive import (
    GoogleTransport, DriveArchiveRejected, DRIVE_ID, COMMIT, RUN_ID,
    json_response, metadata_path,
)
from seal_private_capture import (
    SCHEMA, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, LOG_RE, _relative,
)

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST_NAME = "stage73-private-manifest.json"


def remote_bytes(transport, file_id, limit):
    if not DRIVE_ID.fullmatch(file_id) or not 0 <= limit <= MAX_FILE_BYTES:
        raise DriveArchiveRejected("invalid_remote_read")
    path = ("/drive/v3/files/" + file_id + "?"
            + urlencode({"alt": "media", "supportsAllDrives": "true"}))
    status, _, data = transport.call("GET", path, limit=limit)
    if status != 200:
        raise DriveArchiveRejected("remote_media_unavailable")
    return data


def validate_remote_manifest(data, source_commit):
    """Use only immutable private manifest metadata, not guest raw content."""
    expected = {"schema", "source_commit", "native_macho_sha256",
                "guest_nro_sha256", "privacy", "files", "file_count",
                "total_bytes", "remote_verified"}
    if (not isinstance(data, dict) or set(data) != expected
            or data.get("schema") != SCHEMA
            or data.get("source_commit") != source_commit
            or data.get("privacy") != "private"
            or data.get("remote_verified") is not False):
        raise DriveArchiveRejected("remote_manifest_identity_invalid")
    for key in ("native_macho_sha256", "guest_nro_sha256"):
        if not isinstance(data.get(key), str) or not HEX64.fullmatch(data[key]):
            raise DriveArchiveRejected("remote_manifest_identity_invalid")
    files = data.get("files")
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise DriveArchiveRejected("remote_manifest_files_invalid")
    size_sum = 0
    paths = set()
    log_count = 0
    receipt_seen = False
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}:
            raise DriveArchiveRejected("remote_manifest_entry_invalid")
        rel = entry["path"]
        if not _relative(rel) or rel in paths:
            raise DriveArchiveRejected("remote_manifest_entry_invalid")
        paths.add(rel)
        if not isinstance(entry["sha256"], str) or not HEX64.fullmatch(entry["sha256"]):
            raise DriveArchiveRejected("remote_manifest_hash_invalid")
        if type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_FILE_BYTES:
            raise DriveArchiveRejected("remote_manifest_size_invalid")
        size_sum += entry["bytes"]
        log_count += bool(LOG_RE.fullmatch(rel))
        receipt_seen |= rel == "smoke_result.json"
    if (log_count != 1 or not receipt_seen or size_sum > MAX_TOTAL_BYTES
            or type(data.get("file_count")) is not int or data["file_count"] != len(files)
            or type(data.get("total_bytes")) is not int
            or data["total_bytes"] != size_sum):
        raise DriveArchiveRejected("remote_manifest_completeness_invalid")
    return files


def list_run_files(transport, folder_id):
    query = "'" + folder_id + "' in parents and trashed = false"
    path = "/drive/v3/files?" + urlencode({
        "q": query, "pageSize": "100",
        "fields": "nextPageToken,files(id,name,mimeType,parents,trashed,shared,size)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    })
    obj, _ = json_response(transport, "GET", path)
    if obj.get("nextPageToken") or not isinstance(obj.get("files"), list):
        raise DriveArchiveRejected("remote_listing_incomplete")
    result = obj["files"]
    if len(result) > MAX_FILES + 1:
        raise DriveArchiveRejected("unexpected_remote_files")
    by_name = {}
    ids = set()
    for item in result:
        if not isinstance(item, dict):
            raise DriveArchiveRejected("invalid_remote_listing")
        name, item_id = item.get("name"), item.get("id")
        if (not isinstance(name, str) or not name or len(name) > 190
                or not isinstance(item_id, str) or not DRIVE_ID.fullmatch(item_id)
                or item_id in ids or name in by_name
                or item.get("parents") != [folder_id]
                or item.get("trashed") is not False
                or item.get("shared") is not False
                or item.get("mimeType") != "application/octet-stream"):
            raise DriveArchiveRejected("invalid_remote_listing")
        byte_size = item.get("size")
        if not isinstance(byte_size, str) or not byte_size.isascii() or not byte_size.isdecimal():
            raise DriveArchiveRejected("invalid_remote_listing_size")
        if int(byte_size) > MAX_FILE_BYTES:
            raise DriveArchiveRejected("invalid_remote_listing_size")
        by_name[name] = item
        ids.add(item_id)
    return by_name


def audit_remote(transport, parent_id, folder_id, run_id, commit, manifest_sha256):
    for value in (parent_id, folder_id):
        if not isinstance(value, str) or not DRIVE_ID.fullmatch(value):
            raise DriveArchiveRejected("invalid_remote_id")
    if (not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id)
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)
            or not isinstance(manifest_sha256, str)
            or not HEX64.fullmatch(manifest_sha256)):
        raise DriveArchiveRejected("invalid_audit_identity")
    remote_folder, _ = json_response(transport, "GET", metadata_path(
        folder_id, "id,name,mimeType,trashed,shared,parents"))
    if (remote_folder.get("id") != folder_id
            or remote_folder.get("name") != "stage73-" + run_id + "-" + commit[:12]
            or remote_folder.get("mimeType") != "application/vnd.google-apps.folder"
            or remote_folder.get("trashed") is not False
            or remote_folder.get("shared") is not False
            or remote_folder.get("parents") != [parent_id]):
        raise DriveArchiveRejected("remote_folder_mismatch")
    children = list_run_files(transport, folder_id)
    manifest_meta = children.get(MANIFEST_NAME)
    if manifest_meta is None:
        raise DriveArchiveRejected("remote_manifest_missing")
    manifest_raw = remote_bytes(transport, manifest_meta["id"], 24576)
    if (hashlib.sha256(manifest_raw).hexdigest() != manifest_sha256
            or int(manifest_meta["size"]) != len(manifest_raw)):
        raise DriveArchiveRejected("remote_manifest_digest_mismatch")
    try:
        manifest = json.loads(manifest_raw)
    except (ValueError, UnicodeError) as error:
        raise DriveArchiveRejected("remote_manifest_invalid_json") from error
    entries = validate_remote_manifest(manifest, commit)
    expected_names = {MANIFEST_NAME}
    for i, entry in enumerate(entries):
        name = str(i).zfill(3) + "-" + entry["path"].rsplit("/", 1)[-1]
        if name in expected_names:
            raise DriveArchiveRejected("duplicate_remote_target")
        expected_names.add(name)
        remote = children.get(name)
        if remote is None or int(remote["size"]) != entry["bytes"]:
            raise DriveArchiveRejected("remote_entry_missing_or_changed")
        payload = remote_bytes(transport, remote["id"], entry["bytes"])
        if (len(payload) != entry["bytes"]
                or hashlib.sha256(payload).hexdigest() != entry["sha256"]):
            raise DriveArchiveRejected("remote_entry_digest_mismatch")
    if set(children) != expected_names:
        raise DriveArchiveRejected("unexpected_remote_files")
    return {"remote_independent_readback_verified": True,
            "retention_policy_verified": False,
            "guest_gpu_frames_verified": False,
            "main_merge_approved": False}


def audit_from_remote_handoff(transport, receipt_parent_id,
                              capture_parent_id, run_id, commit):
    """Locate remote receipt after runner expiry, then audit the capture itself.

    Trust boundary: two previously established private, unshared Drive folders
    and an independently supplied run ID + 40-hex source commit.
    """
    if (not isinstance(receipt_parent_id, str)
            or not DRIVE_ID.fullmatch(receipt_parent_id)
            or not isinstance(capture_parent_id, str)
            or not DRIVE_ID.fullmatch(capture_parent_id)
            or receipt_parent_id == capture_parent_id
            or not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id)
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
        raise DriveArchiveRejected("invalid_handoff_anchor")
    parent, _ = json_response(transport, "GET", metadata_path(
        receipt_parent_id, "id,mimeType,trashed,shared"
    ))
    if (parent.get("id") != receipt_parent_id
            or parent.get("mimeType") != "application/vnd.google-apps.folder"
            or parent.get("trashed") is not False
            or parent.get("shared") is not False):
        raise DriveArchiveRejected("receipt_folder_not_private")
    filename = "stage73-" + run_id + "-" + commit[:12] + "-handoff.json"
    query = ("'" + receipt_parent_id + "' in parents and "
             + "name = '" + filename + "' and trashed = false")
    listing, _ = json_response(transport, "GET", "/drive/v3/files?" + urlencode({
        "q": query, "pageSize": "100",
        "fields": "nextPageToken,files(id,name,mimeType,parents,trashed,shared,size)",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }))
    found = listing.get("files")
    if listing.get("nextPageToken") or not isinstance(found, list) or len(found) != 1:
        raise DriveArchiveRejected("receipt_missing_or_ambiguous")
    item = found[0]
    if (not isinstance(item, dict)
            or item.get("name") != filename
            or item.get("parents") != [receipt_parent_id]
            or item.get("mimeType") != "application/octet-stream"
            or item.get("trashed") is not False
            or item.get("shared") is not False
            or not isinstance(item.get("id"), str)
            or not DRIVE_ID.fullmatch(item["id"])
            or not isinstance(item.get("size"), str)
            or not item["size"].isascii() or not item["size"].isdecimal()
            or not 0 < int(item["size"]) <= 8192):
        raise DriveArchiveRejected("receipt_metadata_invalid")
    raw = remote_bytes(transport, item["id"], 8192)
    if len(raw) != int(item["size"]):
        raise DriveArchiveRejected("receipt_size_mismatch")
    try:
        receipt = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise DriveArchiveRejected("receipt_invalid_json") from error
    keys = {"schema", "privacy", "source_commit", "run_id", "parent_id",
            "run_folder_id", "manifest_sha256", "remote_readback_verified",
            "independent_persistence_verified", "retention_policy_verified",
            "guest_gpu_frames_verified"}
    if (not isinstance(receipt, dict) or set(receipt) != keys
            or receipt.get("schema") != "nexium-stage73-private-drive-handoff/v1"
            or receipt.get("privacy") != "private"
            or receipt.get("source_commit") != commit
            or receipt.get("run_id") != run_id
            or receipt.get("parent_id") != capture_parent_id
            or receipt.get("remote_readback_verified") is not True
            or receipt.get("independent_persistence_verified") is not False
            or receipt.get("retention_policy_verified") is not False
            or receipt.get("guest_gpu_frames_verified") is not False
            or not isinstance(receipt.get("run_folder_id"), str)
            or not DRIVE_ID.fullmatch(receipt["run_folder_id"])
            or receipt["run_folder_id"] in (receipt_parent_id, capture_parent_id)
            or not isinstance(receipt.get("manifest_sha256"), str)
            or not HEX64.fullmatch(receipt["manifest_sha256"])):
        raise DriveArchiveRejected("untrusted_private_receipt")
    evidence = audit_remote(
        transport, capture_parent_id, receipt["run_folder_id"], run_id,
        commit, receipt["manifest_sha256"],
    )
    if evidence["retention_policy_verified"] is not False:
        raise DriveArchiveRejected("untrusted_retention_claim")
    return {**evidence, "remote_receipt_readback_verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent private Drive read-only audit")
    parser.add_argument("--parent-id", required=True)
    parser.add_argument("--folder-id")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--receipt-parent-id")
    args = parser.parse_args(argv)
    try:
        if (os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
                or os.environ.get("NEXIUM_PRIVATE_ARCHIVE_ARMED") != "true"):
            raise DriveArchiveRejected("private_execution_required")
        transport = GoogleTransport(os.environ.get("NEXIUM_DRIVE_ACCESS_TOKEN", ""))
        if args.receipt_parent_id:
            if args.folder_id or args.expected_manifest_sha256:
                raise DriveArchiveRejected("incompatible_audit_inputs")
            result = audit_from_remote_handoff(
                transport, args.receipt_parent_id, args.parent_id,
                args.run_id, args.source_commit,
            )
        else:
            if not args.folder_id or not args.expected_manifest_sha256:
                raise DriveArchiveRejected("missing_audit_inputs")
            result = audit_remote(
                transport, args.parent_id, args.folder_id, args.run_id,
                args.source_commit, args.expected_manifest_sha256,
            )
        if result["retention_policy_verified"] is not False:
            raise DriveArchiveRejected("untrusted_retention_claim")
        print("STAGE73_PRIVATE_REMOTE_PERSISTENCE_READBACK_VERIFIED_RETENTION_UNVERIFIED")
        return 0
    except (DriveArchiveRejected, OSError, KeyError, TypeError, ValueError):
        print("STAGE73_PRIVATE_REMOTE_PERSISTENCE_UNVERIFIED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
