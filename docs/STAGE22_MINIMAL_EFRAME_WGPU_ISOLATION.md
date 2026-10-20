# NeXium Intel/macOS Stage22 — isolate minimal eframe/Wgpu GUI startup

## Why

Original [Stage21 Intel A/B Actions run #39506855929](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39506855929) compiled a genuine x86_64 Rustarmic NeXium binary, then launched that single binary on a hosted Intel Mac twice with and without host/menu audio initialization. **Both original no-NRO process launches aborted via SIGABRT** with winit's message `tried to handle event while another event is currently being handled`. With audio enabled CPAL also reported underruns; **disabling audio did not eliminate the panic**. Successful build/CI comparison alone is not an operational GUI.

## Stage22 controlled experiment

A new guarded local source patch applies only during the separate Intel experimental build (`NEXIUM_EXPERIMENT_MINIMAL_EFRAME=1`). It adds a Rust `eframe::App` with a single egui panel. When and only when the compiled macOS binary is invoked with `NEXIUM_MACOS_MINIMAL_EFRAME=1`, it returns early into `eframe::run_native` with **Wgpu and the same host Wgpu setup** as normal startup, before ordinary settings, host audio, file logger, NRO loader and `HorizonApp` initialization. Default application behavior remains unchanged.

A single freshly built Intel Mach-O is launched twice in isolated NeXium data roots:

| Variant | Environment | Expected path |
| --- | --- | --- |
| Full emulator GUI (no audio, no NRO) | `NEXIUM_MACOS_NO_AUDIO=1 NEXIUM_MACOS_MINIMAL_EFRAME=0` | Original HorizonApp initialization and eframe/Wgpu path |
| Minimal eframe/Wgpu (no audio, no NRO) | `NEXIUM_MACOS_NO_AUDIO=1 NEXIUM_MACOS_MINIMAL_EFRAME=1` | Bypasses emulator/GUI-app initialization but retains eframe/Wgpu |

The runtime prints `STAGE22_MINIMAL_EFRAME_ENTERED` before its native window attempt. The classifier fails closed if this marker is absent, if reports are missing, if executables differ by SHA-256, or if the test incorrectly claims to execute an NRO.

A nonzero exit or SIGABRT is **captured as a real failure observation**, not hidden and not mislabeled as GUI success. Process survival would **not** establish actual window drawing without separate validated window evidence.

## Interpreting the outcomes

- If **both variants crash**, the failure persists in basic eframe/Wgpu initialization or the hosted AppKit environment, and cannot be attributed solely to `HorizonApp`/audio.
- If **the minimal variant survives** but full NeXium still aborts, focus on the extra emulator/UI/app startup path; survival alone does not prove a visible window.
- If **both survive**, add verified window/renderer checks and only then a local no-private-assets NRO smoke experiment.
- If the patch cannot build, label it **experimental compilation failure**, not an emulator or music regression.

The patch is anchored to the pinned NeXium source, idempotent, and covered by seven synthetic positive/negative tests. No upstream checkout is published, no game assets or keys are uploaded, and no release/physical Nintendo Switch behavior is claimed.
