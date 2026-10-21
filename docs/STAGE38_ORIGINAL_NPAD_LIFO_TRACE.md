# Stage38 — original serialized NPad LIFO B press/release

## Verified prior stages

[Stage36](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39605034642) succeeded on native Intel macOS: the original SDL3 virtual SOUTH button was sent pressed and released, and both transitions were read through the actual original `InputSnapshot`. The pinned default mapping translates SDL SOUTH to Nintendo Switch B.

Stage37 instruments the unchanged original `HorizonApp` boundary after `hid.update_input(ControllerInput)`; it accepts a synthetic B press only when both original `gp_buttons` and actual post-update `hid.input.buttons` contain the B bit, and release only when both clear after a confirmed down. Its source is double-opt-in, macOS-only, and remains a separate Draft on the Stage36 branch.

## Stage38 next boundary

The pinned upstream `nexium-kernel/src/hid_state.rs` already has an opt-in `NEXIUM_HID_TRACE=1` trace. Its original `trace_published_input` reads each layout's latest serialized button word back from the real internal `HidState.buf` NPad LIFO after `tick_with_source` writes it. It emits a `[hid-publish]` line with `npad=[...]` values. The bit for Switch B is `1 << 1`. No source patch to kernel HID serialization is needed.

Stage38 sets this existing diagnostic env flag only for the three native no-NRO controls. A local audit script reads the raw logs locally and outputs **only sanitized booleans/counts**. It requires the full virtual process to show:
- original Stage36 synthetic snapshot press and release markers;
- original Stage37 host HID B press and release markers;
- an actual serialized NPad LIFO sample with B set, followed by a later actual sample with B clear.

The full GUI without virtual input must show no synthetic B press; the inert constructor must not poll or publish a B sample. All three process receipts must use the same actual x86_64 Mach-O. Raw logs, button arrays, pointers, and private console text are never included in uploaded artifacts.

## What a positive result means

A positive Stage38 result proves the synthetic Switch B transition was serialized into NeXium's **host-side internal NPad LIFO buffer** and cleared afterward. It does not prove that guest NPad shared memory was mapped, that guest code read the report, that a game NRO received it, that Vandal Hearts is playable, or that a physical controller/console audio works. The Stage39 source audit now confirms a production path in `nexium-kernel/src/kernel/svc.rs`: HID cmd 0 routes to `IAppletResource`, its cmd 0 returns a SharedMemory-typed handle, and `svcMapSharedMemory` sets `HidState.shmem_va` and binds the original HID buffer when `size == HID_SHMEM_SIZE`. However, that mapping is size-based and does not validate the handle; `svcUnmapSharedMemory` is currently a no-op. Stage39 documents these source findings without claiming that a guest process has exercised the path.

This is a Draft stacked on Stage37; NeXium main and Vandal Hearts PR #176 remain untouched.
