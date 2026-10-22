# Stage72 — pinned upstream VI/BufferQueue source-risk inventory

## Scope and evidence

The first authentic public libnx framebuffer guest run at Stage68 completed the reviewed 36-PR virtual merge, full Python suite and native Intel Mach-O compilation, but **blocked after the guest attempt**. The only emitted marker was `STAGE68_GUEST_GRAPHICS_RUNTIME_BLOCKED`, so its exact runtime cause is **not known**. Stage71 now retries on a 39-PR virtual integrated tree with private original FileLogger boot milestone classification; that native CI has not yet returned a graphics diagnosis.

Independently, the *actual upstream NeXium source* used by these Intel builds is pinned to immutable public commit `089562567a0a8760dfdd8420e1f57c35159a9219`. We reviewed the exact Git blobs of these five files:

- `nexium-kernel/src/services/sm.rs` — registration list includes `vi:m`, `vi:s`, `vi:u`, and `nvdrv`. A service name's registration **is not proof of fully functioning IPC dispatch**.
- `nexium-kernel/src/services/vi_root_service/handlers.rs` — `get_display_service_u_from_root` is an empty handler in the pinned version, an important service-response implementation risk.
- `nexium-kernel/src/services/application_display_service/handlers.rs` — `open_layer` returns the constant `NATIVE_WINDOW_PARCEL_SIZE` instead of a complete transferable native-window/BufferQueue response contract.
- `nexium-kernel/src/services/vi.rs` — fallback for unknown VI commands logs a warning but returns `SUCCESS`; a local `Arc<Mutex<Vec<Vec<u8>>>>` framebuffer queue exists without proof of end-to-end guest-to-host presentation.
- `nexium-kernel/src/services/nvnflinger.rs` — REQUEST_BUFFER/DEQUEUE_BUFFER appear to return `SUCCESS` without supplying a complete buffer response, unknown commands also return `SUCCESS`, and `compose_frame` may fall back to a constant `0x10` byte-filled frame if no real GPU frame is available.

These are **source-review findings and hypotheses**, not a verified explanation for Stage68's failure. The actual route executed by the original libnx NRO depends on the guest boot, IPC parsing, service command IDs and return payloads. It would be incorrect to infer graphics support from constant `SUCCESS` codes or changing NeXium-owned window pixels alone.

## Guardrails

The new public-source audit reads an exact separate upstream checkout and verifies each of the five pinned Git blob object hashes **before** semantic anchors. The 11 adversarial tests reject unexpected changes in those files, missing service stubs, changed fallback bytes, invalid SHA, symlinked files and missing evidence. Its read-only CI fetches only the public original upstream source at the exact hash. No local patching of emulator code, hidden graphics implementations, runtime emulation claims, firmware/keys, private game data or screenshots.

## Engineering plan after Stage71

1. Use Stage71's authentic boot/guest marker category to locate whether the failure is *before* public libnx main/OutputDebugString or *within* default window/Framebuffer allocation.
2. If graphics guest start is proven, map its exact IPC path and return structures to the reviewed VI root, ApplicationDisplayService, NvFlinger and BinderDriver contracts **without fake-success shortcuts**.
3. Introduce a minimal, testable public graphics service adaptation **only after the actual failing service command and expected ABI are verified**, then build a new virtual Intel integrated artifact in a Draft PR.
4. Verify submitted guest pixel provenance using guest-originated patterns and measured real host window output; do not accept arbitrary host-generated changing pixels as a guest GPU success.

No merge to `main` is approved. This artifact reports `runtime_graphics_failure_cause_confirmed=false` and `guest_gpu_frames_verified=false` by design.
