# Stage32: preserve real SDL3 controller input before entering the macOS winit event loop

## Independently confirmed starting point

The [Stage31 authentic Intel CI #39587051996](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39587051996) succeeded in a repeat A/B test of the **same original Stage29 Rustarmic x86_64 executable**, SHA-256 `dcde8e712eac86966bd66b6510b5d99ab69092adbaa4c67f19a4a3172c44d89b`. It classified eight true no-NRO, audio-disabled process observations: with SDL3 InputBackend initialization in `HorizonApp::new`, constructor-only mode reproduced **2/2 SIGABRT** and the `winit` reentrant event panic; omitting the input backend produced **2/2 twelve-second surviving visible windows** for both constructor-only and the ordinary full NeXium GUI. The minimal host control also survived. The constructor completed through `12_BEFORE_RETURN` when SDL3 input was omitted.

This is strong evidence that `InputBackend::new` interferes with the macOS `winit/eframe` startup. It is **not** proof which SDL3 call, macOS event, or timing interaction causes the abort. Simply leaving input disabled is not a viable full emulator port because controller input is lost.

## Genuine controller-preserving source experiment

A pinned opt-in patch validates all three original sources before altering any, and adds `NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT=1`:

- In `nexium-gui/src/main.rs`, initialize the **real** `InputBackend::new(settings.motion_enabled, settings.gamepad.clone())` **before** invoking `eframe::run_native` on the main macOS thread.
- In `nexium-gui/src/input.rs`, hold the real `Option<InputBackend>` containing SDL3/gamepad handles in a thread-local `RefCell`, not a cross-thread unsafe global. Transfer it **once** into `HorizonApp` using `take()`.
- In `nexium-gui/src/app.rs`, the opt-in path consumes this already-created input while preserving the original constructor, all UI, Nextendo, library, guest and source order. `STAGE32_PREINPUT_CREATED_SOME` and `STAGE32_TAKE_SOME` markers are required before claiming even that SDL3 handles were retained.

If the environment variable is absent, the original `InputBackend::new` path is unchanged. Stage29's `NEXIUM_MACOS_SKIP_SDL3_INPUT=1` still supplies the independent no-controller positive control. The new experiment does **not** assert a production fix.

## Native Intel evidence

On one freshly compiled x86_64 Intel NeXium executable, five isolated no-NRO, audio-disabled controls run for at most 12s: constructor-only original input; constructor-only preinitialized real input; full HorizonApp preinitialized real input; full HorizonApp controller-disabled; host-init-only minimal interface. The audit checks same compiled executable SHA, authentic runtime branch markers, whether an actual SDL3 InputBackend was created and consumed (or not), process SIGABRT, and process-owned window existence. An abort **before** entering `winit`, or a `CREATED_NONE` result, is meaningful negative evidence and must not be reported as working controllers.

Ten fail-closed tests assert source boundaries, idempotence, unchanged original fallback, true pre-winit ordering, one-shot ownership and no partial writes on incompatible sources.

## Remaining limitations

Even creating and transferring a nonempty SDL3 controller object without an abort **would not** prove physical controller buttons, rumble, correct GUI pixels, Vandal Hearts guest execution, a finished macOS Intel NeXium application, or Nintendo Switch audio. Any candidate fix needs real input-event tests and an NRO/game test. This is a separate **Draft PR** stacked on Stage29 with NeXium main and Vandal Hearts PR #176 unchanged.
