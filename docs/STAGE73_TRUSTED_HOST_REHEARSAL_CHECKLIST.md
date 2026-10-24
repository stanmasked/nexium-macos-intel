# Stage73 trusted-host rehearsal checklist

Status: preparation only. The live Google Drive API rehearsal has NOT yet run. Do not mark the archive ready from CI or connector smoke tests.

## Scope and trust boundary

This checklist runs the existing synthetic-only rehearsal at `scripts/rehearse_stage73_private_drive.py`. It creates fabricated log/JSON bytes and synthetic Mach-O/NRO identities. It must not read a game image, a real guest capture, or any original/private diagnostic payload.

Run only on a separately reviewed, isolated host that is not a GitHub Actions runner and is not executing pull-request-controlled code. The protected CLI entrypoints reject recognised CI host markers, including GitHub Actions, CircleCI, GitLab CI, Buildkite, Jenkins and other CI platforms. Never unset or bypass these guards. The absence of a CI marker is not proof that a host is trusted: separate operator review of isolation and durable storage remains required. The public PR remains Draft and `archive_ready=false`.

## Preflight — before any upload

- [ ] Check out the exact reviewed commit that contains the current uploader, anchor backup, independent auditor, and synthetic tests. Record the full commit SHA in the private operator record.
- [ ] Confirm the checkout is clean and review the exact scripts being executed; do not run modified/unreviewed files with a Drive credential.
- [ ] Confirm the host is not GitHub Actions, is isolated from ordinary development, and has no public artifact/log upload configured for this process.
- [ ] Supply `NEXIUM_DRIVE_ACCESS_TOKEN` from a protected local secret manager or equivalent trusted secret injection. Never put a token in the command line, repository, a Drive document, a CI variable, or this PR. Do not paste it into ChatGPT.
- [ ] Set `NEXIUM_PRIVATE_ARCHIVE_ARMED=true` only in this isolated process environment.
- [ ] At runtime, select two distinct owner-only My Drive folders: one for synthetic capture objects and one for handoff receipts. The script checks each full ACL ancestry. Do not copy folder IDs or token values into public files or logs.
- [ ] Choose a unique decimal `--run-id` that has not been used before. On any partial failure, inspect the private leftovers before choosing a new ID; do not reuse an ID or automatically delete evidence.
- [ ] Choose two durable anchor destinations in different protection domains, outside the temporary producer workspace. The `--backup` and `--reference` paths must be in separate directories, but separate directories alone do NOT prove independent retention. Do not use two folders on the same ephemeral worker as the claimed independent backup.

## Read-only preflight (recommended before the first upload)

Run the same reviewed command with `--preflight-only` first:

```sh
python3 scripts/rehearse_stage73_private_drive.py \
  --capture-parent-id '<private capture folder ID from protected operator config>' \
  --receipt-parent-id '<distinct private receipt folder ID from protected operator config>' \
  --run-id '<new unique decimal run ID>' \
  --source-commit '<full 40-character reviewed source commit>' \
  --backup '/protected-domain-A/stage73-anchor-<run-id>.json' \
  --reference '/protected-domain-B/stage73-anchor-reference-<run-id>.json' \
  --preflight-only
```

Expected marker: `STAGE73_PRIVATE_SYNTHETIC_DRIVE_PREFLIGHT_VERIFIED_NO_UPLOAD`.

This mode performs read-only Drive checks for both parent ACL chains and exact-name collisions, and opens every component of both future anchor paths with no-follow directory semantics. Untrusted symlinks anywhere in a parent chain are rejected before Drive is queried. On macOS only, the root-owned `/tmp`, `/var`, and `/etc` aliases are accepted when they resolve exactly to `/private/tmp`, `/private/var`, and `/private/etc`; their canonical targets are then traversed without following links. Tests cover a symlinked ancestor that is not itself the final parent directory. It must not issue a remote POST/PUT or create either local anchor file. The run ID is **not reserved** by preflight; the full rehearsal repeats the checks immediately before writing. A successful preflight is not a retention, archive-readiness, or graphics result.

## Execute

From the reviewed repository checkout, run the existing CLI with runtime-supplied private folder IDs and a unique run ID. Do not add the token value to this command.

```sh
python3 scripts/rehearse_stage73_private_drive.py \
  --capture-parent-id '<private capture folder ID from protected operator config>' \
  --receipt-parent-id '<distinct private receipt folder ID from protected operator config>' \
  --run-id '<new unique decimal run ID>' \
  --source-commit '<full 40-character reviewed source commit>' \
  --backup '/protected-domain-A/stage73-anchor-<run-id>.json' \
  --reference '/protected-domain-B/stage73-anchor-reference-<run-id>.json'
```

Expected success marker:

`STAGE73_PRIVATE_SYNTHETIC_DRIVE_REHEARSAL_VERIFIED_RETENTION_UNVERIFIED`

The script itself creates only synthetic bytes, checks folder ACLs before upload, verifies full remote byte read-back, backs up the private receipt anchor, deletes the temporary producer workspace, restores the anchor from the two backup files, and re-runs the read-only remote audit. Its status marker contains no private identifiers, paths, hashes, or payloads.

## Acceptance criteria

All of the following are required:

- [ ] The exact success marker is emitted and the process exits zero.
- [ ] Drive-side synthetic archive and handoff uploads are read back byte-for-byte with the expected SHA-256 values by the script.
- [ ] The anchor is restored and the independent remote audit passes after the temporary producer workspace has been deleted.
- [ ] The two anchor destinations are confirmed by the operator to be durable and independently protected; filesystem path separation alone is not sufficient.
- [ ] The operator separately records the reviewed commit, run ID, success marker, and protection-domain review in a private record. Never publish private folder IDs, receipt hashes, raw payloads, or credentials in GitHub.
- [ ] Partial-failure artifacts, if any, are reviewed privately. Do not automatically delete them; do not retry the same run identity.

## What a pass does NOT prove

Even a successful synthetic rehearsal proves only that this synthetic upload/read-back and immediate anchor-recovery path worked at that time. It does not prove long-term Drive retention, disaster recovery, independent-account/offsite durability unless separately reviewed, real raw-capture preservation, a graphics window, GPU frames, or gameplay.

Keep `archive_ready=false` and the integrated Intel guest-graphics job skipped until the separate retention/access review and independent persistence evidence are complete. Do not merge PR #76 or weaken the gate just because this synthetic rehearsal passes.
