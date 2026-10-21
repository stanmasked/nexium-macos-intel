# Stage36 — original SDL3 virtual gamepad through the original `InputSnapshot` (Intel macOS)

## Prior verified source-bound evidence

[Stage34 actual native macOS Intel CI #39594654633](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39594654633) finished SUCCESS, with a genuine original Rustarmic NeXium x86_64 Mach-O SHA-256 `eb8306844ca3ac955c3c92d13b28f42161fcf1568b0f95d4327e4436f19b58e2` and four no-NRO/no-audio startup variants. **The full original HorizonApp with a real pre-winit-initialized SDL3 InputBackend** stayed alive with its own visible window and emitted the original `InputBackend::poll` method-entry, SDL event pump and gamepad-update source checkpoints. The original inside-winit SDL3 initializer still produced SIGABRT. Inert UI and no-input negative controls emitted no polling markers. Genuine source-bound receipt artifact #12345236161.

[Stage35 native Intel Actions #39595973101](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39595973101) independently captured four original PID-scoped full GUI PNGs of 1392×860, all with different SHA-256 hashes, from the unchanged Stage32 Intel binary, versus four identical 832×620 minimal-control PNGs. Raw images deleted; no pixel correctness claim. Artifact #12344017845.

These results show initialization, original SDL3 polling and OS window acquisition. They **do not** verify any button press or guest Nintendo game event.

## Official SDL3 facility

SDL3 exposes a [virtual joystick API](https://wiki.libsdl.org/SDL3/SDL_AttachVirtualJoystick) for tests without physical hardware. `SDL_AttachVirtualJoystick` installs an in-process device and `SDL_SetJoystickVirtualButton` supplies program-controlled pressed/released states that are applied upon SDL event/joystick updating. This is synthetic input, **not a real controller**.

## Stage36 experiment

A pinned, fail-closed, default-disabled source patch is applied only when `NEXIUM_EXPERIMENT_VIRTUAL_INPUT_SNAPSHOT=1` at experimental build time. Its runtime path requires `NEXIUM_MACOS_VIRTUAL_BUTTON_TEST=1` on native macOS; normal startup leaves the original input code unchanged.

1. Inside the genuine pre-winit `InputBackend::new`, after successful original `sdl.gamepad()` initialization, attach one synthetic SDL3 virtual gamepad (no real device name/identifier is logged). Hold the joystick pointer on the same macOS main thread for the bounded process.
2. Inside the **real original** `InputBackend::poll`, send one programmed synthetic SOUTH button down followed by up. Keep `self.sdl.event_pump()`, `ep.pump_events()`, `self.gamepad.update()`, `self.ensure_pad()` and existing `ControllerConfig::gamepad_pressed()` unchanged.
3. Emit only whitelisted status milestones if the original `InputSnapshot` actually reports a connected pad, a nonzero mapped button during the synthetic press, and a return to zero after release. **Never** synthesize or assign `snap.buttons` or publish raw button/device data.
4. Execute three isolated genuine native Intel GUI processes from **the same freshly compiled NeXium Mach-O**: full UI with synthetic pad, full UI without synthetic pad, and constructor-only inert UI with synthetic pad. The inert wrapper must not poll; the no-synthetic control must emit no synthetic markers. Both controls still initialize the genuine SDL3 `InputBackend` before entering `winit`.

Ten source-bound tests reject drift, missing original SDL operations, source duplicates, partial patches and unsafe evidence claims. The authenticated native CI audit records only actual emitted source-marker names, process survival/abort, original executable SHA-256 and whether press/release mapping occurred. An absent press/release marker is an **unverified** outcome, not a claimed success. Raw logs and any private identifiers are not uploaded.

## Limits

Even a positive result would establish **only a program-generated virtual SDL3 press/release passing through the original input snapshot**. It cannot verify external USB/Bluetooth controllers, actual macOS hardware events, joystick HID transport, rumble output, NeXium guest HID state delivery, Vandal Hearts NRO/gameplay, GUI visual correctness or physical Nintendo Switch audio.

The branch remains a separate Draft stacked over Stage34; no changes to NeXium main or Vandal Hearts PR #176. The separate Stage402 official SDL2 Switch NRO compiler fix in Vandal Hearts Draft PR #416 remains untouched.
