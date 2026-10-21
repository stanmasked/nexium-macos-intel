#!/usr/bin/env python3
"""Stage29: opt-in one-variable SDL3 InputBackend initializer ablation.

Applied to the pinned Stage28-instrumented HorizonApp::new in a local
experimental macOS checkout. Original startup remains unchanged unless
NEXIUM_MACOS_SKIP_SDL3_INPUT=1. Host/UI audio ablation remains independently
controlled by the existing Stage21 NEXIUM_MACOS_NO_AUDIO switch.
"""
from pathlib import Path
import argparse
import sys

START = "    pub fn new(\n        cc: &eframe::CreationContext<'_>,"
END = "    fn apply_theme(ctx: &egui::Context)"
ORIGINAL = '''        let input = InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {
            log::warn!("SDL3 gamepad init failed");
            None
        });'''
UPDATED = '''        // Stage29: deliberately bypass only SDL3 input construction in the
        // opt-in native Intel diagnostic, retain all other HorizonApp stages.
        let stage29_skip_sdl3_input = cfg!(target_os = "macos")
            && std::env::var("NEXIUM_MACOS_SKIP_SDL3_INPUT")
                .ok().as_deref() == Some("1");
        let input = if stage29_skip_sdl3_input {
            eprintln!("STAGE29_SDL3_INPUT_SKIPPED");
            None
        } else {
            eprintln!("STAGE29_SDL3_INPUT_ENABLED");
            InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {
                log::warn!("SDL3 gamepad init failed");
                None
            })
        };'''
SKIP_MARKER = "STAGE29_SDL3_INPUT_SKIPPED"
RUN_MARKER = "STAGE29_SDL3_INPUT_ENABLED"

def patch_source(source: str) -> str:
    if SKIP_MARKER in source or RUN_MARKER in source:
        if (source.count(SKIP_MARKER)==1 and source.count(RUN_MARKER)==1
                and source.count(UPDATED)==1 and ORIGINAL not in source):
            return source
        raise RuntimeError("Stage29 source appears partially patched")
    if source.count(START)!=1 or source.count(END)!=1:
        raise RuntimeError("pinned HorizonApp ctor section missing or duplicated")
    head,tail=source.split(START,1)
    ctor,after=tail.split(END,1)
    ctor=START+ctor
    if "STAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT" not in ctor:
        raise RuntimeError("Stage28 source phase markers not applied")
    if "STAGE28_HORIZON_CTOR_PHASE_04_AFTER_INPUT" not in ctor:
        raise RuntimeError("Stage28 after-input marker missing")
    if ctor.count(ORIGINAL)!=1:
        raise RuntimeError("SDL3 InputBackend call missing or ambiguous")
    return head+ctor.replace(ORIGINAL,UPDATED,1)+END+after

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    args=parser.parse_args(argv)
    path=args.source/"nexium-gui/src/app.rs"
    try:
        old=path.read_text(encoding="utf-8")
        new=patch_source(old)
        if new!=old:
            path.write_text(new,encoding="utf-8")
        print("STAGE29_SDL3_INPUT_PATCH_APPLIED" if new!=old
              else "STAGE29_SDL3_INPUT_PATCH_ALREADY_APPLIED")
    except (OSError, UnicodeError, RuntimeError) as e:
        print("STAGE29_SDL3_INPUT_PATCH_BLOCKED: "+str(e),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    sys.exit(main())
