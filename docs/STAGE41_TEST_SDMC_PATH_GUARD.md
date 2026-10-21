# Stage41 — private He-Man lab SD path guard

This is a stacked experimental patch on the Stage40 NeXium Intel work.
It does **not** implement Horizon \`fsp-srv\` IPC or file-system handles.
The pinned NeXium kernel currently dispatches \`fsp-srv\` to an FS stub.
No SD save/load round-trip can be claimed from this patch alone.

The source patch restricts \`fs_host.rs\` to exactly three classes of path:
\`sdmc:/switch\`, \`sdmc:/switch/heman_lore_lab\`, and either
\`progress0.bin\` or \`progress1.bin\` within that directory. It refuses
parent traversal, arbitrary namespaces, nested paths, backslashes,
embedded NULs, special components, and existing symlinks. Host file
access requires an explicitly configured **absolute** \`NEXIUM_DATA_ROOT\`.
Without that environment variable, all translated paths return an error.

**Important security boundary:** checks are lexical and based on
\`symlink_metadata()\` of existing path components. They are **not
race-resistant** against another host process swapping directories or
symlinks after validation. This is therefore **strictly test-only** and
must not be used with personal user files, real SD mounts, or untrusted
guests until secure directory-handle-relative operations are implemented.
Do not merge into production FS/FSP support as a finished sandbox.

A dedicated workflow compiles and runs standalone Rust policy tests,
validates the fail-closed source rewriter, downloads the exact pinned
upstream \`fs_host.rs\`, and applies the patch twice to verify idempotence.
It does not claim that the entire NeXium kernel or guest IPC has compiled.

Next gate: implement genuine, documented Horizon IPC response objects,
file handles, safe file I/O and commit in a disposable test guest root.
Then run a libnx NRO across independent guest process restarts; physical
power-loss durability remains out of scope.
