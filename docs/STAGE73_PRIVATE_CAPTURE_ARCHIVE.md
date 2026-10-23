# Stage73 — private capture archival contract

State: only a local integrity checker is implemented. Drive authentication,
upload, remote digest read-back and retention verification remain UNIMPLEMENTED.
The native CI guard must keep archive_ready=false; a skipped Intel job cannot
be counted as graphics success.

scripts/seal_private_capture.py seals a temporary guest report while it
still exists and rejects absent/duplicate original logs, symlinks, hardlinks,
file mutations, traversal and unlisted files. Limits: 64 files, 32 MiB/file,
96 MiB combined. The 0600 private manifest, outside the report directory,
binds source commit, Mach-O/NRO SHA-256 and each file's path/size/SHA-256.
All outputs explicitly say LOCAL_ONLY and remote_verified stays false.

Required before native capture: configure a restricted private Drive folder
and scoped authentication; seal and upload in the SAME Intel runner before
TemporaryDirectory cleanup; read back EVERY file and verify SHA-256; check
remote retention; emit a separate private remote-verification receipt; validate
the entire flow with synthetic data before opening the archive_ready gate.
Original inputs/captures stay immutable. Derived reports remain separate.
Never upload raw logs, capture manifests or screenshots to public GitHub
Actions artifacts. All work stays in Draft; main is unchanged.
