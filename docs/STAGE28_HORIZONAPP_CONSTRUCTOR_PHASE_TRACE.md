# Stage28 — narrow down the native Intel HorizonApp constructor abort

## Authoritative result

The genuine Intel macOS [Stage26 Actions #39518341145](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39518341145), job `118964479702`, compiled a real native Rustarmic Mach-O, SHA-256 `9a4aed6e04f2c2cdd3f318cb73070badb342be67b6d5ce2cedcb02f7f5c03780`. On this identical executable with host audio disabled and no NRO:

- The full NeXium GUI aborted `SIGABRT`, winit reentrant event handler panic.
- Constructor-only mode entered the **actual** `HorizonApp::new`, aborted `SIGABRT` after about 0.7 seconds, and **did not reach** `STAGE26_HORIZON_CTOR_RETURNED`. Original normal `HorizonApp::ui` did not run.
- Full original host startup with minimal app replacing `HorizonApp` survived twelve seconds and owned a visible window.
- Early minimal eframe survived twelve seconds and owned a visible window.

Its final job result was failure **because the original verifier required the constructor to return**, not because no real process test ran. All four original process receipts remain in artifact `12310683980`. This establishes that the constructor path aborts before returning, but not which internal call causes it.

## New strictly opt-in original constructor phase trace

This stacked experimental patch adds **only static eprintln checkpoint markers** around a pinned section of `nexium-gui/src/app.rs`, guarded by the environment variable `NEXIUM_MACOS_CONSTRUCTOR_PHASE_TRACE=1` and macOS-only compilation. Nothing in the original constructor is suppressed, re-ordered or replaced.

Thirteen checkpoints separate theme setup, UI audio initialization, SDL3 gamepad backend initialization, Nextendo startup, construction of the app state, profile texture setup, UI audio setup, and library rescan. No user data, home paths, content paths or NROs appear in the marker text. Nine synthetic tests reject source drift, ambiguous anchors, reordered phases and partial edits.

A new native Intel CI job launches **the same freshly compiled Mach-O** three times: full HorizonApp, constructor-only under inert UI, and the full-host/no-constructor negative control. All variants disable host audio and supply no NRO. A final **fail-closed** classifier accepts a real SIGABRT as a diagnostic result, checks unique mode markers and hash equality, and records only the last **actually observed** constructor checkpoint. Critically, unlike Stage26 it does not require the constructor return marker in an authentic crash. It does require reaching the entry marker in constructor-only mode.

If a precise internal call is identified, the next separate fix should isolate or defer that operation, rather than adding broad macOS workarounds speculatively. Checkpoints alone do not establish causation: their timing may influence races. Any hypothesis must be retested against independent original controls.

## Boundaries

This is a separate Draft experiment stacked on Stage26, not merged into NeXium main or Vandal Hearts PR #176. It does not prove normal GUI functionality, pixel correctness, game emulation, NRO boot, physical Switch speaker audio or resolve historical `0xEA01`. Its CI must actually run before any new phase result is asserted.
