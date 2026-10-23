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


CRITICAL: A receipt retrieved from Drive is not an independent trust anchor
for itself. The receipt-mode CLI REQUIRES --expected-receipt-sha256, calculated
from the original 0600 handoff before runner deletion and held in a separate
trusted location outside the capture/receipt Drive folders. The auditor hashes
the remote receipt BEFORE trusting any of its metadata or following remote
folder IDs. Without this independent anchor, an attacker with write access
to both capture and receipt folders could forge a self-consistent set of files.
No automatic fallback or trust-on-first-use is allowed. A manifest/receipt
fingerprint read from the same remote folder is insufficient.


The independent audit CLI now accepts --anchor-path as an alternative to
--expected-receipt-sha256. A local anchor is read using O_NOFOLLOW from a
single regular owner-only (0600) file with an exact private schema and exact
source/run/parent identities. The SHA-256 stored there must match the remote
receipt before the auditor follows any receipt-provided folder information.
Do NOT use both anchor options simultaneously. An anchor file derived from
the remote Drive receipt is not independent; it must originate from the
trusted uploader and survive on separately controlled storage. This still
does not prove long-term retention, backup replication, or GPU execution.
