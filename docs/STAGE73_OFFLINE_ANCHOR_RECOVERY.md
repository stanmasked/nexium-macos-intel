# Stage73 offline private anchor recovery contract

Status: synthetic-only utility. It is **not** integrated into the Draft PR's
raw capture flow. It does not prove permanent or independent remote storage.

Source: scripts/backup_stage73_private_anchor.py.

Once the protected uploader has generated a private 0600 receipt SHA anchor,
a separately trusted process may back it up into a *different secure storage
location* and save the expected full-anchor SHA in another independently
controlled private location. This makes it possible to recover the anchor
after the source runner/work directory has been destroyed.

The tool supports:

- backup: rejects symlinks, hardlinks, non-0600 originals, destination
  overwrites, and backup/reference inside a disposable work tree. Creates
  owner-only files with atomic O_EXCL and fsync, verifies read-back.
- verify: checks both owner-only backup and reference using SHA-256, verifies
  exact source commit/run/folder IDs and anchor schema; works without the
  original source file.
- Fixed vocabulary stdout/stderr only. It never logs private paths, Drive IDs,
  token strings, raw files, hashes, or the actual receipt.

These test fixtures use only fabricated data. On a live protected machine the
reference and copy MUST be held in independent trust domains (ideally separate
providers/devices and credentials) to resist joint tampering. Merely creating
two separate folders on one ephemeral disk or within one Drive account is
**not** independent durability. A real test must verify restoration from the
chosen storage after ending the producer session.

Critically, backup and verify return remote_retention_verified=false. No test,
documentation or workflow change in this PR may set archive_ready=true.
No sensitive materials may be uploaded as public Actions artifacts. No Drive
credentials should be available to code checked out by a Draft PR.
