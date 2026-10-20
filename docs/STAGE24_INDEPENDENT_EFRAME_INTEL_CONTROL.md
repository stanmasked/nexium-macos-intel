# Stage24 — independent Intel Mac eframe 0.37 renderer control

## Hypothesis

The original Stage21 Intel NeXium experiment ([Actions #39506855929](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39506855929)) compiled a real x86_64 NeXium binary, but its GUI exited SIGABRT with winit's "tried to handle event while another event is currently being handled" **with and without audio initialization**. Stage22 and Stage23 separately isolate NeXium GUI initialization and its native renderer.

Stage24 asks whether an extremely small eframe 0.37 GUI **with no NeXium dependencies** also aborts on the same class of hosted Intel macOS runner.

## Reproducible independent control

The Rust crate in probes/standalone-eframe-intel depends only on the same eframe/egui **minor version** used by pinned NeXium GUI. It contains no NeXium source, Nintendo content, keys, NRO, firmware or ROM. A *single native Intel Mach-O* is built in a fresh GitHub Actions job. Two sequential processes use that same binary, changing only STAGE24_RENDERER between wgpu (Wgpu/Metal) and glow (OpenGL).

The code uses the eframe 0.37 App::ui trait form. The workflow verifies true Intel x86_64 hardware, runs nine synthetic fail-closed report tests, builds with macOS minimum target 10.15, and records a process result for each renderer.

Each result records actual process outcome and SIGABRT status, whether the winit panic was observed, a source marker emitted by the binary, and the binary SHA-256. Final source-bound comparison rejects mismatched binary hashes, swapped/missing renderer markers, missing genuine process observations, and assertions of emulator or window-pixel success.

**Critical boundaries:** An eframe process surviving for 12 seconds is **not** evidence of window rendering. This test does not launch NeXium, a game or Nintendo Switch, verify a presented frame, nor fix the original crash. A control SIGABRT is recorded as a failure observation rather than suppressed.

## Interpreting paired outcomes

If both independent eframe renderers also abort with the same reentrant-event panic, investigate common macOS AppKit/winit initialization and hosted runner restrictions. If standalone eframe survives but Stage22/23 NeXium minimal mode fails, investigate the NeXium build environment, linking, inherited host options and source patches. If only Wgpu aborts, focus on Metal/Wgpu surface lifecycle while separately checking GL's actual window visibility.

Stage24 has its **own workflow and branch from NeXium main** to avoid running, cancelling or modifying Stage22/23. Results should not be described as confirmed until the actual native Intel workflow reports.
