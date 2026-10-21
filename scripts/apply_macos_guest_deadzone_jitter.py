#!/usr/bin/env python3
"""Stage52 original SDL3/NeXium dead-zone jitter vs processed four-stick state.

Upstream pinned default deadzones: 0.12 for both sticks. Source original:
dz(v, limit) = 0 if abs(v) < limit; v = SDL axis / 32768, with Y
sign reversal and processed state scaled by 30000. Test +/-1000 raw axis
jitter: nonzero original raw_sticks, zero original processed sticks.
No direct InputSnapshot mutation, no guest HID injection.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

BUTTON_ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
SNAPSHOT_ANCHOR = "        snap\n    }\n\n    pub fn first_pressed"

PULSE = '''            // Stage52 source-authentic low amplitude virtual joystick jitter.
            // All four axes are nonzero, below pinned default 0.12 deadzone.
            if std::env::var("NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE")
                .ok().as_deref() == Some("1")
            {
                use sdl3::sys::joystick::SDL_SetJoystickVirtualAxis;
                let a = n >= 250 && n < 400;
                let b = n >= 525 && n < 675;
                let p: i16 = if a { 1000 } else if b { -1000 } else { 0 };
                let q: i16 = if a { -1000 } else if b { 1000 } else { 0 };
                let set_ok = unsafe {
                    SDL_SetJoystickVirtualAxis(ptr, 0, p) &&
                    SDL_SetJoystickVirtualAxis(ptr, 1, q) &&
                    SDL_SetJoystickVirtualAxis(ptr, 2, q) &&
                    SDL_SetJoystickVirtualAxis(ptr, 3, p)
                };
                if !set_ok {
                    if n == 250 { eprintln!("STAGE52_JITTER_VIRTUAL_AXIS_SET_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE52_JITTER_RAW_PATTERN_A_SENT");
                } else if n == 400 {
                    eprintln!("STAGE52_JITTER_CENTER_AFTER_A_SENT");
                } else if n == 525 {
                    eprintln!("STAGE52_JITTER_RAW_PATTERN_B_SENT");
                } else if n == 675 {
                    eprintln!("STAGE52_JITTER_CENTER_AFTER_B_SENT");
                }
            }
'''

OBSERVE = '''        // Read source InputSnapshot produced by original SDL3, inversion
        // and configured deadzone. raw_sticks must contain tiny movement,
        // processed sticks must be neutral for all axes simultaneously.
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE")
            .ok().as_deref() == Some("1")
        {
            static STAGE52_OBS_PHASE: std::sync::atomic::AtomicU8 =
                std::sync::atomic::AtomicU8::new(0);
            use std::sync::atomic::Ordering;
            let phase = STAGE52_OBS_PHASE.load(Ordering::Relaxed);
            let r = snap.raw_sticks;
            let p = snap.sticks;
            let neutral = p[0] == 0 && p[1] == 0
                && p[2] == 0 && p[3] == 0;
            // SDL LeftY and RightY must be inverted before raw_sticks.
            let pattern_a = r[0] > 0.025 && r[1] > 0.025
                && r[2] < -0.025 && r[3] < -0.025;
            let pattern_b = r[0] < -0.025 && r[1] < -0.025
                && r[2] > 0.025 && r[3] > 0.025;
            let raw_center = r.iter().all(|v| v.abs() < 0.005);
            if phase == 0 && pattern_a && neutral {
                eprintln!("STAGE52_ORIGINAL_RAW_JITTER_A_PROCESSED_NEUTRAL");
                STAGE52_OBS_PHASE.store(1, Ordering::Relaxed);
            } else if phase == 1 && raw_center && neutral {
                eprintln!("STAGE52_ORIGINAL_JITTER_CENTER_AFTER_A");
                STAGE52_OBS_PHASE.store(2, Ordering::Relaxed);
            } else if phase == 2 && pattern_b && neutral {
                eprintln!("STAGE52_ORIGINAL_RAW_JITTER_B_PROCESSED_NEUTRAL");
                STAGE52_OBS_PHASE.store(3, Ordering::Relaxed);
            } else if phase == 3 && raw_center && neutral {
                eprintln!("STAGE52_ORIGINAL_JITTER_CENTER_AFTER_B");
                STAGE52_OBS_PHASE.store(4, Ordering::Relaxed);
            }
        }
'''


def patch_source(source: str) -> str:
    if PULSE in source or OBSERVE in source:
        if source.count(PULSE) == 1 and source.count(OBSERVE) == 1:
            return source
        raise RuntimeError("partial/duplicated Stage52 source patch")
    if "NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE" in source:
        raise RuntimeError("Stage52 source instrumentation drift")
    if source.count(BUTTON_ANCHOR) != 1 or source.count(SNAPSHOT_ANCHOR) != 1:
        raise RuntimeError("original SDL3/InputSnapshot source anchors changed")
    if source.count("NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE") != 2:
        raise RuntimeError("Stage48 original dual-stick patch prerequisite missing")
    if source.count("desc.axis_mask = 0x3fu32;") != 1:
        raise RuntimeError("virtual SDL3 axis descriptor changed")
    if "snap.raw_sticks = [lx, ly, rx, ry];" not in source:
        raise RuntimeError("original raw stick source processing changed")
    if "let dz = |v: f32, limit: f32| if v.abs() < limit { 0.0 } else { v };" not in source:
        raise RuntimeError("original deadzone semantics changed")
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
        print("STAGE52_JITTER_PATCH_APPLIED" if before != after
              else "STAGE52_JITTER_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as exc:
        print("STAGE52_JITTER_PATCH_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
