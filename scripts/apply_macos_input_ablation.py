#!/usr/bin/env python3
"""Opt-in Intel macOS diagnostic: skip SDL3 gamepad initialization in HorizonApp.

Experiment only. Does not repair the NeXium GUI or prove game input.
Applied exclusively to a local pinned upstream source checkout with
NEXIUM_EXPERIMENT_SDL_INPUT_ABLATION=1 at build time.
At run time NEXIUM_MACOS_SKIP_SDL_INPUT=1 skips InputBackend::new on macOS.
"""
from pathlib import Path
import argparse
import sys

ORIGINAL = '''        let gamepad = app_settings.gamepad.clone();
        let input = InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {
            log::warn!("SDL3 gamepad init failed");
            None
        });'''
REPLACEMENT = '''        // Intel macOS Stage28: isolate SDL3/joystick startup from winit's
        // event-loop reentrancy. Original gamepad path stays the default.
        let input = if cfg!(target_os = "macos")
            && std::env::var("NEXIUM_MACOS_SKIP_SDL_INPUT").ok().as_deref() == Some("1")
        {
            eprintln!("STAGE28_SDL_INPUT_SKIPPED");
            None
        } else {
            eprintln!("STAGE28_SDL_INPUT_INITIALIZING");
            let gamepad = app_settings.gamepad.clone();
            InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {
                log::warn!("SDL3 gamepad init failed");
                None
            })
        };'''
MARKER = "STAGE28_SDL_INPUT_SKIPPED"


def patch_source(source: str) -> str:
    if MARKER in source:
        if source.count(MARKER) == 1 and REPLACEMENT in source and ORIGINAL not in source:
            return source
        raise RuntimeError("partially applied SDL input patch or unexpected source drift")
    if source.count(ORIGINAL) != 1:
        raise RuntimeError("exactly one pinned HorizonApp input anchor required")
    return source.replace(ORIGINAL, REPLACEMENT, 1)


def apply(root: Path) -> bool:
    target = root / "nexium-gui/src/app.rs"
    original = target.read_text(encoding="utf-8")
    modified = patch_source(original)
    if modified == original:
        return False
    target.write_text(modified, encoding="utf-8")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkout", type=Path)
    args = p.parse_args()
    try:
        changed = apply(args.checkout)
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(f"STAGE28_SDL_INPUT_PATCH_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("STAGE28_SDL_INPUT_PATCH_APPLIED" if changed
          else "STAGE28_SDL_INPUT_PATCH_ALREADY_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
