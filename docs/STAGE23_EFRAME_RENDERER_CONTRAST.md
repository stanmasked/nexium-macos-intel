# Stage23 — Intel macOS minimal eframe renderer A/B preparation

## Original diagnostic boundary

Stage21 hosted Intel macOS A/B attempted the same original GUI process with/without host/UI audio; both failed with SIGABRT in winit. Stage22 isolates `eframe/Wgpu` startup without `HorizonApp` in [Draft PR #6](https://github.com/stanmasked/nexium-macos-intel/pull/6). **Do not claim Stage22 minimal GUI outcome before its native job completes.**

## Single Mach-O Wgpu versus Glow comparison

This child branch adds a third optional patch applied *only* after the Stage22 minimal eframe source patch. The normal NeXium code path remains the same. The minimal-mode branch chooses `eframe::Renderer::Wgpu` or `eframe::Renderer::Glow` via `NEXIUM_MACOS_MINIMAL_RENDERER=wgpu|glow`, prints an explicit branch marker, and rejects unrecognized values.

The same freshly built native Intel binary is launched in two isolated no-NRO processes:

| Variant | Minimal GUI | Renderer | Host audio |
|---|---|---|---|
| Wgpu | enabled | Wgpu/Metal default | disabled |
| Glow | enabled | Glow/OpenGL fallback | disabled |

Both programs are sampled for 12 seconds and passed an optional scoped CoreGraphics window identifier helper. The classifier requires the same executable SHA-256 and the correct console marker for each variant before publishing results. A SIGABRT is a real failure observation; process survival does not prove pixels were presented. Window ID visibility, if independently observed, is not proof of emulator or NRO graphics.

Nine additional fail-closed synthetic tests cover source-patch idempotence, renderer toggle confinement, unchanged original GUI, duplicate/missing anchors and partial source edits.

**Interpretation (not presupposed):** If Wgpu fails while Glow survives, focus follow-on diagnostics on the Wgpu/Metal surface or event-loop interaction. If both fail, investigate shared eframe/winit/AppKit execution or the hosted environment. If both survive, observe genuine windows and then independently test local clean homebrew inputs. This experiment does not test any NRO, ROM, firmware or Nintendo Switch speaker.

The branch is intentionally isolated from the running Stage22 PR; do not publish Stage23 as a successful runtime diagnostic until a real native Intel CI job executes both variants.
