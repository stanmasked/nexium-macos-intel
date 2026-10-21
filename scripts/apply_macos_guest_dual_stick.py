#!/usr/bin/env python3
"""Stage48: simultaneous four-axis virtual SDL3 stick crossover, guest verified.

Source patch follows Stage47 and only activates under a separate explicit
opt-in. Original InputSnapshot is observed after the real axis/dead-zone
processing; there is no guest HID/shmem or InputSnapshot value modification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BUTTON_ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
SNAPSHOT_ANCHOR = "        snap\n    }\n\n    pub fn first_pressed"

PULSE = '''            // Stage48: simultaneous two-stick diagonals with reverse and
            // two neutral intervals. SDL LeftY/RightY are inverted by input.
            if std::env::var("NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE")
                .ok().as_deref() == Some("1")
            {
                use sdl3::sys::joystick::SDL_SetJoystickVirtualAxis;
                let first = n >= 250 && n < 400;
                let second = n >= 525 && n < 675;
                let lx: i16 = if first { -25000 } else if second { 25000 } else { 0 };
                let ly: i16 = if first { -25000 } else if second { 25000 } else { 0 };
                let rx: i16 = if first { 25000 } else if second { -25000 } else { 0 };
                let ry: i16 = if first { 25000 } else if second { -25000 } else { 0 };
                let axis_ok = unsafe {
                    SDL_SetJoystickVirtualAxis(ptr, 0, lx) &&
                    SDL_SetJoystickVirtualAxis(ptr, 1, ly) &&
                    SDL_SetJoystickVirtualAxis(ptr, 2, rx) &&
                    SDL_SetJoystickVirtualAxis(ptr, 3, ry)
                };
                if !axis_ok {
                    if n == 250 { eprintln!("STAGE48_DUAL_AXIS_SET_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE48_DUAL_DIAGONAL_A_SENT");
                } else if n == 400 {
                    eprintln!("STAGE48_DUAL_CENTER_AFTER_A_SENT");
                } else if n == 525 {
                    eprintln!("STAGE48_DUAL_DIAGONAL_B_SENT");
                } else if n == 675 {
                    eprintln!("STAGE48_DUAL_CENTER_AFTER_B_SENT");
                }
            }
'''

OBSERVE = '''        // Validate all four processed original analog values *together*.
        // These are reads only; original SDL3 -> InputSnapshot -> HID is kept.
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE")
            .ok().as_deref() == Some("1")
        {
            static STAGE48_OBS_PHASE: std::sync::atomic::AtomicU8 =
                std::sync::atomic::AtomicU8::new(0);
            use std::sync::atomic::Ordering;
            let phase = STAGE48_OBS_PHASE.load(Ordering::Relaxed);
            let (lx, ly, rx, ry) =
                (snap.sticks[0], snap.sticks[1], snap.sticks[2], snap.sticks[3]);
            let center = lx > -4000 && lx < 4000
                && ly > -4000 && ly < 4000
                && rx > -4000 && rx < 4000
                && ry > -4000 && ry < 4000;
            let diag_a = lx < -12000 && ly > 12000
                && rx > 12000 && ry < -12000;
            let diag_b = lx > 12000 && ly < -12000
                && rx < -12000 && ry > 12000;
            if phase == 0 && diag_a {
                eprintln!("STAGE48_ORIGINAL_SNAPSHOT_DUAL_DIAGONAL_A");
                STAGE48_OBS_PHASE.store(1, Ordering::Relaxed);
            } else if phase == 1 && center {
                eprintln!("STAGE48_ORIGINAL_SNAPSHOT_DUAL_CENTER_AFTER_A");
                STAGE48_OBS_PHASE.store(2, Ordering::Relaxed);
            } else if phase == 2 && diag_b {
                eprintln!("STAGE48_ORIGINAL_SNAPSHOT_DUAL_DIAGONAL_B");
                STAGE48_OBS_PHASE.store(3, Ordering::Relaxed);
            } else if phase == 3 && center {
                eprintln!("STAGE48_ORIGINAL_SNAPSHOT_DUAL_CENTER_AFTER_B");
                STAGE48_OBS_PHASE.store(4, Ordering::Relaxed);
            }
        }
'''


def patch_source(source: str) -> str:
    if PULSE in source or OBSERVE in source:
        if source.count(PULSE) == 1 and source.count(OBSERVE) == 1:
            return source
        raise RuntimeError("partial or duplicated Stage48 instrumentation")
    if "NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE" in source:
        raise RuntimeError("Stage48 source contract drift")
    if source.count(BUTTON_ANCHOR) != 1 or source.count(SNAPSHOT_ANCHOR) != 1:
        raise RuntimeError("original SDL3 button or snapshot source changed")
    if source.count('NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE') != 2:
        raise RuntimeError("Stage47 Y predecessor is mandatory")
    if source.count('NEXIUM_MACOS_GUEST_RIGHT_X_PROBE') != 2:
        raise RuntimeError("Stage46 X predecessor is mandatory")
    if source.count('desc.axis_mask = 0x3fu32;') != 1:
        raise RuntimeError("original SDL virtual four-axis descriptor changed")
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
        if before != after:
            path.write_text(after, encoding="utf-8")
        print("STAGE48_DUAL_STICK_PATCH_APPLIED" if before != after
              else "STAGE48_DUAL_STICK_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as exc:
        print("STAGE48_DUAL_STICK_PATCH_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
