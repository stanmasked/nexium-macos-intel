# Stage25: locate Intel macOS NeXium winit crash before/inside HorizonApp

## Grounded prerequisite

Stage22 [Actions #39511503479](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39511503479), real Intel process job 118942854116, successfully built one native Rustarmic NeXium executable and observed two actual no-NRO launches of the exact same Mach-O (SHA-256 b844f25511edd1af8f5e1c5b6316edd3e39d0abdde12cad1e8820ace4f65aa66). With host audio **disabled**, the default NeXium UI path aborted with SIGABRT while the early minimal Wgpu/eframe path stayed alive for 12 seconds. This does not prove window pixels or functional game emulation.

Stage24 [Actions #39513705196](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39513705196) independently compiled a source-unrelated eframe 0.37 control and observed 12-second process survival with Wgpu and Glow, again without proving visible pixels.

## The next isolated question

Is the macOS abort caused by **normal NeXium initialization before the eframe application constructor**, or by HorizonApp construction/use itself?

Stage25 extends ONLY the pinned Stage22 experimental checkout and adds the opt-in NEXIUM_MACOS_FULL_INIT_MINIMAL_APP=1 selector within the original eframe::run_native app-creator closure. The selector keeps settings, logging, native options, Wgpu selection and the normal eframe startup path, **but replaces only HorizonApp::new** with the existing Stage22MinimalEframe. No NRO is passed, and host/menu audio is disabled through the Stage21 guard in every variant.

One newly built native x86_64 Intel Mac NeXium Mach-O is launched in three separately isolated data roots, with the same native audio policy:

| Path | Setting | What it tests |
| --- | --- | --- |
| Original full GUI | MINIMAL_EFRAME=0, FULL_INIT_MINIMAL_APP=0 | Full host initialization plus HorizonApp creation |
| Full startup, minimal app | MINIMAL_EFRAME=0, FULL_INIT_MINIMAL_APP=1 | Full host initialization, same NativeOptions, skip HorizonApp constructor |
| Early minimal | MINIMAL_EFRAME=1, FULL_INIT_MINIMAL_APP=0 | Minimal eframe before normal settings and NeXium initialization |

The runtime emits a unique path marker for the new mode; the original Stage22 marker proves the early path. The verified receipt requires all three actual process observations from an identical SHA-256 executable, denies mixed markers and private/NRO claims, and stores only sanitized JSON receipts. Optional scoped CoreGraphics process window probe is included, but a found window is not proof of a rendered game frame.

## Interpreting actual results (not assuming them)

If full-startup/minimal-app survives while original GUI aborts, additional initialization in HorizonApp::new or its UI/update path becomes the primary next investigation; the result does **not** prove exact culprit or exclude timing effects. If full-startup/minimal-app also aborts while early-minimal survives, concentrate on settings, logger, input, initial GPU state or NativeOptions differences **before** the app constructor. If all variants abort/survive, retain raw classification and do not over-interpret a possibly intermittent hosted runner.

The source patch is idempotent, pinned to one exact upstream app-creator closure, and protected by nine synthetic positive/negative tests. Stage22 and Stage23, the NeXium main branch, and all Vandal Hearts game/audio branches are unchanged. Stage25 CI must run before any runtime conclusion is claimed.
