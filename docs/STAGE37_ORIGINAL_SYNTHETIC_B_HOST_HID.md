# Stage37 — original SDL3 SOUTH → Switch B → host `HidState.update_input` boundary

## Verified prerequisite

[Stage36 native Intel CI #39605034642](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39605034642) **SUCCESS** with original Rustarmic NeXium x86_64 Mach-O SHA-256 `a88c508512f01e3cb236c43928bd2bdc2dcc780dea07f448401a2503f4a443aa` and genuine three-process source-bound artifact #12350042134. In the full original NeXium GUI with the genuine SDL3 InputBackend initialized before `winit`, a **purely synthetic virtual in-process SDL3 SOUTH button** was attached, sent pressed and released, and both transitions were read through original `InputBackend::poll` and `InputSnapshot`, with `virtual_input_round_trip_positive: true`. The no-virtual full GUI and inert-constructor virtual controls emitted no false mapped button events.

Pinned source `nexium-gui/src/controller_config.rs` maps `GpButton::South` to `SwitchButton::B` by default (Switch A maps to SDL EAST), so the host event is **synthetic Switch B**. Stage36 alone does **not** prove that `HorizonApp` forwards B to host HID state, that guest Switch NPad shared memory is mapped, that a real USB/Bluetooth pad works or that a Nintendo game is running.

## Stage37 original host HID boundary

Pinned upstream `nexium-gui/src/app.rs` calls `self.last_input.to_npad()` after `InputBackend::poll`, merges controller and keyboard input, then obtains `nexium_core::hid_state::get_hid_state()`, locks it and calls the real `hid.update_input(nexium_core::hid_state::ControllerInput { buttons, ... })`. Pinned `nexium-kernel/src/hid_state.rs` confirms `HidState.input` and `shmem_va` are public and `update_input` updates host HID state. The synthetic original `InputSnapshot` state must therefore reach this **host HID** path before guest delivery can be evaluated.

Stage37 adds **opt-in marker-only** source checks **immediately after the original** `hid.update_input`, enabled exclusively with `NEXIUM_MACOS_STAGE37_HID_BRIDGE_TRACE=1` **and** `NEXIUM_MACOS_VIRTUAL_BUTTON_TEST=1` on macOS. Original `InputSnapshot.to_npad`, controller mapping, keyboard merge, `ControllerInput`, `hid.update_input`, polling and guest HID functions are **not changed**.

On genuine synthetic B down, the marker is emitted only if BOTH the original gamepad `gp_buttons` contains `SwitchButton::B.npad_bit()` AND actual post-update `hid.input.buttons` contains the same bit. The release marker is emitted only after both return to zero following a previously confirmed down. An explicit marker distinguishes no guest NPad shared memory (`hid.shmem_va.is_none()`) from a mapping being present **but unverified**. No numerical controller state, paths, raw events, serial numbers or logs are uploaded.

CI builds one authentic x86_64 NeXium Rustarmic binary and runs the same three real no-NRO/audioless controls: full normal GUI with synthetic virtual SOUTH; full normal GUI with no virtual pad; inert constructor with a synthetic pad. All must use the same executable SHA. Only the virtual full GUI may emit host HID press/release. Eleven synthetic source-bound tests fail closed on anchor drift, original function deletion, changed Switch button, premature positive claims and non-idempotence.

## Strict interpretation

A positive `source_bound_synthetic_switch_b_host_hid_round_trip_positive` would establish **host** `HidState.input` press and release from a virtual synthetic SDL3 SOUTH button. It would **not** establish guest NPad shared-memory mapping, actual game/NRO consumption, playing Vandal Hearts, correct rendered game frames, a physical Bluetooth/USB controller, rumble or speaker sound. Those are separate milestones requiring actual guest/game evidence. If the host state is not reached, Stage37 records the missing markers and reports `false` rather than filling gaps.

This is a separate Draft stacked on Stage36. NeXium main, original Vandal Hearts PR #176, and already verified SDL2 music NRO workflow fix in Vandal Hearts Draft PR #416 remain untouched.
