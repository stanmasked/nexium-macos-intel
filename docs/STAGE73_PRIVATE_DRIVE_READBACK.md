# Stage73 private Drive remote integrity (experimental and NOT armed)

Local integrity: scripts/seal_private_capture.py, 17 synthetic fixtures.

Remote integrity: scripts/archive_private_capture_drive.py provides a fail-closed
Drive API upload/read-back prototype. It requires NEXIUM_PRIVATE_ARCHIVE_ARMED=true
and NEXIUM_DRIVE_ACCESS_TOKEN in a separately trusted execution context. It
validates the private destination folder, creates a unique run folder, uploads
each sealed capture file using Drive resumable upload, reads back every byte
and checks SHA-256 and remote size/parent; it sends the sealed manifest last.
All remote responses and credentials remain private. Console output uses
fixed status markers only; never print private paths, file IDs, raw reports,
upload sessions or credentials.

Tests/tests_stage73_drive_readback.py is not the expected test path;
the real fixture is tests/test_stage73_drive_readback.py.

SECURITY: Do NOT expose Drive tokens in a pull_request, workflow_run,
pull_request_target or any workflow executing a Draft PR checkout. Such code
may be untrusted, and GitHub secret scoping can be bypassed by unsafe
privileged workflows. Use an independently reviewed trusted deployment
environment with protected refs and scoped credentials, and only run this
prototype after it has been reviewed/landed in a trusted location.
Never pass a personal OAuth refresh token through PR jobs or repository code.

Upload SHA-256 read-back is NOT verified retention. The prototype deliberately
reports retention_verified=false. Retention policy, remote access review and
a second independent persistence check must be completed before the readiness
gate can be set to true. Never override the existing archive_ready=false
until full end-to-end verification on synthetic content succeeds.

The already-created project Drive structure uses separate private folders for
originals, raw captures, manifests and aggregate reports. Do not share its
private contents in a public GitHub repository. Stage73 remains Draft.

Additional fail-closed privacy gate: before creating the run folder the Drive
parent metadata must explicitly report shared=false and writable folder
capabilities. The created folder and every uploaded file must also return
shared=false. A shared or unknown ACL blocks the upload, even if checksums
would match. This prototype is intended for private My Drive contexts;
service-account/shared-folder configurations need an independently reviewed
privacy design rather than bypassing this check.

Hardening checkpoint: the uploader now reads each capture entry through
directory-relative O_NOFOLLOW descriptors and checks inode regularity,
hardlink count, size, timestamps and digest before any upload. This closes
path/symlink switching between the seal scan and the network operation.
The experimental CLI explicitly blocks execution under GITHUB_ACTIONS=true,
even with the arm switch set; CI runs only the synthetic mock transport tests.
A future verified, protected deployment requires a separately reviewed release
workflow, not a flag change on this Draft PR.

The upload command additionally requires --receipt-path, pointing to an
existing secure directory outside the whole disposable guest work tree.
After remote byte read-back, it writes an atomic 0600 PRIVATE handoff record,
never to stdout. That record contains the exact remote folder ID and original
manifest SHA-256 for the independent persistence auditor. Do not store this
receipt in a transient runner directory; place a copy in the project's
private 00_Manifest_and_SHA256 Drive area by an independently trusted
archival process. An absent or unpersisted receipt is NOT backup proof.


New fail-closed private receipt storage requirement:
The trusted CLI requires --receipt-parent-id pointing to a separate, private
Drive folder (NOT the capture parent). After the original capture bytes and
manifest have been read back, it creates the 0600 local handoff, uploads the
handoff to the receipt folder and reads that upload back by full SHA-256.
A missing, modified, symlinked, shared or unverified handoff aborts without a
successful completion marker. The private receipt is essential for locating
the archive after the disposable source directory disappears.
The existing dedicated private Stage73 receipt folder must be configured
only at protected runtime; never embed its ID or tokens into public code.
Independent persistence and long-term retention both remain explicitly false
until later separate validation.


The uploader's persist_private_handoff() returns a
private_receipt_sha256 computed over its locally held 0600 receipt. The caller
must anchor this SHA-256 in a separately controlled private audit record,
independent of the raw-capture and receipt Drive folders, before the
temporary source is deleted. The independent auditor will NOT accept a
receipt without this external checksum. No checksum or private IDs in public
GitHub Actions logs; the live integration remains disabled.


A separate local integrity anchor is now required for the trusted CLI:
--anchor-path must point outside the guest temporary work tree and must not
be the receipt file. The uploader exclusively creates a 0600 JSON anchor
containing the original source identity, parent folders, and the SHA-256 of
the privately uploaded/verified handoff receipt. It refuses to overwrite an
existing anchor or create one before all remote upload read-backs pass.

IMPORTANT: a local anchor is NOT an independently durable copy. A separate
trusted backup process must copy it to a protected location independently
controlled from the capture and receipt Drive folders, verify the copied SHA,
and confirm recovery after temporary runner deletion. Until then, both
retention and the readiness gate remain unverified/false.


The local private handoff receipt also uses atomic exclusive publication,
not an exists-check followed by os.replace. A concurrent process cannot
replace an existing private receipt; exact collision leaves the original
unchanged. This is separate from, and does not establish, remote persistence
or retention.


Privacy hardening: the trusted uploader now inspects the full Drive parent
hierarchy to the root before sending any private payload. Every ancestor must
expose exactly one user-owner ACL grant; shared drives, missing permissions,
extra grants, shared ancestors and cycles fail closed. Every created folder
and uploaded file must also expose a single owner-only ACL. This is stricter
than shared=false alone (which does not prove that no inherited permissions
exist). This profile is restricted to owner-authenticated private My Drive.
A service account or delegated writer in someone else's folder requires a
separately audited access design rather than bypassing the owner check.
