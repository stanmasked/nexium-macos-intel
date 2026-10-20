# Stage26 — does HorizonApp construction or its first UI frame trigger the macOS crash?

## Authoritative earlier result

Native Intel macOS Stage25 [Actions #39514962640](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39514962640) job 118953692601 built a real Rustarmic NeXium Mach-O (SHA-256 38f66e29623995835af8f35409d802e929e084774e40727223de7b3bf9f5e5ad). All three no-NRO and audio-disabled processes ran on this **same binary**:

- Original full HorizonApp exited SIGABRT before 12 seconds.
- All normal host initialization, but minimal eframe app substituted instead of HorizonApp::new, survived 12 seconds and owned an observable CoreGraphics window.
- Early minimal eframe survived 12 seconds and owned an observable CoreGraphics window.

That is a reproducible difference at/after the HorizonApp application creation point, **not** yet proof whether its constructor or its first eframe App lifecycle/UI caused the crash. No video/frame pixel or game was verified.

## Stage26 single-binary four-path experiment

The new opt-in NEXIUM_MACOS_HORIZON_CTOR_ONLY=1 path (macOS only) runs the **actual pinned HorizonApp::new** and then retains its resulting instance in Stage26HorizonCtorOnly, a small eframe::App wrapper whose ui() draws a minimal label instead of invoking original HorizonApp::ui/logic.

To avoid an invalid experiment, the original constructed HorizonApp is **kept alive** inside the wrapper for the whole eframe process, rather than immediately dropped; all guest/game inputs stay absent. The wrapper emits separate constructor entry/return markers, so a crash *inside* the constructor will be distinguished from one *after* constructor return.

Four genuine Intel x86_64 processes use the same freshly compiled Mach-O and host audio disabled, each launched for at most 12 seconds:

| Runtime mode | Original host settings/options | Original HorizonApp constructor | Original HorizonApp UI |
| --- | --- | --- | --- |
| Full original | Yes | Yes | Yes |
| Constructor-only | Yes | Yes | No, minimal wrapper UI |
| Full-init minimal | Yes | No | No |
| Early minimal | No | No | No |

Acceptance requires an actual process receipt for all four, original constructor entry and return markers in constructor-only, other modes' expected markers, identical Mach-O SHA-256, and no mixed branch markers or NRO/game assertions. Best-effort CoreGraphics may detect a process-owned visible window. This is distinct from verifying nonblank frame pixels.

## Interpretation and limitations

- If constructor-only also aborts before its return marker, focus on the constructor's side effects: UI audio, SDL3 input, Nextendo::start, library scanning, and other creation-time tasks.
- If constructor-only reaches its return marker but aborts soon after, investigate background threads or callback lifetimes created by HorizonApp::new.
- If constructor-only survives but the full original App aborts, focus on original HorizonApp::ui/logic and its window/event-loop callbacks on the first frames; this is a strong narrowing but no single source-level culprit has been proven.
- If original full and constructor-only both survive, original Stage25 behavior may be intermittent: repeat with reproducible isolated native sessions rather than prematurely claiming a fix.

Only a separate **Draft PR**, stacked on Stage25; default NeXium, Stage22/23, Vandal Hearts PS1 content and all Switch audio/main PR work are left untouched. Nine source-safe tests plus live macOS CI check the implementation. Do not claim any results until the real four-process native job reports them.
