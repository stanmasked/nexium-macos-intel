# Stage39 — Guest HID IPC and shared-memory mapping source audit

## Pinned source

This audit targets NeXium revision `089562567a0a8760dfdd8420e1f57c35159a9219` and fetches the original files in CI. It is source-contract evidence only; it does not claim a running guest game mapped or read the region.

## Confirmed production route

1. In `nexium-kernel/src/kernel/svc.rs`, `subsession_service` routes `("hid", 0)` to `IAppletResource`.
2. `IAppletResource` command 0 returns a handle created with `HandleType::SharedMemory`.
3. The SVC dispatcher routes `0x13` to `svc_map_shared_memory` and `0x14` to `svc_unmap_shared_memory`.
4. `svc_map_shared_memory` recognizes HID shared memory by `size == HID_SHMEM_SIZE`, maps the guest address as `hid_shmem` if needed, sets `HidState.shmem_va`, records `Kernel.hid_mapped_host_ptr`, calls `HidState.bind_mapped_host(region.host_ptr)`, and attempts to register that region through `cpu.map_host`.
5. In `hid_state.rs`, the original tick path copies the serialized internal HID buffer into the mapped host region. The existing `NEXIUM_HID_TRACE=1` diagnostic reads the serialized NPad LIFO values from the internal buffer.

## Confirmed implementation limitations

- The HID-size branch does **not validate the supplied handle**. A zero handle is logged as an error, but execution still reaches the size-based branch. This is a size heuristic, not a full shared-memory object/handle association.
- `svc_unmap_shared_memory` is currently a no-op. It does not clear `HidState.shmem_va`, clear `Kernel.hid_mapped_host_ptr`, or unbind the host pointer. This is a potential stale-binding/lifetime hazard if guest code unmaps or remaps HID memory; it is not yet demonstrated to cause the Vandal Hearts issue.
- The native no-NRO process probe does not exercise the guest IPC route, so no runtime SVC 0x13 call, guest memory read, or game input has yet been observed.

The audit script fails closed if the pinned route changes and emits only a small JSON report. It deliberately reports `runtime_guest_map_call_observed=false` and `guest_read_of_npad_report_observed=false`.

## Next runtime proof

After a usable game NRO is available in the local test environment, capture only safe structured fields at the SVC boundary: caller process/PC, handle type, requested size, guest VA, mapped host-region identity, and success/failure. Then instrument a guest-side read or the exact input-consumption call to verify B press and release. Before changing production behavior, add isolated regression tests for handle validation and unmap/rebind lifecycle; do not patch the mapping semantics solely from this static audit.

This is a Draft stacked on Stage38; no change to NeXium upstream or Vandal Hearts PR #176 is made by this audit.
