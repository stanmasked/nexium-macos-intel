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
