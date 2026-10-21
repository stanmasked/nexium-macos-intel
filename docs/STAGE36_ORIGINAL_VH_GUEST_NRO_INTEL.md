# Stage36 — run the original Vandal Hearts homebrew diagnostic NRO in genuine Intel NeXium

## Immutable provenance from already successful GitHub Actions

The original Vandal Hearts Switch repository [Stage371 CI #39501847103](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39501847103) compiled a **homebrew diagnostic libnx NRO** without SDL2, named `vandal-hearts-prototype.nro`, original size **299,064 bytes** and SHA-256 `cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b`, artifact `stage371-same-run-nro` **#12309987121**. That diagnostic was independently executed in NeXium on Linux with two source-bound audout service exits and original guest data receipts. It is **not** the full Vandal Hearts game, not a commercial ROM and not a music/gameplay fidelity proof.

[Successful Intel macOS Stage32 CI #39588444239](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39588444239) produced an authentic NeXium Rustarmic x86_64 Mach-O SHA-256 `4d40b18bb52b5a498f0efb1d00812643bc4062e18c6e27a4d2af6b208787be93`, artifact `nexium-macos-intel-rustarmic-probe` **#12342108781**, and demonstrated that the actual SDL3 `InputBackend` initialized **before** winit could be retained in full `HorizonApp` without the original SIGABRT.

[Stage35 CI #39595973101](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39595973101) obtained four actual full-GUI own-PID window PNG captures (1392x860, 4 distinct hashes) from this **same unchanged original Intel binary**. Raw PNGs and private logs were discarded; pixel correctness and gameplay were not verified.

## Stage36 actual guest command-line experiment

The pinned original NeXium `main.rs` takes `std::env::args().nth(1)` as `nro_arg` and passes it into the real `HorizonApp::new`; constructor source invokes `EmulationHandle::new_with_presentation(&nro_path,...)` when the argument is nonempty, logging either `Auto-loaded NRO:` or `Failed to load NRO:`.

On a real macOS Intel GitHub runner this separate experiment:

1. Downloads both original GitHub Actions artifacts from their exact original run IDs, not from a mutable latest release.
2. Verifies x86_64 Mach-O and **exact original binary hash**; verifies original NRO filename, byte count, SHA-256 and `NRO0` header.
3. Runs the **actual full NeXium GUI** with the retained real pre-winit SDL3 `InputBackend` and the original homebrew NRO as the first command-line argument for 12 seconds, with UI/host audio disabled and an isolated home. Separately runs a no-NRO negative control on the identical executable.
4. Captures only truthful process survival/exit, own PID-owned window existence, whether source auto-load/failure marker appeared in process stdout, and a **count only** of nonempty guest SD diagnostics in the isolated home if any. No speculative `service_results` or audio output observations are manufactured.
5. Deletes temporary game-path and diagnostic files/private logs before publishing. Only sanitized source-bound receipt JSON may be uploaded, never guest file bytes, private paths, PNGs or NRO binaries. Ten fail-closed synthetic tests reject unverified game/guest/audio claims.

**Important:** a process that survives 12 seconds or displays NeXium's window does **not** prove that the NRO actually ran, much less that Vandal Hearts gameplay loaded. Even an `Auto-loaded NRO` message would establish only a loader-return observation; authoritative guest execution still requires real guest output and guest events. If GitHub's normal repository-scoped `GITHUB_TOKEN` cannot download an Actions artifact from the separate public Vandal Hearts repository, the workflow must fail transparently with that access restriction, not silently replace the source NRO or pull a different game file.

No changes to the Vandal Hearts game code, proprietary game images, NeXium main, tested SDL2 audio NRO in game PR #416 or native-audio Stage371 evidence.
