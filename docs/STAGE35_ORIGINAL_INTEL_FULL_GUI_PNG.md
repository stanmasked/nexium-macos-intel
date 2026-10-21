# Stage35 — full original Intel NeXium GUI window-specific PNG evidence

## Verified original build reused unchanged

The original authentic [Stage32 Intel NeXium Actions #39588444239](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39588444239), run artifact `nexium-macos-intel-rustarmic-probe` #12342108781, contains a genuine Rustarmic x86_64 NeXium executable with exact SHA-256 `4d40b18bb52b5a498f0efb1d00812643bc4062e18c6e27a4d2af6b208787be93`. The Stage32 five-mode process classifier separately proved that when SDL3's actual `InputBackend` was constructed on the main Intel macOS thread before `eframe::run_native` and transferred once into `HorizonApp`, the ordinary full GUI stayed alive for 12s and owned a visible window. That evidence did **not** include PNG image bytes from the ordinary NeXium window.

Stage27 previously captured PNGs only of a **minimal eframe** window. Thus process survival and an OS window ID must not be mistaken for a correctly drawn full NeXium user interface.

## Source-bound no-recompile experiment

This independent Draft downloads **only the exact original Stage32 executable** from its original GitHub Actions run and checks x86_64 architecture and SHA-256 before running.

Two independent no-NRO and audio-disabled process modes are run on a genuine macOS Intel runner from separate temporary home directories:

1. **Full normal `HorizonApp` GUI** with the real SDL3 InputBackend initialized before `winit`, without skipping input.
2. **Early minimal eframe** negative UI control without original HorizonApp.

For each mode, the existing `capture_macos_window.py` helper first verifies its *own spawned process PID* is a running `nexium`, discovers only the CoreGraphics window owned by that PID, and executes window-specific `screencapture -l WINDOW_ID`. It **never takes a desktop screenshot or another application's window**. All raw PNGs and stdout/stderr remain solely inside a Python TemporaryDirectory and are deleted before publishing. Exactly **nine synthetic tests** check pinned binary provenance, privacy, missing/invalid screenshots, SHA digest reporting, true source modes and zero unsupported game/audio/controller claims.

The only uploaded JSON contains exact original binary hash, per-mode process state, number of successful window-specific PNGs, each image's dimensions/byte count/SHA-256 and whether full GUI and minimal screenshots differ by hash. If Screen Recording permission is denied, the correct outcome is `no_window_png`, not a fabricated screenshot. Even if hashes differ, **this cannot prove the full GUI's widgets were drawn correctly**; image contents remain uninspected. The experiment does not upload screenshots to a public repository.

## Limits and relation to other diagnostics

Stage34 is separately building a fresh Intel NeXium with one-time `InputBackend::poll` source markers to determine whether the real input event pump and gamepad subsystem update are called after pre-winit controller setup. The two experiments are independent and should not cancel one another.

Neither real process/window screenshot nor polling source markers certify a physical controller button press, Nintendo Switch NRO loading, Vandal Hearts gameplay, rendered in-game frames, correct sound samples or actual physical speaker output.

No source code changes are made to the upstream emulator or the main Vandal Hearts PR #176. Stage402's already successful original and independent SDL2 Switch NRO workflows in game Draft PR #416 remain untouched.
