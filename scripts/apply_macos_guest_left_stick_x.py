#!/usr/bin/env python3
"""Stage44: opt-in SDL3 virtual LeftX axis excursion in original InputBackend.

Apply after the pinned Stage36/40/42/43 source transforms. No guest/HidState
memory injection: original SDL3 Gamepad::axis -> InputSnapshot -> original
HidState -> mapped guest NPad -> libnx padGetStickPos is the only data path.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
INSERT = '''            // Stage44 only: left stick negative X, neutral, positive X,
            // neutral, during the original 900-poll synthetic SOUTH/B hold.
            if std::env::var("NEXIUM_MACOS_GUEST_STICK_X_PROBE")
                .ok().as_deref() == Some("1")
            {
                use sdl3::sys::joystick::SDL_SetJoystickVirtualAxis;
                // 0 is SDL_GAMEPAD_AXIS_LEFTX, already in virtual axis_mask.
                let x: i16 = if n >= 250 && n < 400 { -25000 }
                    else if n >= 525 && n < 675 { 25000 }
                    else { 0 };
                if !unsafe { SDL_SetJoystickVirtualAxis(ptr, 0, x) } {
                    if n == 250 { eprintln!("STAGE44_LEFTX_AXIS_SET_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE44_LEFTX_NEGATIVE_SENT");
                } else if n == 400 {
                    eprintln!("STAGE44_LEFTX_NEUTRAL_AFTER_NEGATIVE_SENT");
                } else if n == 525 {
                    eprintln!("STAGE44_LEFTX_POSITIVE_SENT");
                } else if n == 675 {
                    eprintln!("STAGE44_LEFTX_NEUTRAL_AFTER_POSITIVE_SENT");
                }
            }
'''



OBSERVE_ANCHOR = "        snap\n    }\n\n    pub fn first_pressed"
OBSERVE = '''        // Stage44: inspect the genuine original InputSnapshot, never assign sticks.
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_GUEST_STICK_X_PROBE")
            .ok().as_deref() == Some("1")
        {
            static STAGE44_OBS_PHASE: std::sync::atomic::AtomicU8 =
                std::sync::atomic::AtomicU8::new(0);
            use std::sync::atomic::Ordering;
            let phase = STAGE44_OBS_PHASE.load(Ordering::Relaxed);
            let lx = snap.sticks[0];
            if phase == 0 && lx < -12000 {
                eprintln!("STAGE44_ORIGINAL_SNAPSHOT_LEFTX_NEGATIVE");
                STAGE44_OBS_PHASE.store(1, Ordering::Relaxed);
            } else if phase == 1 && lx > -4000 && lx < 4000 {
                eprintln!("STAGE44_ORIGINAL_SNAPSHOT_LEFTX_CENTER_AFTER_NEGATIVE");
                STAGE44_OBS_PHASE.store(2, Ordering::Relaxed);
            } else if phase == 2 && lx > 12000 {
                eprintln!("STAGE44_ORIGINAL_SNAPSHOT_LEFTX_POSITIVE");
                STAGE44_OBS_PHASE.store(3, Ordering::Relaxed);
            } else if phase == 3 && lx > -4000 && lx < 4000 {
                eprintln!("STAGE44_ORIGINAL_SNAPSHOT_LEFTX_CENTER_AFTER_POSITIVE");
                STAGE44_OBS_PHASE.store(4, Ordering::Relaxed);
            }
        }
'''

def patch_source(source: str) -> str:
    if INSERT in source or OBSERVE in source:
        if source.count(INSERT) == 1 and source.count(OBSERVE) == 1:
            return source
        raise RuntimeError("partial/duplicate Stage44 stick-axis patch")
    if "NEXIUM_MACOS_GUEST_STICK_X_PROBE" in source:
        raise RuntimeError("partial or mismatched Stage44 stick patch")
    if source.count(ANCHOR) != 1 or source.count(OBSERVE_ANCHOR) != 1:
        raise RuntimeError("pinned SDL3 SOUTH/B or original snapshot anchor absent")
    if source.count("NEXIUM_MACOS_GUEST_DPAD_PROBE") != 2:
        raise RuntimeError("original Stage43 DPad guard missing; wrong patch order")
    if source.count("NEXIUM_MACOS_GUEST_HID_PROBE") != 1:
        raise RuntimeError("original Stage40 long B hold missing")
    if source.count("desc.axis_mask = 0x3fu32;") != 1:
        raise RuntimeError("SDL3 virtual joystick must advertise LeftX axis")
    stage44 = source.replace(ANCHOR, INSERT + ANCHOR, 1)
    stage44 = stage44.replace(OBSERVE_ANCHOR, OBSERVE + OBSERVE_ANCHOR, 1)
    return stage44

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    path = args.source / "nexium-gui/src/input.rs"
    try:
        before = path.read_text(encoding="utf-8")
        after = patch_source(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
        print("STAGE44_STICK_X_PATCH_APPLIED" if after != before
              else "STAGE44_STICK_X_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as err:
        print("STAGE44_STICK_X_PATCH_BLOCKED: " + type(err).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
