# Stage33 — seven internal SDL3 InputBackend construction checkpoints (Intel macOS)

## Evidence and remaining unknown

The [Stage31 authentic native Intel CI #39587051996](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39587051996) successfully replayed **eight** original no-NRO, audio-disabled GUI processes on the unchanged Stage29 Rustarmic Intel NeXium Mach-O. In both runs with SDL3 controller initialization enabled **inside** `HorizonApp::new`, the constructor aborted with the `winit` event-reentrancy panic and last outer checkpoint `03_BEFORE_INPUT`. Bypassing only `InputBackend::new` allowed full original HorizonApp and inert-UI variants to complete and retain visible windows in 2/2 runs each. See original sanitized source-bound receipt artifact #12339936797.

This reproducibly implicates the **initialization path**, but does not show whether macOS reentrant processing arises while setting SDL hints, in `sdl3::init`, initializing the gamepad subsystem, creating rumble support, or a different SDL3 side effect. Simply disabling input is not a working emulator port.

## Stage33 marker-only experiment

This **separate Draft** is based on Stage29 rather than altering/cancelling Stage32's independent pre-winit preservation experiment. A pinned opt-in patch to `nexium-gui/src/input.rs` adds macOS-only static messages, enabled with `NEXIUM_MACOS_SDL3_SUBCALL_TRACE=1`, at seven originally ordered positions:

| Marker | Original operation at/after boundary |
| --- | --- |
| 00_BEFORE_HINTS | Before setting SDL joystick hints |
| 01_AFTER_HINTS | After hint writes, before hint reads |
| 02_BEFORE_SDL_INIT | Before `sdl3::init()` |
| 03_AFTER_SDL_INIT | After SDL context initialization, before `sdl.gamepad()` |
| 04_AFTER_GAMEPAD | After gamepad subsystem creation, before rumble |
| 05_AFTER_RUMBLE | After rumble creation, before logging |
| 06_BEFORE_RETURN | Before returning actual SDL3 InputBackend |

**No original SDL3 statement is moved, disabled, replaced or given a fallback.** A trace's last emitted marker is diagnostic location evidence, not proof the following expression is itself the unique root cause. A Rust panic, process signal, truncated stderr buffer or emitted-message timing can create gaps.

Native Intel CI builds one x86_64 executable and launches it in three authenticated no-NRO, audio-disabled modes: actual `HorizonApp::new` with SDL3 enabled in inert-UI wrapper, original full GUI with SDL3 enabled, and the original constructor with Stage29 SDL3 skip control. The comparison requires original process receipts, exact same binary SHA-256, correct entry/skip markers, chronological emitted phase identifiers, and original `SIGABRT`/window observations. It uploads **only** source-bound phase identifiers and sanitized process metadata, not private stdout or game files. Ten fail-closed source tests preserve original subcall order, idempotence and strict pinned anchoring.

## What still needs proof

Stage33's own native CI must finish before interpreting any internal SDL3 marker. Separate [Stage32 Draft PR #22](https://github.com/stanmasked/nexium-macos-intel/pull/22) is testing whether real InputBackend can be created before entering `winit` and then handed to `HorizonApp` without disabling controller support. Neither experiment alone proves actual gamepad button input, working GUI pixels, guest game/NRO boot, Switch audio or a finished Intel Mac release.

NeXium main and Vandal Hearts game PR #176 are unchanged.
