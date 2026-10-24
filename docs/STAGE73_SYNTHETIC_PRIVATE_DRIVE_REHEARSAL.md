# Stage73 trusted synthetic Drive rehearsal — no original captures

Status: tested against a synthetic/mock transport. Real Google Drive API
rehearsal has NOT run, and independent retention remains UNVERIFIED.

The trusted-machine-only script scripts/rehearse_stage73_private_drive.py
creates fabricated guest log and JSON data, seals a manifest with synthetic
Mach-O/NRO identities, uploads the derived synthetic archive to a separately
configured private capture folder and the handoff to a distinct private
receipt folder. It creates a private receipt SHA anchor, backs that up in two
preconfigured separate local directories (backup and reference), deletes
the ENTIRE temporary producer workspace, and independently re-reads every
remote archive byte via the saved anchor.

The CLI requires NEXIUM_PRIVATE_ARCHIVE_ARMED=true and
NEXIUM_DRIVE_ACCESS_TOKEN in the isolated protected process environment,
and *refuses GitHub Actions altogether*. It never needs any game ROM,
guest raw capture or original copyrighted bytes.

Example for a pre-reviewed, separately trusted private machine only:

python3 scripts/rehearse_stage73_private_drive.py \
  --capture-parent-id '<private folder ID supplied at runtime>' \
  --receipt-parent-id '<separate private folder ID at runtime>' \
  --run-id '<unique decimal rehearsal run ID>' \
  --source-commit '<reviewed 40-character commit ID>' \
  --backup '/private-local-archive-A/<unique anchor>.json' \
  --reference '/independently-owned-archive-B/<unique digest>.json'

The two backup destinations must be permanent private directories OUTSIDE
the ephemeral worker, with separate protection domains in production.
The test creates remote synthetic files in Drive; use a unique run-id.
On partial failure, staging objects may remain private in Drive: do not
automatically delete forensic/audit evidence. Review retention and cleanup
with the protected operator separately.

The script's output is only fixed-vocabulary status; no Drive IDs, hashes,
paths, or payloads. No success marker means the rehearsal is unverified.
Local backup/readback proof does not establish independent hardware or
account separation, disaster recovery, Drive retention policy, or native
emulation success. The native CI archive_ready=false guard is unchanged.
Do not merge PR #76 before protected-environment review and direct
independent persistence evidence.


Before any synthetic Drive upload, the trusted runner checks BOTH protected
parent-folder ACL chains and searches for an existing capture run folder or
private handoff receipt with the same run ID/source-commit. A collision,
missing/incomplete listing, or changed privacy fails without any new POST.
This is a fail-closed optimization for recoverable retries, not a remotely
atomic reservation: concurrent trusted upload processes must not run with
the same identity. Partial failure artifacts must be retained privately
for later review, not automatically deleted.


The core uploader now re-lists the capture run name *after* creating its
folder, before sending capture bytes, and verifies it uniquely resolves to
the newly created folder ID. The handoff uploader likewise re-lists its
receipt name after content upload and fails closed if multiple IDs exist.
These checks mitigate a concurrent duplicate between preflight and upload,
but Google Drive does not offer an atomic name reservation. A protected
single-writer lock is still mandatory. Existing remote objects must remain
private and be reviewed separately on partial failure.


Trusted-host operational checklist:
See [STAGE73_TRUSTED_HOST_REHEARSAL_CHECKLIST.md](STAGE73_TRUSTED_HOST_REHEARSAL_CHECKLIST.md) for the no-secret operator procedure and acceptance criteria. This documentation does not activate the live uploader or change archive readiness.
