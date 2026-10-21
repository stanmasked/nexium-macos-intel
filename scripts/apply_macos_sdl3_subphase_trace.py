#!/usr/bin/env python3
"""Opt-in source-anchored SDL3 input construction phase trace for Intel macOS.

No production behavior is altered except static diagnostic stderr lines when
NEXIUM_MACOS_SDL3_SUBPHASE_TRACE=1. Do not claim a particular native callback
caused a crash solely because it was the last marker observed.
"""
from pathlib import Path
import argparse
import sys

START = "    pub fn new(motion_enabled: bool, preferred: Option<String>) -> Option<Self> {"
END = "    fn sync_motion(&mut self) {"
PREFIX = "STAGE38_SDL3_INPUT_"
PHASES = (
    ("00_ENTRY", '        sdl3::hint::set("SDL_JOYSTICK_THREAD", "1");'),
    ("01_BEFORE_SDL_INIT", "        let sdl = sdl3::init().ok()?;"),
    ("02_BEFORE_GAMEPAD_SUBSYSTEM", "        let gamepad = sdl.gamepad().ok()?;"),
    ("03_BEFORE_RUMBLE", "        let rumble_out = crate::rumble_output::RumbleOutput::new();"),
    ("04_BEFORE_INPUT_STRUCT", '        log::info!("SDL3 gamepad subsystem initialized");'),
)

def block(name: str) -> str:
    return (
        '        #[cfg(target_os = "macos")]\n'
        '        if std::env::var("NEXIUM_MACOS_SDL3_SUBPHASE_TRACE")\n'
        '            .ok().as_deref() == Some("1")\n'
        '        {\n'
        f'            eprintln!("{PREFIX}{name}");\n'
        '        }\n'
    )

def patch_source(source: str) -> str:
    if PREFIX in source:
        if all(source.count(block(name)) == 1 for name, _ in PHASES) and (
            source.count(PREFIX) == len(PHASES)
        ):
            return source
        raise ValueError("SDL3 input partial instrumentation detected")
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("original pinned SDL3 InputBackend::new boundaries missing")
    head, remainder = source.split(START, 1)
    section, tail = remainder.split(END, 1)
    section = START + section
    starts = [section.find(anchor) for _, anchor in PHASES]
    if any(p < 0 for p in starts) or starts != sorted(set(starts)):
        raise ValueError("SDL3 phase call order or source anchors differ from pinned version")
    for name, anchor in PHASES:
        if section.count(anchor) != 1:
            raise ValueError("ambiguous SDL3 subphase anchor: " + name)
        section = section.replace(anchor, block(name) + anchor, 1)
    return head + section + END + tail

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args(argv)
    target = args.checkout / "nexium-gui/src/input.rs"
    try:
        original = target.read_text(encoding="utf-8")
        updated = patch_source(original)
        if updated != original:
            target.write_text(updated, encoding="utf-8")
        print("STAGE38_SDL3_PHASE_PATCH_APPLIED" if updated != original
              else "STAGE38_SDL3_PHASE_PATCH_IDEMPOTENT")
        return 0
    except (OSError, ValueError) as exc:
        print("STAGE38_SDL3_PHASE_PATCH_BLOCKED: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
