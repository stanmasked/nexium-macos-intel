# Stage29 — SDL3 InputBackend constructor ablation on native Intel Mac

## What is already independently established

[Stage26 native Intel Actions #39518341145](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39518341145) proves that NeXium's normal `HorizonApp::new` path aborts with winit `SIGABRT` **before the constructor returns**, even when the original `HorizonApp::ui` implementation is suppressed. Full host startup and the early eframe control without `HorizonApp` both survive 12 seconds with process-owned visible windows.

The established `NEXIUM_MACOS_NO_AUDIO=1` guard already suppresses *both* host and UI audio initialization; duplicating an audio ablation would not supply new causal evidence. One remaining plausible initializer is `InputBackend::new`, which initializes SDL3 controllers from inside `HorizonApp::new`. This is a hypothesis, **not an identified root cause**.

## Exact experiment

This Draft is stacked on the Stage28 phase-instrumentation branch and adds a **single separately controlled** environment variable `NEXIUM_MACOS_SKIP_SDL3_INPUT=1`. In the pinned `nexium-gui/src/app.rs` constructor this replaces only the `InputBackend::new(...).or_else(...)` expression with `None`; the original expression is still taken when the variable is absent or zero. All other constructor statements (including Nextendo startup, native presentation, library scanning, settings and UI state) are unchanged. Stage28's phase markers remain in place.

One fresh native Intel x86_64 NeXium Mach-O is launched four times, **with no NRO and both UI/host audio disabled in all cases**:

| Variant | Real HorizonApp constructor | SDL3 InputBackend::new | Original HorizonApp UI |
| --- | --- | --- | --- |
| Constructor-only, SDL3 enabled | Yes | Yes | No |
| Constructor-only, SDL3 skipped | Yes | No | No |
| Full HorizonApp, SDL3 skipped | Yes | No | Yes (only if constructor returns) |
| Full host startup / minimal app | No | No | No |

Checks require all four authentic no-NRO process receipts, unique matching Mach-O SHA-256, constructor-entry/return markers, explicit SDL3 branch markers **if the execution reaches that decision**, and an independent no-constructor negative control. A crash before the new marker remains an honest partial observation and must not be reported as a successful ablation. The failure-aware classifier does **not** demand that a constructor return after an authentic SIGABRT.

Ten source regression tests assert the original path is present, the flag is macOS-scoped, constructor statements outside SDL3 are preserved, source drift/duplicates are rejected, and re-application is idempotent.

## Limits

Process survival or even a process-owned visible window is not proof of rendered correct NeXium GUI, NRO, gameplay or sound. Even if skipping input prevents SIGABRT, it might alter timing or events; it is not proof that SDL3 is the sole cause. The experiment must be replicated and tightened before proposing a production fix.

This is separate from active Stage28 CI, and no changes are made to Vandal Hearts main Draft PR #176, NeXium main or the original archived Intel/guest observations.
