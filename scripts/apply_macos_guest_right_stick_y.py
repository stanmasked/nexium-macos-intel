#!/usr/bin/env python3
"""Stage47 opt-in SDL3 right-Y axis test through the original input pipeline.

Apply after Stage46, preserving the verified X and Y analog paths. SDL gamepad RightY reports negative for up, whereas
original NeXium InputBackend converts ly=-axis(RightY) before writing HidState.
Do not mutate input snapshots, shared memory or guest state.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
OBSERVE_ANCHOR = "        snap\n    }\n\n    pub fn first_pressed"
PULSE = '''            // Stage47 only: SDL3 RightY up(-), center, down(+), center.
            if std::env::var("NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE")
                .ok().as_deref() == Some("1")
            {
                use sdl3::sys::joystick::SDL_SetJoystickVirtualAxis;
                let y: i16 = if n >= 250 && n < 400 { -25000 }
                    else if n >= 525 && n < 675 { 25000 }
                    else { 0 };
                if !unsafe { SDL_SetJoystickVirtualAxis(ptr, 3, y) } {
                    if n == 250 { eprintln!("STAGE47_RIGHTY_AXIS_SET_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE47_RIGHTY_SDL_UP_SENT");
                } else if n == 400 {
                    eprintln!("STAGE47_RIGHTY_CENTER_AFTER_UP_SENT");
                } else if n == 525 {
                    eprintln!("STAGE47_RIGHTY_SDL_DOWN_SENT");
                } else if n == 675 {
                    eprintln!("STAGE47_RIGHTY_CENTER_AFTER_DOWN_SENT");
                }
            }
'''
OBSERVE = '''        // Read only the original InputSnapshot after dead-zone processing.
        // Original InputBackend inverts raw SDL RightY to positive Switch up.
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE")
            .ok().as_deref() == Some("1")
        {
            static STAGE47_OBS_PHASE: std::sync::atomic::AtomicU8 =
                std::sync::atomic::AtomicU8::new(0);
            use std::sync::atomic::Ordering;
            let phase = STAGE47_OBS_PHASE.load(Ordering::Relaxed);
            let ly = snap.sticks[3];
            if phase == 0 && ly > 12000 {
                eprintln!("STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_UP_POSITIVE");
                STAGE47_OBS_PHASE.store(1, Ordering::Relaxed);
            } else if phase == 1 && ly > -4000 && ly < 4000 {
                eprintln!("STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_CENTER_AFTER_UP");
                STAGE47_OBS_PHASE.store(2, Ordering::Relaxed);
            } else if phase == 2 && ly < -12000 {
                eprintln!("STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_DOWN_NEGATIVE");
                STAGE47_OBS_PHASE.store(3, Ordering::Relaxed);
            } else if phase == 3 && ly > -4000 && ly < 4000 {
                eprintln!("STAGE47_ORIGINAL_SNAPSHOT_RIGHTY_CENTER_AFTER_DOWN");
                STAGE47_OBS_PHASE.store(4, Ordering::Relaxed);
            }
        }
'''


def patch_source(source: str) -> str:
    if PULSE in source or OBSERVE in source:
        if source.count(PULSE) == 1 and source.count(OBSERVE) == 1:
            return source
        raise RuntimeError("Stage47 partially installed or duplicated")
    if "NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE" in source:
        raise RuntimeError("Stage47 source drift")
    if source.count(ANCHOR) != 1 or source.count(OBSERVE_ANCHOR) != 1:
        raise RuntimeError("original SDL3 button or snapshot anchors changed")
    if source.count("NEXIUM_MACOS_GUEST_STICK_X_PROBE") != 2:
        raise RuntimeError("Stage44 source observer and axis pulse required")
    if source.count("NEXIUM_MACOS_GUEST_RIGHT_X_PROBE") != 2:
        raise RuntimeError("Stage46 right X predecessor missing")
    if source.count("desc.axis_mask = 0x3fu32;") != 1:
        raise RuntimeError("virtual SDL joystick axis mask changed")
    return source.replace(ANCHOR, PULSE + ANCHOR, 1).replace(
        OBSERVE_ANCHOR, OBSERVE + OBSERVE_ANCHOR, 1
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    path = args.source / "nexium-gui/src/input.rs"
    try:
        before = path.read_text(encoding="utf-8")
        after = patch_source(before)
        if before != after:
            path.write_text(after, encoding="utf-8")
        print("STAGE47_LEFT_Y_PATCH_APPLIED" if before != after
              else "STAGE47_LEFT_Y_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as error:
        print("STAGE47_LEFT_Y_PATCH_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
