#!/usr/bin/env python3
"""Stage32: pre-initialize real SDL3 InputBackend BEFORE entering eframe/winit.

Three pinned NeXium source files are all validated before ANY writes.
Only opt-in NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT=1 changes startup.
This attempts to preserve the actual InputBackend and controller capability,
unlike Stage29's documented SDL3-input-disabled positive control.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from apply_macos_sdl3_input_ablation import UPDATED as APP_ORIGINAL

MAIN_ANCHOR = "    let mut log_feed_for_app = Some(log_feed);\n"
INPUT_ANCHOR = "impl InputBackend {\n"
MARKER = "STAGE32_PREINPUT_"
APP_MARKER = "STAGE32_TAKE_PREINITIALIZED_INPUT"

MAIN_PREINIT = r'''    // Stage32 experimental native Intel branch: construct the actual SDL3
    // controller input BEFORE entering eframe::run_native/winit event dispatch.
    // Never enabled by default, or on other platforms.
    #[cfg(target_os = "macos")]
    if std::env::var("NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT")
        .ok().as_deref() == Some("1")
    {
        eprintln!("STAGE32_PREINPUT_BEGIN_BEFORE_WINIT");
        input::stage32_preinitialize_input(
            settings.motion_enabled,
            settings.gamepad.clone(),
        );
        eprintln!("STAGE32_PREINPUT_DONE_BEFORE_WINIT");
    }
'''

INPUT_HELPER = r'''// Stage32 diagnostic-only: same main GUI thread, no cross-thread SDL3 object.
// Retain the original SDL3 Sdl/gamepad/rumble handles rather than bypassing
// controller input. The local instance is consumed exactly once by HorizonApp.
thread_local! {
    static STAGE32_EARLY_INPUT: std::cell::RefCell<Option<InputBackend>> =
        const { std::cell::RefCell::new(None) };
}

pub fn stage32_preinitialize_input(
    motion_enabled: bool,
    preferred: Option<String>,
) {
    STAGE32_EARLY_INPUT.with(|slot| {
        let input = InputBackend::new(motion_enabled, preferred);
        eprintln!("{}", if input.is_some() {
            "STAGE32_PREINPUT_CREATED_SOME"
        } else {
            "STAGE32_PREINPUT_CREATED_NONE"
        });
        *slot.borrow_mut() = input;
    });
}

pub fn stage32_take_preinitialized_input() -> Option<InputBackend> {
    STAGE32_EARLY_INPUT.with(|slot| slot.borrow_mut().take())
}

'''

APP_UPDATED = r'''        // Stage29/Stage32: opt-in A/B without changing default behavior.
        let stage29_skip_sdl3_input = cfg!(target_os = "macos")
            && std::env::var("NEXIUM_MACOS_SKIP_SDL3_INPUT")
                .ok().as_deref() == Some("1");
        let input = if stage29_skip_sdl3_input {
            eprintln!("STAGE29_SDL3_INPUT_SKIPPED");
            None
        } else {
            eprintln!("STAGE29_SDL3_INPUT_ENABLED");
            if cfg!(target_os = "macos")
                && std::env::var("NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT")
                    .ok().as_deref() == Some("1")
            {
                let preinitialized = crate::input::stage32_take_preinitialized_input();
                eprintln!("STAGE32_TAKE_PREINITIALIZED_INPUT");
                eprintln!("{}", if preinitialized.is_some() {
                    "STAGE32_TAKE_SOME"
                } else {
                    "STAGE32_TAKE_NONE"
                });
                preinitialized
            } else {
                InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {
                    log::warn!("SDL3 gamepad init failed");
                    None
                })
            }
        };'''


def patch_triplet(files: dict[str, str]) -> dict[str, str]:
    expected={"nexium-gui/src/main.rs", "nexium-gui/src/app.rs", "nexium-gui/src/input.rs"}
    if set(files) != expected:
        raise RuntimeError("must provide all three pinned NeXium sources")
    main, app, inp = (files[p] for p in ("nexium-gui/src/main.rs",
                                       "nexium-gui/src/app.rs",
                                       "nexium-gui/src/input.rs"))
    if MAIN_PREINIT in main and APP_UPDATED in app and INPUT_HELPER in inp:
        if (main.count(MAIN_PREINIT)==1 and app.count(APP_UPDATED)==1
                and inp.count(INPUT_HELPER)==1 and APP_ORIGINAL not in app):
            return dict(files)
        raise RuntimeError("Stage32 partial/doubled source patch")
    if (MARKER in main or MARKER in inp or APP_MARKER in app or
            "STAGE32_TAKE_" in app):
        raise RuntimeError("Stage32 partial or unrelated source drift")
    if main.count(MAIN_ANCHOR)!=1:
        raise RuntimeError("pinned main eframe app-creator anchor missing or doubled")
    if app.count(APP_ORIGINAL)!=1:
        raise RuntimeError("pinned Stage29 InputBackend ablation anchor missing or doubled")
    if inp.count(INPUT_ANCHOR)!=1:
        raise RuntimeError("pinned InputBackend impl anchor missing or doubled")
    return {
        "nexium-gui/src/main.rs":
            main.replace(MAIN_ANCHOR,MAIN_PREINIT+MAIN_ANCHOR,1),
        "nexium-gui/src/app.rs":
            app.replace(APP_ORIGINAL,APP_UPDATED,1),
        "nexium-gui/src/input.rs":
            inp.replace(INPUT_ANCHOR,INPUT_HELPER+INPUT_ANCHOR,1),
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    args=parser.parse_args(argv)
    paths=("nexium-gui/src/main.rs","nexium-gui/src/app.rs",
           "nexium-gui/src/input.rs")
    try:
        inputs={p:(args.source/p).read_text(encoding="utf-8") for p in paths}
        updates=patch_triplet(inputs)
        for p in paths:
            if inputs[p] != updates[p]:
                (args.source/p).write_text(updates[p],encoding="utf-8")
        print("STAGE32_PREWINIT_SDL3_PATCH_APPLIED" if inputs!=updates
              else "STAGE32_PREWINIT_SDL3_PATCH_ALREADY_APPLIED")
    except (RuntimeError,UnicodeError,OSError) as exc:
        print("STAGE32_PREWINIT_SDL3_PATCH_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
