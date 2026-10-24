#!/usr/bin/env python3
"""Stage73 private synthetic Drive rehearsal (NEVER PR CI).

Creates only fabricated logs/receipt. Validates archive and handoff upload,
SHA-256 readback, recoverable offline anchor, removal of producer workspace,
then a new independent remote readback. Not guest GPU or retention proof.
"""
import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlencode

from archive_private_capture_drive import (
    COMMIT, RUN_ID, DRIVE_ID, DriveArchiveRejected, GoogleTransport,
    upload_archive, write_private_handoff, persist_private_handoff,
    write_private_receipt_anchor, json_response, check_parent,
)
from backup_stage73_private_anchor import (
    backup_offline_anchor, verify_offline_anchor, _separate_paths,
)
from seal_private_capture import build_manifest, write_manifest
from verify_stage73_private_drive_persistence import (
    read_independent_anchor, audit_from_remote_handoff,
)

MARKER = "STAGE73_PRIVATE_SYNTHETIC_DRIVE_REHEARSAL_VERIFIED_RETENTION_UNVERIFIED"
ERROR = "STAGE73_PRIVATE_SYNTHETIC_DRIVE_REHEARSAL_BLOCKED"



def preflight_new_rehearsal(transport, capture_parent, receipt_parent,
                            run_id, commit):
    """Reject duplicate remote run IDs before writing any synthetic object."""
    for parent in (capture_parent, receipt_parent):
        check_parent(transport, parent)
    targets = (
        (capture_parent, "stage73-" + run_id + "-" + commit[:12]),
        (receipt_parent, "stage73-" + run_id + "-" + commit[:12] + "-handoff.json"),
    )
    for parent, name in targets:
        query = "'" + parent + "' in parents and name = '" + name + "' and trashed = false"
        path = "/drive/v3/files?" + urlencode({
            "q": query, "pageSize": "2", "fields": "nextPageToken,files(id,name)",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
        })
        result, _ = json_response(transport, "GET", path)
        if (result.get("nextPageToken")
                or not isinstance(result.get("files"), list)
                or len(result["files"]) != 0):
            raise DriveArchiveRejected("synthetic_run_identity_not_unique")


