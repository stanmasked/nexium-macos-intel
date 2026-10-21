# Stage34 — does the preserved real SDL3 input backend actually reach its GUI poll?

## Authoritative starting results

[Native Intel macOS Stage32 CI #39588444239](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39588444239) is **successful**. Five authentic no-NRO, audio-disabled processes shared one x86_64 Rustarmic NeXium executable SHA-256 `4d40b18bb52b5a498f0efb1d00812643bc4062e18c6e27a4d2af6b208787be93`:

- With ordinary `InputBackend::new` inside `HorizonApp::new`: SIGABRT and winit event reentrancy.
- With `InputBackend::new` **before** entering `eframe::run_native`, retained once through main-thread thread-local and transferred into the original `HorizonApp`: both the full GUI and constructor-only inert-UI paths **survived 12 seconds** with process-owned windows, confirmed `STAGE32_PREINPUT_CREATED_SOME` **and** `STAGE32_TAKE_SOME`.
- Full GUI without input and full-host/minimal controls: also survived 12 seconds.
- Original artifact `nexium-intel-stage32-sdl3-prewinit-controls` **#12343040608**.

In independent [Stage33 Intel CI #39590021225](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39590021225), both original SDL3 enabled startup modes crashed after `03_AFTER_SDL_INIT` and before `04_AFTER_GAMEPAD`, implicating the `sdl.gamepad()` subsystem transition. This location is not proof which SDL3/macOS OS callback is causal.

## New check: actual original input poll calls, not a surrogate

The original `nexium-gui/src/app.rs` calls `ib.poll(...)` when `self.input` exists and its real full UI logic runs. Original `InputBackend::poll` calls `self.sdl.event_pump()`, `ep.pump_events()`, `self.gamepad.update()`, `self.ensure_pad()` and additional motion/rumble steps.

Stage34 uses a **strictly opt-in macOS-only marker patch** to place three one-time `AtomicBool`-guarded IDs at original source boundaries: method entry, after original SDL event pump, and after original gamepad update. No original event code is replaced, no extra controller event is synthesized, and no private device name, button value, joystick ID, gamepad serial, file path or screenshot is logged. Ten fail-closed source tests require original polling operations and exact ordering.

One freshly built native Intel Rustarmic executable is run as **four** no-NRO/no-audio controls for 16 seconds each: full original HorizonApp with genuine SDL3 pre-winit input, constructor-only pre-winit input under inert UI, full original HorizonApp with no input, and original unmodified constructor path which historically SIGABRTs. The verifier checks source-branch markers, same exact Mach-O SHA, original process receipts and the actual emitted one-time polling phase IDs in order. Inert UI and no-input controls **must not** poll.

Stage34 distinguishes success in creating/retaining an SDL3 context (already proved by Stage32) from actually executing the original event pump and gamepad update in a real full NeXium GUI process. A missing poll marker would remain negative evidence, not be guessed or relabeled as executed. Even observed polling **does not** prove actual hardware controller button input or rumble, because CI has no trusted user gamepad connected.

No Nintendo ROM, Switch NRO or gameplay is supplied, no frame pixels or audio sample playback are certified. This separate stacked Draft changes only the experimental Intel NeXium branch. NeXium main and Vandal Hearts PR #176, its soundtrack assets, SDL2 NRO and Stage402 CI fix are untouched.
