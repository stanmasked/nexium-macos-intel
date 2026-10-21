# Stage40 — opt-in guest HID SVC mapping trace

Stage40 adds **diagnostics only** to the pinned NeXium kernel source during the experimental Intel build. It does not change the behavior of `svcMapSharedMemory` or `svcUnmapSharedMemory`. The patch is applied only when `NEXIUM_EXPERIMENT_STAGE40_GUEST_HID_MAP_TRACE=1` is set, and the emitted marker lines contain no guest virtual addresses, host pointers, or raw handle values.

## Markers

- `STAGE40_SVC_MAP_SHARED_MEMORY_ENTER` — the guest invoked SVC 0x13.
- `STAGE40_SVC_MAP_SIZE_MATCH_HID` / `STAGE40_SVC_MAP_SIZE_OTHER` — whether the requested size matched `HID_SHMEM_SIZE`.
- `STAGE40_SVC_MAP_HANDLE_NONZERO` / `STAGE40_SVC_MAP_HANDLE_ZERO` — only the zero/nonzero property of the handle.
- `STAGE40_HID_SHARED_MEMORY_HOST_BOUND` — the original HID buffer was bound to the mapped host region.
- `STAGE40_HID_SHARED_MEMORY_CPU_MAP_OK` / `STAGE40_HID_SHARED_MEMORY_CPU_MAP_FAILED` — outcome of `cpu.map_host` for the HID region.
- `STAGE40_SVC_UNMAP_SHARED_MEMORY_NOOP` — the guest invoked SVC 0x14, whose pinned implementation is currently a no-op.

Stage38's local trace auditor now records only booleans for these markers in the sanitized report. It never uploads raw logs or pointer-bearing traces.

## Limits

The current native probes deliberately launch NeXium without a game NRO. Therefore an absent SVC map marker means only that the no-NRO process did not exercise this path; it does not imply the path is unreachable for a game. A present host-bound marker still does not prove that guest code read the NPad report. That final proof requires a real game NRO or a controlled guest test that calls SVC 0x13 and reads the mapped region.

The original mapping limitations remain: size-based HID recognition does not validate handle identity, and unmap does not clear the saved VA or unbind the host pointer. Stage40 merely makes future runtime observations safer and unambiguous.
