# Stage73 — bounded original guest display IPC diagnosis

## Stage71 result

The native Stage71 integrated run `39821434769` failed closed after compiling the original public libnx checkerboard NRO, passing the reviewed virtual merge, passing the integrated Python suite, and producing the native Intel Mach-O. Its private-log classifier reported:

- the original public NRO was auto-loaded;
- the guest booted and its guest context was ready;
- `svcOutputDebugString` was reached and the original `STAGE67_GUEST_GRAPHICS_START` marker was observed;
- the process remained alive until the guest-smoke timeout;
- no later guest marker proved default-window acquisition, framebuffer creation or presentation.

This places the observed stall **after guest main-start marker and before any verified framebuffer completion**, but Stage71's debug-level log did not include the generic IPC request trace. It therefore did not prove whether the first blocked call was service-manager lookup, VI service/session creation, OpenLayer, Binder or BufferQueue.

## Stage73 change

The next run keeps `NEXIUM_LOG_LEVEL=debug` and applies a source-pinned, temporary instrumentation patch to exactly one generic IPC-request log call in the disposable upstream checkout: `log::trace!` becomes `log::debug!` for that single request record. It does **not** enable global TRACE (which would log every guest SVC). The smoke duration is reduced from 70 to 25 seconds, and no guest or service behavior changes. The smoke receipt is still bound to the exact native Mach-O and public NRO SHA-256.

A new parser reads at most one private original FileLogger (bounded at 16 MiB) and outputs only fixed booleans for source-anchored milestones:

1. service-manager lookup of `vi:u`;
2. creation of an `IApplicationDisplayService` subsession;
3. the original IPC request/response marker for OpenLayer commands 2020/2030;
4. creation and first transaction of `IHOSBinderDriver`;
5. original IGBP Connect, RequestBuffer, DequeueBuffer and QueueBuffer markers;
6. original guest default-window and framebuffer-created markers.

The stage classifier emits no raw log lines, dynamic service names, command IDs, IPC bytes, paths or screenshots. If scoped IPC request markers are absent it reports `ipc_request_markers_not_observed` rather than claiming that no service call happened. Every outcome keeps guest GPU and gameplay proof false. This is observation only, not a guessed VI/Binder fix.

## Validation and next decision

- 18 new adversarial fixtures cover each progressive boundary, wrong executable/NRO identity, invalid smoke status, absent/duplicate/symlinked logs and oversized trace.
- The lightweight Stage73 CI covers these fixtures and Stage68/70/71 predecessors.
- A separate native Intel workflow repeats the exact virtual integration at depth 40 and emits only sanitized Stage71/Stage73 classifications.

After the exact native run completes, implement only the first specific missing response/handler demonstrated by the allowlisted marker sequence. Do not treat an IPC request or a framebuffer API call returning as visible guest GPU rendering. All PRs remain Draft and `main` unchanged.
