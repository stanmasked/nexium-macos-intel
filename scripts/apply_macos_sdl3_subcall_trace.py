#!/usr/bin/env python3
"""Stage33: marker-only instrumentation of pinned SDL3 InputBackend::new.

Do not suppress, defer or reorder SDL3. A real macOS Intel process may
abort after any marker. The analysis records only what actually appeared.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

START='    pub fn new(motion_enabled: bool, preferred: Option<String>) -> Option<Self> {\n'
END='    fn sync_motion(&mut self) {'
MARKER='STAGE33_INPUT_PHASE_'
PHASES=(
    ('00_BEFORE_HINTS', '        sdl3::hint::set("SDL_JOYSTICK_THREAD", "1");'),
    ('01_AFTER_HINTS', '        let motion_hint_note = MOTION_HINTS[..3]'),
    ('02_BEFORE_SDL_INIT', '        let sdl = sdl3::init().ok()?;'),
    ('03_AFTER_SDL_INIT', '        let gamepad = sdl.gamepad().ok()?;'),
    ('04_AFTER_GAMEPAD', '        let rumble_out = crate::rumble_output::RumbleOutput::new();'),
    ('05_AFTER_RUMBLE', '        log::info!("SDL3 gamepad subsystem initialized");'),
    ('06_BEFORE_RETURN', '        Some(Self {'),
)

def instrument(name: str) -> str:
    return (
        '        #[cfg(target_os = "macos")]\n'
        '        if std::env::var("NEXIUM_MACOS_SDL3_SUBCALL_TRACE")'
        '.ok().as_deref() == Some("1") {\n'
        '            eprintln!("'+MARKER+name+'");\n'
        '        }\n'
    )

def patch_source(original: str) -> str:
    generated=[instrument(name) for name,_ in PHASES]
    if MARKER in original:
        if all(original.count(block)==1 for block in generated) and (
                original.count(MARKER)==len(PHASES)):
            return original
        raise RuntimeError("Stage33 partial or inconsistent existing phase trace")
    if original.count(START)!=1 or original.count(END)!=1:
        raise RuntimeError("pinned InputBackend::new boundaries absent or duplicated")
    head,tail=original.split(START,1)
    func,after=tail.split(END,1)
    func=START+func
    at=[]
    for name,anchor in PHASES:
        if func.count(anchor)!=1:
            raise RuntimeError("SDL3 input subcall anchor absent or doubled: "+name)
        at.append(func.index(anchor))
    if at!=sorted(at) or len(set(at))!=len(at):
        raise RuntimeError("SDL3 input source subcalls unexpectedly reordered")
    for name,anchor in PHASES:
        func=func.replace(anchor,instrument(name)+anchor,1)
    return head+func+END+after

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path)
    args=p.parse_args(argv)
    path=args.source/"nexium-gui/src/input.rs"
    try:
        old=path.read_text(encoding="utf-8")
        new=patch_source(old)
        if new!=old: path.write_text(new,encoding="utf-8")
        print("STAGE33_SDL3_SUBCALL_TRACE_PATCH_APPLIED" if new!=old
              else "STAGE33_SDL3_SUBCALL_TRACE_ALREADY_APPLIED")
    except (OSError,UnicodeError,RuntimeError) as exc:
        print("STAGE33_SDL3_SUBCALL_TRACE_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    sys.exit(main())
