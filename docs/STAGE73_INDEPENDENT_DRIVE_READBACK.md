# Stage73 independent Drive persistence audit

Status: synthetic-only, not activated on GitHub or linked to the live Intel run.

scripts/verify_stage73_private_drive_persistence.py provides a second read-only
audit after the original runner's TemporaryDirectory is deleted. An independently
retained private manifest SHA-256, exact source commit, run ID and private
Drive folder IDs are REQUIRED inputs. The verifier checks:

- Private run folder: exact name and parent, no shared permission.
- Complete one-page child listing; no duplicate, missing or extra objects.
- Remote manifest bytes against the independently held SHA-256.
- Manifest schema, source/Mach-O/NRO identities, file count, sizes, paths.
- Every remotely stored file's full bytes and SHA-256, again, WITHOUT accessing
  the original local capture tree.

Never put the private folder IDs, manifest SHA or raw payloads in GitHub logs.
The verifier emits a fixed status marker and deliberately keeps
retention_policy_verified=false, guest_gpu_frames_verified=false. The
independent readback proves temporary-runner independence at that instant,
NOT any future retention guarantee, access policy, backup or offsite replica.

Both CLI programs are explicitly blocked when GITHUB_ACTIONS=true. Any future
deployment must use a separately reviewed protected execution environment;
nothing in this Draft PR grants permissions or sets archive_ready=true.


After the uploader stores its private handoff in a SEPARATE Drive folder,
the auditor can now retrieve that handoff without any local capture files.
Use --receipt-parent-id together with the independently known exact
--source-commit, --run-id and --parent-id. The auditor requires exactly one
unshared handoff with the expected fixed-vocabulary schema and then rechecks
EVERY original capture file using the manifest SHA-256 from the handoff.
The original runner may already be deleted. No secrets, file IDs, or private
contents are printed. Remote readback at this instant is not a retention policy
guarantee. Independent execution on trusted, non-GitHub infrastructure remains
required, and Stage73's real capture gate remains disabled.
