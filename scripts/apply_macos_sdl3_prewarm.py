#!/usr/bin/env python3
"""Opt-in Stage40: initialize SDL3 controller backend before eframe/winit starts.

This is a controlled experiment, not a production fix. SDL3 and controller
support remain enabled. Main-thread thread_local storage passes the initialized
non-Send InputBackend into HorizonApp on the SAME thread without Arc/Mutex.
If the UI closure runs on another thread the prewarmed input will be missing;
we do not silently initialize it again in the reentrant constructor.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

MAIN_FUNCTION = "fn main() -> Result<(), eframe::Error> {"
MAIN_CALL = '    let result = eframe::run_native('
APP_CALL = "            InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {"
MAIN_SLOT = "STAGE40_PREWARM_MAIN_BEFORE_EFRAME"
APP_SLOT = "STAGE40_PREWARM_CONSTRUCTOR"

PREWARM_GLOBAL = '''#[cfg(target_os = "macos")]
thread_local! {
    // SDL's input context is intentionally not moved between AppKit threads.
    static STAGE40_PREWARMED_INPUT: std::cell::RefCell<Option<input::InputBackend>> =
        std::cell::RefCell::new(None);
}

#[cfg(target_os = "macos")]
pub(crate) fn stage40_take_prewarmed_input() -> Option<input::InputBackend> {
    STAGE40_PREWARMED_INPUT.with(|slot| slot.borrow_mut().take())
}

'''

PREWARM_MAIN = '''    // Stage40 experimental prewarming before eframe creates its event loop.
    #[cfg(target_os = "macos")]
    if std::env::var("NEXIUM_MACOS_PREWARM_SDL3_INPUT").ok().as_deref() == Some("1")
        && std::env::var("NEXIUM_MACOS_SKIP_SDL3_INPUT").ok().as_deref() != Some("1")
    {
        eprintln!("STAGE40_PREWARM_MAIN_BEFORE_EFRAME");
        let candidate = input::InputBackend::new(
            settings.motion_enabled, settings.gamepad.clone()
        );
        eprintln!(
            "{}",
            if candidate.is_some() {
                "STAGE40_PREWARM_MAIN_READY"
            } else {
                "STAGE40_PREWARM_MAIN_UNAVAILABLE"
            }
        );
        STAGE40_PREWARMED_INPUT.with(|slot| *slot.borrow_mut() = candidate);
    }

'''

PREWARM_APP = '''            // Stage40: take same-thread SDL3 context prepared before winit.
            // An unavailable prewarm stays None; never fall back to a
            // potentially reentrant second native initialization here.
            #[cfg(target_os = "macos")]
            let stage40_input = if std::env::var("NEXIUM_MACOS_PREWARM_SDL3_INPUT")
                .ok().as_deref() == Some("1")
            {
                let prewarmed = crate::stage40_take_prewarmed_input();
                eprintln!(
                    "{}",
                    if prewarmed.is_some() {
                        "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"
                    } else {
                        "STAGE40_PREWARM_CONSTRUCTOR_MISSING"
                    }
                );
                prewarmed
            } else {
                InputBackend::new(app_settings.motion_enabled, gamepad)
            };
            #[cfg(not(target_os = "macos"))]
            let stage40_input = InputBackend::new(app_settings.motion_enabled, gamepad);
            stage40_input.or_else(|| {'''


def patch_main(source: str) -> str:
    if MAIN_SLOT in source:
        if source.count(PREWARM_GLOBAL) == 1 and source.count(PREWARM_MAIN) == 1:
            return source
        raise ValueError("partial Stage40 main instrumentation")
    if source.count(MAIN_FUNCTION) != 1 or source.count(MAIN_CALL) != 1:
        raise ValueError("pinned main.rs event loop anchors missing")
    if source.count("mod input;") != 1 or source.count("use app_settings::AppSettings;") != 1:
        raise ValueError("expected pinned main module declarations absent")
    source = source.replace(MAIN_FUNCTION, PREWARM_GLOBAL + MAIN_FUNCTION, 1)
    source = source.replace(MAIN_CALL, PREWARM_MAIN + MAIN_CALL, 1)
    return source


def patch_app(source: str) -> str:
    if APP_SLOT in source:
        if source.count(PREWARM_APP) == 1:
            return source
        raise ValueError("partial Stage40 HorizonApp instrumentation")
    if source.count("STAGE29_SDL3_INPUT_ENABLED") != 1:
        raise ValueError("Stage29 SDL3 A/B gate missing")
    if source.count(APP_CALL) != 1:
        raise ValueError("Stage29 source initializer call missing or ambiguous")
    return source.replace(APP_CALL, PREWARM_APP, 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args(argv)
    base = args.checkout / "nexium-gui/src"
    main_file, app_file = base / "main.rs", base / "app.rs"
    try:
        original_main = main_file.read_text("utf-8")
        original_app = app_file.read_text("utf-8")
        patched_main = patch_main(original_main)
        patched_app = patch_app(original_app)
        # Validate BOTH before writing anything; patches fail closed.
        if patched_main != original_main:
            main_file.write_text(patched_main, encoding="utf-8")
        if patched_app != original_app:
            app_file.write_text(patched_app, encoding="utf-8")
        print("STAGE40_PREWARM_PATCH_APPLIED" if
              (patched_main != original_main or patched_app != original_app)
              else "STAGE40_PREWARM_PATCH_IDEMPOTENT")
        return 0
    except (OSError, ValueError) as exc:
        print("STAGE40_PREWARM_PATCH_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
