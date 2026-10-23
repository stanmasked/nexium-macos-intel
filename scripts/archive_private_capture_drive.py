#!/usr/bin/env python3
"""Upload an already-sealed private Stage73 report to Drive and read back each byte.

NOT wired to pull_request CI. A Drive token must never be available to PR code.
This verifies upload integrity, not remote retention or guest GPU rendering.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlencode

from seal_private_capture import verify_manifest, MAX_FILE_BYTES, ArchiveRejected

HOST = "www.googleapis.com"
DRIVE_ID = re.compile(r"[A-Za-z0-9_-]{10,128}\Z")
RUN_ID = re.compile(r"[0-9]{1,20}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_METADATA = 16384


class DriveArchiveRejected(ValueError):
    """No raw response bodies, paths, tokens or identifiers in error messages."""


class GoogleTransport:
    def __init__(self, token):
        if not token or len(token) > 8192 or "\n" in token or "\r" in token:
            raise DriveArchiveRejected("invalid_credentials")
        self._token = token

    def call(self, method, path, body=b"", headers=None, limit=MAX_METADATA):
        if not path.startswith("/") or path.startswith("//"):
            raise DriveArchiveRejected("unsafe_url")
        request_headers = {
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json",
        }
        request_headers.update(headers or {})
        connection = http.client.HTTPSConnection(HOST, timeout=45)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            status = response.status
            response_headers = dict(response.getheaders())
            content = response.read(limit + 1)
            if len(content) > limit:
                raise DriveArchiveRejected("oversized_remote_response")
            return status, response_headers, content
        except (OSError, http.client.HTTPException) as error:
            raise DriveArchiveRejected("remote_transport_failed") from error
        finally:
            connection.close()


def json_response(transport, method, path, body=b"", headers=None):
    status, response_headers, raw = transport.call(
        method, path, body=body, headers=headers, limit=MAX_METADATA
    )
    if status not in (200, 201):
        raise DriveArchiveRejected("remote_status_failed")
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError, TypeError) as error:
        raise DriveArchiveRejected("invalid_remote_json") from error
    if not isinstance(data, dict):
        raise DriveArchiveRejected("invalid_remote_json")
    return data, response_headers


def metadata_path(file_id, fields):
    if not DRIVE_ID.fullmatch(file_id):
        raise DriveArchiveRejected("invalid_remote_id")
    return ("/drive/v3/files/" + file_id + "?" +
            urlencode({"fields": fields, "supportsAllDrives": "true"}))


def validate_metadata(item, *, file_id, parent_id, filename, size=None):
    if item.get("id") != file_id or item.get("name") != filename:
        raise DriveArchiveRejected("wrong_remote_identity")
    if item.get("trashed") is not False or item.get("parents") != [parent_id]:
        raise DriveArchiveRejected("wrong_remote_parent")
    if item.get("mimeType") != "application/octet-stream":
        raise DriveArchiveRejected("wrong_remote_content_type")
    if size is not None and str(item.get("size")) != str(size):
        raise DriveArchiveRejected("wrong_remote_size")


def check_parent(transport, folder_id):
    if not DRIVE_ID.fullmatch(folder_id):
        raise DriveArchiveRejected("invalid_folder")
    fields = "id,mimeType,trashed,capabilities(canAddChildren)"
    data, _ = json_response(transport, "GET", metadata_path(folder_id, fields))
    if (data.get("id") != folder_id or data.get("trashed") is not False
            or data.get("mimeType") != "application/vnd.google-apps.folder"
            or data.get("capabilities", {}).get("canAddChildren") is not True):
        raise DriveArchiveRejected("remote_folder_not_writable")


def create_run_folder(transport, parent, run_id, commit):
    name = "stage73-" + run_id + "-" + commit[:12]
    data, _ = json_response(
        transport, "POST",
        "/drive/v3/files?" + urlencode({
            "fields": "id,name,mimeType,trashed,parents",
            "supportsAllDrives": "true",
        }),
        body=json.dumps({
            "name": name, "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent],
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    folder_id = data.get("id")
    if (not isinstance(folder_id, str) or not DRIVE_ID.fullmatch(folder_id)
            or data.get("name") != name or data.get("parents") != [parent]
            or data.get("mimeType") != "application/vnd.google-apps.folder"
            or data.get("trashed") is not False):
        raise DriveArchiveRejected("folder_creation_unverified")
    return folder_id


def upload_one(transport, folder_id, name, payload, digest):
    if not name or "/" in name or len(name) > 190:
        raise DriveArchiveRejected("invalid_entry_name")
    if len(payload) > MAX_FILE_BYTES or hashlib.sha256(payload).hexdigest() != digest:
        raise DriveArchiveRejected("local_capture_changed")
    init_metadata = {
        "name": name, "parents": [folder_id],
        "mimeType": "application/octet-stream",
    }
    status, headers, _ = transport.call(
        "POST",
        "/upload/drive/v3/files?" + urlencode({
            "uploadType": "resumable",
            "fields": "id,name,mimeType,parents,trashed,size",
            "supportsAllDrives": "true",
        }),
        body=json.dumps(init_metadata).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Upload-Content-Type": "application/octet-stream",
            "X-Upload-Content-Length": str(len(payload)),
        },
    )
    if status != 200:
        raise DriveArchiveRejected("upload_init_failed")
    location = next((value for key, value in headers.items()
                     if key.lower() == "location"), None)
    if not location:
        raise DriveArchiveRejected("upload_session_missing")
    parsed = urlsplit(location)
    if (parsed.scheme != "https" or parsed.netloc != HOST
            or parsed.path != "/upload/drive/v3/files" or not parsed.query
            or parsed.username or parsed.password):
        raise DriveArchiveRejected("upload_session_unsafe")
    remote, _ = json_response(
        transport, "PUT", parsed.path + "?" + parsed.query,
        body=payload, headers={"Content-Type": "application/octet-stream"},
    )
    file_id = remote.get("id")
    if not isinstance(file_id, str) or not DRIVE_ID.fullmatch(file_id):
        raise DriveArchiveRejected("upload_id_missing")
    fields = "id,name,mimeType,trashed,parents,size"
    verified, _ = json_response(transport, "GET", metadata_path(file_id, fields))
    validate_metadata(verified, file_id=file_id, parent_id=folder_id,
                      filename=name, size=len(payload))
    path = ("/drive/v3/files/" + file_id + "?" +
            urlencode({"alt": "media", "supportsAllDrives": "true"}))
    status, _, readback = transport.call(
        "GET", path, limit=len(payload)
    )
    if (status != 200 or len(readback) != len(payload)
            or hashlib.sha256(readback).hexdigest() != digest):
        raise DriveArchiveRejected("remote_readback_mismatch")
    return file_id


def upload_archive(report, manifest_path, parent_id, run_id, transport):
    if not RUN_ID.fullmatch(run_id):
        raise DriveArchiveRejected("invalid_run_id")
    try:
        verify_manifest(report, manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ArchiveRejected, OSError, UnicodeError, ValueError) as error:
        raise DriveArchiveRejected("invalid_local_capture") from error
    commit = manifest["source_commit"]
    if not COMMIT.fullmatch(commit):
        raise DriveArchiveRejected("invalid_source_commit")
    # Fail before creating a remote folder if the manifest points to files
    # that changed since sealing. The first verification above does this.
    check_parent(transport, parent_id)
    folder_id = create_run_folder(transport, parent_id, run_id, commit)
    count = 0
    for index, entry in enumerate(manifest["files"]):
        # No arbitrary traversal: the locally sealed manifest has already been
        # validated; repeat it to catch changes between reads.
        verify_manifest(report, manifest_path)
        source = report / entry["path"]
        if source.is_symlink() or not source.is_file():
            raise DriveArchiveRejected("invalid_local_file")
        data = source.read_bytes()
        name = str(index).zfill(3) + "-" + source.name
        upload_one(transport, folder_id, name, data, entry["sha256"])
        count += 1
    verify_manifest(report, manifest_path)
    raw = manifest_path.read_bytes()
    upload_one(transport, folder_id, "stage73-private-manifest.json",
               raw, hashlib.sha256(raw).hexdigest())
    # Remote retention/access policy must be independently verified; do not
    # set archive_ready or remote_retention_verified here.
    return {"readback_verified": True, "retention_verified": False,
            "uploaded_files": count + 1}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trusted-runner Drive readback verification")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--parent-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        if os.environ.get("NEXIUM_PRIVATE_ARCHIVE_ARMED") != "true":
            raise DriveArchiveRejected("uploader_not_armed")
        transport = GoogleTransport(os.environ.get("NEXIUM_DRIVE_ACCESS_TOKEN", ""))
        result = upload_archive(args.report, args.manifest,
                                args.parent_id, args.run_id, transport)
        if result["retention_verified"] is not False:
            raise DriveArchiveRejected("retention_claim_invalid")
        print("STAGE73_REMOTE_SHA256_READBACK_VERIFIED_RETENTION_UNVERIFIED")
        return 0
    except (DriveArchiveRejected, OSError, ValueError, TypeError, KeyError):
        print("STAGE73_PRIVATE_DRIVE_ARCHIVE_BLOCKED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
