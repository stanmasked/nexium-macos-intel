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
import stat
import sys
import tempfile
from urllib.parse import urlsplit, urlencode

from seal_private_capture import verify_manifest, MAX_FILE_BYTES, ArchiveRejected, _relative

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
    if item.get("shared") is not False:
        raise DriveArchiveRejected("remote_file_is_shared")
    if item.get("trashed") is not False or item.get("parents") != [parent_id]:
        raise DriveArchiveRejected("wrong_remote_parent")
    if item.get("mimeType") != "application/octet-stream":
        raise DriveArchiveRejected("wrong_remote_content_type")
    if size is not None and str(item.get("size")) != str(size):
        raise DriveArchiveRejected("wrong_remote_size")


def check_parent(transport, folder_id):
    if not DRIVE_ID.fullmatch(folder_id):
        raise DriveArchiveRejected("invalid_folder")
    fields = "id,mimeType,trashed,shared,capabilities(canAddChildren)"
    data, _ = json_response(transport, "GET", metadata_path(folder_id, fields))
    if (data.get("id") != folder_id or data.get("trashed") is not False
            or data.get("mimeType") != "application/vnd.google-apps.folder"
            or data.get("shared") is not False
            or data.get("capabilities", {}).get("canAddChildren") is not True):
        raise DriveArchiveRejected("remote_folder_not_writable")