def run_synthetic_rehearsal(transport, capture_parent, receipt_parent,
                            run_id, commit, backup, reference):
    """Exercise real transport interface using fabricated bytes only.

    The caller owns the explicit trusted execution boundary and credentials.
    Returned data is fixed and safe to publish; private IDs never returned.
    """
    if (not isinstance(capture_parent, str)
            or not DRIVE_ID.fullmatch(capture_parent)
            or not isinstance(receipt_parent, str)
            or not DRIVE_ID.fullmatch(receipt_parent)
            or capture_parent == receipt_parent
            or not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id)
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
        raise DriveArchiveRejected("invalid_synthetic_rehearsal_inputs")
    backup = Path(backup)
    reference = Path(reference)
    if (backup == reference or backup.resolve() == reference.resolve()
            or backup.parent.resolve() == reference.parent.resolve()
            or backup.exists() or backup.is_symlink()
            or reference.exists() or reference.is_symlink()
            or not backup.parent.is_dir() or backup.parent.is_symlink()
            or not reference.parent.is_dir() or reference.parent.is_symlink()):
        raise DriveArchiveRejected("unsafe_synthetic_backup_paths")
    # Perform read-only collision and ACL checks before even creating a
    # remote run folder or a private upload session.
    preflight_new_rehearsal(
        transport, capture_parent, receipt_parent, run_id, commit)
    with tempfile.TemporaryDirectory(prefix="nexium-stage73-synthetic-") as root_name:
        root = Path(root_name)
        workspace = root / "workspace"
        workspace.mkdir()
        report = workspace / "report"
        log = report / "data-root" / "logs" / "nexium-synthetic.log"
        log.parent.mkdir(parents=True)
        log.write_bytes(b"SYNTHETIC STAGE73 FAKE IPC DATA. NO ORIGINAL OR GUEST CAPTURE.\n")
        (report / "smoke_result.json").write_bytes(b'{"synthetic_only":true}\n')
        manifest_path = workspace / "private-manifest.json"
        fake_macho = hashlib.sha256(b"stage73-synthetic-macho-not-real").hexdigest()
        fake_nro = hashlib.sha256(b"stage73-synthetic-nro-not-real").hexdigest()
        manifest = build_manifest(report, commit, fake_macho, fake_nro)
        write_manifest(manifest_path, manifest, report)
        receipt_dir = root / "private-handoff"
        anchor_dir = root / "private-anchor"
        receipt_dir.mkdir()
        anchor_dir.mkdir()
        receipt_path = receipt_dir / "synthetic-handoff.json"
        anchor_path = anchor_dir / "synthetic-anchor.json"
        # A protected host must never choose backup paths within the throwaway
        # environment; validate this BEFORE creating any remote Drive files.
        _separate_paths(anchor_path, backup, reference, root)
        uploaded = upload_archive(
            report, manifest_path, capture_parent, run_id, transport)
        write_private_handoff(
            receipt_path, report, capture_parent, run_id, commit, uploaded)
        handoff = persist_private_handoff(
            transport, receipt_path, receipt_parent,
            capture_parent, run_id, commit, uploaded)
        write_private_receipt_anchor(
            anchor_path, report, receipt_path, capture_parent,
            receipt_parent, run_id, commit, uploaded, handoff)
        saved = backup_offline_anchor(
            anchor_path, backup, reference,
            source_commit=commit, run_id=run_id,
            capture_parent=capture_parent, receipt_parent=receipt_parent,
            disposable_root=root)
        if (saved.get("independent_copy_readback_verified") is not True
                or saved.get("remote_retention_verified") is not False):
            raise DriveArchiveRejected("synthetic_backup_not_verified")
    # Both manifest and original anchor are now gone. The only local evidence
    # left is the separately retained backup and its external SHA-256 reference.
    restored = verify_offline_anchor(
        backup, reference, source_commit=commit, run_id=run_id,
        capture_parent=capture_parent, receipt_parent=receipt_parent)
    if (restored.get("independent_copy_readback_verified") is not True
            or restored.get("remote_retention_verified") is not False):
        raise DriveArchiveRejected("synthetic_restore_not_verified")
    receipt_sha = read_independent_anchor(
        backup, commit, run_id, capture_parent, receipt_parent)
    remote = audit_from_remote_handoff(
        transport, receipt_parent, capture_parent, run_id, commit, receipt_sha)
    if (remote.get("remote_independent_readback_verified") is not True
            or remote.get("remote_receipt_readback_verified") is not True
            or remote.get("retention_policy_verified") is not False
            or remote.get("guest_gpu_frames_verified") is not False):
        raise DriveArchiveRejected("synthetic_remote_audit_not_verified")
    return {"synthetic_only": True,
            "independent_remote_readback_verified": True,
            "producer_workspace_deleted": True,
            "offline_anchor_backup_recovered": True,
            "retention_policy_verified": False,
            "guest_gpu_frames_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Protected, SYNTHETIC-ONLY Stage73 Drive upload/recovery exercise")
    parser.add_argument("--capture-parent-id", required=True)
    parser.add_argument("--receipt-parent-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
                or os.environ.get("NEXIUM_PRIVATE_ARCHIVE_ARMED") != "true"):
            raise DriveArchiveRejected("trusted_private_execution_required")
        transport = GoogleTransport(os.environ.get("NEXIUM_DRIVE_ACCESS_TOKEN", ""))
        result = run_synthetic_rehearsal(
            transport, args.capture_parent_id, args.receipt_parent_id,
            args.run_id, args.source_commit, args.backup, args.reference)
        if result.get("retention_policy_verified") is not False:
            raise DriveArchiveRejected("retention_claim_invalid")
        print(MARKER)
        return 0
    except (DriveArchiveRejected, OSError, ValueError, TypeError, KeyError):
        print(ERROR, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
