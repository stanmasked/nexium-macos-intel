#!/usr/bin/env python3
"""Stage46: opt-in real SDL3 RightX axis path via original NeXium InputBackend.

Apply after Stage45; the default and all previous stage opt-ins are unchanged.
Read-only InputSnapshot instrumentation observes source-processed right X.
The guest NRO independently samples padGetStickPos(..., 1).x, not host data.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BUTTON_ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
SNAPSHOT_ANCHOR = "        snap\n    }\n\n    pub fn first_pressed"

PULSE = '''            // Stage46: SDL_GAMEPAD_AXIS_RIGHTX (virtual raw axis index 2).
            // Negative, centered, positive, centered inside SOUTH/B hold.
            if std::env::var("NEXIUM_MACOS_GUEST_RIGHT_X_PROBE")
                .ok().as_deref() == Some("1")
            {
                use sdl3::sys::joystick::SDL_SetJoystickVirtualAxis;
                let right_x: i16 = if n >= 250 && n < 400 { -25000 }
                    else if n >= 525 && n < 675 { 25000 }
                    else { 0 };
                if !unsafe { SDL_SetJoystickVirtualAxis(ptr, 2, right_x) } {
                    if n == 250 { eprintln!("STAGE46_RIGHTX_AXIS_SET_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE46_RIGHTX_NEGATIVE_SENT");
                } else if n == 400 {
                    eprintln!("STAGE46_RIGHTX_CENTER_AFTER_NEGATIVE_SENT");
                } else if n == 525 {
                    eprintln!("STAGE46_RIGHTX_POSITIVE_SENT");
                } else if n == 675 {
                    eprintln!("STAGE46_RIGHTX_CENTER_AFTER_POSITIVE_SENT");
                }
            }
'''

OBSERVE = '''        // Observe genuine original InputSnapshot *after* SDL axis processing.
        // No writes to InputSnapshot, HidState, NPad or guest address space.
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_GUEST_RIGHT_X_PROBE")
            .ok().as_deref() == Some("1")
        {
            static STAGE46_OBS_PHASE: std::sync::atomic::AtomicU8 =
                std::sync::atomic::AtomicU8::new(0);
            use std::sync::atomic::Ordering;
            let phase = STAGE46_OBS_PHASE.load(Ordering::Relaxed);
            let rx = snap.sticks[2];
            if phase == 0 && rx < -12000 {
                eprintln!("STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_NEGATIVE");
                STAGE46_OBS_PHASE.store(1, Ordering::Relaxed);
            } else if phase == 1 && rx > -4000 && rx < 4000 {
                eprintln!("STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_CENTER_AFTER_NEGATIVE");
                STAGE46_OBS_PHASE.store(2, Ordering::Relaxed);
            } else if phase == 2 && rx > 12000 {
                eprintln!("STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_POSITIVE");
                STAGE46_OBS_PHASE.store(3, Ordering::Relaxed);
            } else if phase == 3 && rx > -4000 && rx < 4000 {
                eprintln!("STAGE46_ORIGINAL_SNAPSHOT_RIGHTX_CENTER_AFTER_POSITIVE");
                STAGE46_OBS_PHASE.store(4, Ordering::Relaxed);
            }
        }
'''


def patch_source(source: str) -> str:
    if PULSE in source or OBSERVE in source:
        if source.count(PULSE) == 1 and source.count(OBSERVE) == 1:
            return source
        raise RuntimeError("partial or duplicated Stage46 source patch")
    if "NEXIUM_MACOS_GUEST_RIGHT_X_PROBE" in source:
        raise RuntimeError("Stage46 source patch drift")
    if source.count(BUTTON_ANCHOR) != 1 or source.count(SNAPSHOT_ANCHOR) != 1:
        raise RuntimeError("original SDL3 button/InputSnapshot anchors missing")
    if source.count("NEXIUM_MACOS_GUEST_STICK_Y_PROBE") != 2:
        raise RuntimeError("Stage45 predecessor must be installed first")
    if source.count("NEXIUM_MACOS_GUEST_STICK_X_PROBE") != 2:
        raise RuntimeError("Stage44 predecessor must be installed first")
    if source.count("desc.axis_mask = 0x3fu32;") != 1:
        raise RuntimeError("SDL3 virtual gamepad must advertise RightX axis")
    return source.replace(BUTTON_ANCHOR, PULSE + BUTTON_ANCHOR, 1).replace(
        SNAPSHOT_ANCHOR, OBSERVE + SNAPSHOT_ANCHOR, 1
    )


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
        print("STAGE46_RIGHT_X_PATCH_APPLIED" if after != before
              else "STAGE46_RIGHT_X_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as error:
        print("STAGE46_RIGHT_X_PATCH_BLOCKED: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