def create_run_folder(transport, parent, run_id, commit):
    name = "stage73-" + run_id + "-" + commit[:12]
    data, _ = json_response(
        transport, "POST",
        "/drive/v3/files?" + urlencode({
            "fields": "id,name,mimeType,trashed,parents,shared",
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
            or data.get("trashed") is not False or data.get("shared") is not False):
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
            "fields": "id,name,mimeType,parents,trashed,size,shared",
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
    fields = "id,name,mimeType,trashed,parents,size,shared"
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



def read_sealed_file(root, relative, expected_size, digest):
    """Read a manifest-bound file using no-follow directory/file descriptors.

    Resolve each child via dir_fd, so replacing a parent with a symlink
    between the manifest scan and upload cannot redirect the read.
    """
    if (not _relative(relative) or type(expected_size) is not int
            or not 0 <= expected_size <= MAX_FILE_BYTES
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise DriveArchiveRejected("invalid_sealed_entry")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    opened = []
    try:
        opened.append(os.open(root, directory_flags))
        for component in relative.split("/")[:-1]:
            opened.append(os.open(component, directory_flags, dir_fd=opened[-1]))
        file_fd = os.open(relative.split("/")[-1], file_flags, dir_fd=opened[-1])
        opened.append(file_fd)
        stat_before = os.fstat(file_fd)
        if (not stat.S_ISREG(stat_before.st_mode) or stat_before.st_nlink != 1
                or stat_before.st_size != expected_size):
            raise DriveArchiveRejected("unsafe_local_file")
        chunks = []
        size = 0
        while True:
            block = os.read(file_fd, min(1048576, expected_size - size + 1))
            if not block:
                break
            size += len(block)
            if size > expected_size:
                raise DriveArchiveRejected("local_file_changed")
            chunks.append(block)
        stat_after = os.fstat(file_fd)
        if (stat_before.st_size != stat_after.st_size
                or stat_before.st_mtime_ns != stat_after.st_mtime_ns
                or stat_before.st_ctime_ns != stat_after.st_ctime_ns):
            raise DriveArchiveRejected("local_file_changed")
        data = b"".join(chunks)
        if size != expected_size or hashlib.sha256(data).hexdigest() != digest:
            raise DriveArchiveRejected("local_file_changed")
        return data
    except OSError as error:
        raise DriveArchiveRejected("local_file_unsafe_or_missing") from error
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)



def read_private_manifest_bytes(path, expected):
    """Read the sealed private manifest without following a swapped symlink."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > 24576):
                raise DriveArchiveRejected("unsafe_private_manifest")
            payload = os.read(fd, 24577)
            after = os.fstat(fd)
            if (len(payload) != before.st_size or len(payload) > 24576
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_ctime_ns != after.st_ctime_ns):
                raise DriveArchiveRejected("changed_private_manifest")
        finally:
            os.close(fd)
    except OSError as error:
        raise DriveArchiveRejected("unreadable_private_manifest") from error
    try:
        parsed = json.loads(payload)
    except (UnicodeError, ValueError) as error:
        raise DriveArchiveRejected("invalid_private_manifest") from error
    if parsed != expected:
        raise DriveArchiveRejected("changed_private_manifest")
    return payload


def write_private_handoff(path, report, parent_id, run_id, commit, upload_result):
    """Store PRIVATE receipt outside the entire disposable guest work tree."""
    path = Path(path)
    work_root = report.parent.resolve()
    resolved = path.resolve()
    if (resolved == work_root or work_root in resolved.parents
            or path.exists() or path.is_symlink()
            or not path.parent.is_dir() or path.parent.is_symlink()):
        raise DriveArchiveRejected("unsafe_private_handoff_path")
    folder = upload_result.get("private_run_folder_id")
    manifest_sha = upload_result.get("private_manifest_sha256")
    if (not isinstance(folder, str) or not DRIVE_ID.fullmatch(folder)
            or not isinstance(manifest_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha)
            or upload_result.get("readback_verified") is not True
            or upload_result.get("retention_verified") is not False):
        raise DriveArchiveRejected("untrusted_private_handoff")
    receipt = {
        "schema": "nexium-stage73-private-drive-handoff/v1",
        "privacy": "private",
        "source_commit": commit,
        "run_id": run_id,
        "parent_id": parent_id,
        "run_folder_id": folder,
        "manifest_sha256": manifest_sha,
        "remote_readback_verified": True,
        "independent_persistence_verified": False,
        "retention_policy_verified": False,
        "guest_gpu_frames_verified": False,
    }
    descriptor, tmp = tempfile.mkstemp(prefix=".stage73-private-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as out:
            json.dump(receipt, out, sort_keys=True, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        if path.exists() or path.is_symlink():
            raise DriveArchiveRejected("private_handoff_collision")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def persist_private_handoff(transport, path, receipt_parent_id,
                            capture_parent_id, run_id, commit, upload_result):
    """Upload the private handoff to a DISTINCT private folder with read-back.

    A locally sealed report and verified payload uploads alone are not
    sufficient: the receipt must survive the disposable runner as well.
    """
    remote_folder = upload_result.get("private_run_folder_id")
    manifest_sha = upload_result.get("private_manifest_sha256")
    if (not isinstance(receipt_parent_id, str)
            or not DRIVE_ID.fullmatch(receipt_parent_id)
            or receipt_parent_id in (capture_parent_id, remote_folder)
            or not isinstance(capture_parent_id, str)
            or not DRIVE_ID.fullmatch(capture_parent_id)
            or not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id)
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)
            or not isinstance(remote_folder, str)
            or not DRIVE_ID.fullmatch(remote_folder)
            or not isinstance(manifest_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha)
            or upload_result.get("readback_verified") is not True
            or upload_result.get("retention_verified") is not False):
        raise DriveArchiveRejected("unsafe_receipt_destination")
    expected = {
        "schema": "nexium-stage73-private-drive-handoff/v1",
        "privacy": "private",
        "source_commit": commit,
        "run_id": run_id,
        "parent_id": capture_parent_id,
        "run_folder_id": remote_folder,
        "manifest_sha256": manifest_sha,
        "remote_readback_verified": True,
        "independent_persistence_verified": False,
        "retention_policy_verified": False,
        "guest_gpu_frames_verified": False,
    }
    raw = read_private_manifest_bytes(Path(path), expected)
    if len(raw) > 8192:
        raise DriveArchiveRejected("oversized_private_receipt")
    # Check BOTH privacy and writability of the separate receipt folder.
    check_parent(transport, receipt_parent_id)
    name = "stage73-" + run_id + "-" + commit[:12] + "-handoff.json"
    receipt_sha = hashlib.sha256(raw).hexdigest()
    upload_one(transport, receipt_parent_id, name, raw, receipt_sha)
    return {"private_receipt_readback_verified": True,
            # This MUST be anchored independently of remote Drive contents.
            # Never print it or put it in PR logs.
            "private_receipt_sha256": receipt_sha,
            "independent_persistence_verified": False,
            "retention_policy_verified": False}


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
        data = read_sealed_file(report, entry["path"], entry["bytes"], entry["sha256"])
        name = str(index).zfill(3) + "-" + entry["path"].rsplit("/", 1)[-1]
        upload_one(transport, folder_id, name, data, entry["sha256"])
        count += 1
    verify_manifest(report, manifest_path)
    raw = read_private_manifest_bytes(manifest_path, manifest)
    manifest_sha = hashlib.sha256(raw).hexdigest()
    upload_one(transport, folder_id, "stage73-private-manifest.json",
               raw, manifest_sha)
    # Remote retention/access policy must be independently verified; do not
    # set archive_ready or remote_retention_verified here.
    return {"readback_verified": True, "retention_verified": False,
            "uploaded_files": count + 1,
            # These values MUST only be written to an independently persisted
            # private handoff receipt; never print the result object.
            "private_run_folder_id": folder_id,
            "private_manifest_sha256": manifest_sha}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trusted-runner Drive readback verification")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--parent-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--receipt-path", type=Path)
    parser.add_argument("--receipt-parent-id")
    args = parser.parse_args(argv)
    try:
        # A code-controlled env toggle alone is not a trust boundary. While
        # the uploader is experimental, forbid all GitHub-hosted execution.
        # Run only from an independently reviewed, isolated private machine.
        if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
            raise DriveArchiveRejected("github_runner_forbidden")
        if os.environ.get("NEXIUM_PRIVATE_ARCHIVE_ARMED") != "true":
            raise DriveArchiveRejected("uploader_not_armed")
        if args.receipt_path is None or not args.receipt_parent_id:
            raise DriveArchiveRejected("private_handoff_required")
        if (not DRIVE_ID.fullmatch(args.receipt_parent_id)
                or args.receipt_parent_id == args.parent_id):
            raise DriveArchiveRejected("unsafe_receipt_destination")
        transport = GoogleTransport(os.environ.get("NEXIUM_DRIVE_ACCESS_TOKEN", ""))
        result = upload_archive(args.report, args.manifest,
                                args.parent_id, args.run_id, transport)
        manifest_data = json.loads(args.manifest.read_text(encoding="utf-8"))
        write_private_handoff(args.receipt_path, args.report, args.parent_id,
                              args.run_id, manifest_data["source_commit"], result)
        handoff = persist_private_handoff(
            transport, args.receipt_path, args.receipt_parent_id,
            args.parent_id, args.run_id, manifest_data["source_commit"], result,
        )
        if (result["retention_verified"] is not False
                or handoff["independent_persistence_verified"] is not False
                or handoff["retention_policy_verified"] is not False):
            raise DriveArchiveRejected("retention_claim_invalid")
        print("STAGE73_REMOTE_CAPTURE_AND_HANDOFF_READBACK_VERIFIED_RETENTION_UNVERIFIED")
        return 0
    except (DriveArchiveRejected, OSError, ValueError, TypeError, KeyError):
        print("STAGE73_PRIVATE_DRIVE_ARCHIVE_BLOCKED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
