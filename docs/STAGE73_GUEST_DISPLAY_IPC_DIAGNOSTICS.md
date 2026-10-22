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

A new parser reads at most one private original FileLogger (bounded at 16 MiB) and outputs only fixed booleans for source-anchored milestones. The CI also downloads the exact pinned public svc.rs, verifies its Git blob SHA-1, checks the real log templates and levels, and rejects marker drift before the native run:

1. service-manager lookup of `vi:u` and the actual `vi:u` IPC request;
2. creation of an `IApplicationDisplayService` subsession;
3. the `IApplicationDisplayService` command 100/103 request and corresponding `IHOSBinderDriver` subsession creation;
4. the OpenLayer/native-window command 2020/2030 request and its matching first-occurrence response;
5. the first Binder-driver transaction after the native-window response, then IGBP Connect and RequestBuffer;
6. the last allowlisted IPC request, whether its first-occurrence response follows, and ambiguity if the same command was previously answered;
7. positive DequeueBuffer retry/timeout diagnostics or QueueBuffer evidence. A normal successful DequeueBuffer record is TRACE-only at the current DEBUG log level, so its absence is reported as unverified rather than as proof that dequeue did not occur;
8. original guest default-window and framebuffer-created markers.

The stage classifier emits no raw log lines, dynamic service names, command IDs, IPC bytes, paths or screenshots. The VI service-handle marker follows the actual `SM::GetServiceHandle 'vi:u'` handler format. If scoped IPC request markers are absent it reports `ipc_request_markers_not_observed` rather than claiming that no service call happened. Missing TRACE-only dequeue-success logging is never treated as a missing operation. Every outcome keeps guest GPU and gameplay proof false. This is observation only, not a guessed VI/Binder fix.

## Validation and next decision

- 29 display-IPC fixtures cover progressive boundaries, the real handler-marker spelling, the source-mapped Binder-session-before-native-window order, out-of-order evidence rejection, debug-visible dequeue retry/timeout behavior and last-request/response ordering; 9 additional fixtures validate the exact scoped source patch, original Git blob, native build wiring, symlink rejection and no mutation on mismatch.
- The lightweight Stage73 CI audits the exact pinned svc.rs log templates and levels, then covers these fixtures and Stage68/70/71 predecessors.
- A separate native Intel workflow repeats the exact virtual integration at depth 40 and emits only sanitized Stage71/Stage73 classifications.

After the exact native run completes, implement only the first specific missing response/handler demonstrated by the allowlisted marker sequence. Do not treat an IPC request or a framebuffer API call returning as visible guest GPU rendering. All PRs remain Draft and `main` unchanged.
