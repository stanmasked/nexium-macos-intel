# Stage31: repeat the original Intel NeXium SDL3 ablation without recompiling

## Original observations

[Stage30 successful Intel CI #39561538680](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39561538680) independently replayed the exact Stage28 Mach-O (SHA-256 `345bb6188e3e5956018605d994e245550f660832fd240587fce6ac292ce59049`). Both full and constructor-only GUI paths aborted with SIGABRT and emitted the constructor phase sequence `00_BEFORE_THEME`, `02_AFTER_UI_AUDIO`, `03_BEFORE_INPUT`; `01_BEFORE_UI_AUDIO` was absent because Stage21's audio bypass replaces that source statement. No `04_AFTER_INPUT` was observed. The full-host/no-HorizonApp control survived 12 seconds. The exact responsible native input call remains a *hypothesis*.

[Stage29 original Intel CI #39559370735](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39559370735) built a real NeXium Rustarmic x86_64 executable with SHA-256 `dcde8e712eac86966bd66b6510b5d99ab69092adbaa4c67f19a4a3172c44d89b`, then tested 4 modes with no NRO and host/UI audio bypassed:

| Mode | Original run |
| --- | --- |
| Constructor-only, SDL3 initialized | SIGABRT |
| Constructor-only, SDL3 skipped | Survived 12s, process-owned window |
| Original full GUI, SDL3 skipped | Survived 12s, process-owned window |
| Normal host init, no HorizonApp | Survived 12s, process-owned window |

**Stage29's final job FAILED** because it incorrectly required the Stage26 `HORIZON_CTOR_ENTERED` wrapper marker in the normal full-GUI mode, where that wrapper is not used. The four genuine original process receipts still exist in artifact #12328406684. This is not a production SDL3 fix.

## Stage31 independent repeat

Stage31 downloads the already-built original Stage29 binary **without changing any NeXium source**, asserts real `macos-15-intel`, x86_64 Mach-O and exact SHA-256, and performs two independent launches for each of the four modes (eight original process receipts).

The new audit distinguishes the normal GUI path (which must **not** show the Stage26 wrapper marker) from the constructor-only path, requires correct Stage29 SDL3 branch emissions on surviving paths, checks the same original binary in all eight sessions, and keeps phase markers in their actual emission order without filling gaps. A second identical result would increase confidence that bypassing the SDL3 input constructor makes the Intel GUI process survive, but **would not prove the underlying Apple event-loop/Sdl3 source cause**: the change may alter startup timing or device enumeration. Eleven synthetic source/audit tests defend against forged receipts, irrelevant windows, mixed binaries and false gameplay/NRO claims.

Original console logs and window screenshots stay private in the disposable runner; GitHub artifacts contain only sanitized guest-process status and whitelisted marker names.

## Limitations and next technical choice

An experimental macOS port that permanently disables SDL3 controllers loses controller input and cannot qualify as a complete NeXium release. Once the independent result is established, the next targeted investigation should consider moving SDL3 controller setup outside winit's recursive App lifecycle and/or initializing it lazily with a reentrancy-safe dispatch. Any future fix must also prove working controller input, real GUI frames and game boot. Until then, no native Switch sound, Vandal Hearts gameplay, NRO, or complete Mac port is claimed.

This is a separate Draft PR stacked on Stage29, with no changes to NeXium main, Vandal Hearts PR #176 or its unchanged game/audio assets.
