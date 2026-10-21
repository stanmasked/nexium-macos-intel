#!/usr/bin/env python3
"""Stage53 source-bound below-vs-above 12% deadzone boundary, four axes."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

BUTTON_ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
SNAPSHOT_ANCHOR = "        snap\n    }\n\n    pub fn first_pressed"

PULSE = '''            // Stage53: compare below (3000/32768) vs above (6000/32768)
            // the pinned 0.12 default deadzone on all four analog axes.
            if std::env::var("NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE")
                .ok().as_deref() == Some("1")
            {
                use sdl3::sys::joystick::SDL_SetJoystickVirtualAxis;
                let below_a = n >= 250 && n < 350;
                let above_a = n >= 350 && n < 450;
                let below_b = n >= 525 && n < 625;
                let above_b = n >= 625 && n < 725;
                let amplitude: i16 = if above_a || above_b { 6000 }
                    else if below_a || below_b { 3000 }
                    else { 0 };
                let reverse = below_b || above_b;
                let p = if reverse { -amplitude } else { amplitude };
                let q = -p;
                let ok = unsafe {
                    SDL_SetJoystickVirtualAxis(ptr, 0, p) &&
                    SDL_SetJoystickVirtualAxis(ptr, 1, q) &&
                    SDL_SetJoystickVirtualAxis(ptr, 2, q) &&
                    SDL_SetJoystickVirtualAxis(ptr, 3, p)
                };
                if !ok {
                    if n == 250 { eprintln!("STAGE53_THRESHOLD_VIRTUAL_AXIS_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE53_BELOW_A_SENT");
                } else if n == 350 {
                    eprintln!("STAGE53_ABOVE_A_SENT");
                } else if n == 450 {
                    eprintln!("STAGE53_CENTER_AFTER_A_SENT");
                } else if n == 525 {
                    eprintln!("STAGE53_BELOW_B_SENT");
                } else if n == 625 {
                    eprintln!("STAGE53_ABOVE_B_SENT");
                } else if n == 725 {
                    eprintln!("STAGE53_CENTER_AFTER_B_SENT");
                }
            }
'''

OBSERVE = '''        // Original per-axis dz and Y inversion are applied here, read only.
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE")
            .ok().as_deref() == Some("1")
        {
            static STAGE53_OBS_PHASE: std::sync::atomic::AtomicU8 =
                std::sync::atomic::AtomicU8::new(0);
            use std::sync::atomic::Ordering;
            let phase = STAGE53_OBS_PHASE.load(Ordering::Relaxed);
            let r = snap.raw_sticks;
            let p = snap.sticks;
            let neutral = p.iter().all(|v| *v == 0);
            // Raw left and right Y signs are inverted from the SDL values.
            let raw_a = r[0] > 0.07 && r[1] > 0.07
                && r[2] < -0.07 && r[3] < -0.07;
            let raw_b = r[0] < -0.07 && r[1] < -0.07
                && r[2] > 0.07 && r[3] > 0.07;
            let above_a = p[0] > 4500 && p[1] > 4500
                && p[2] < -4500 && p[3] < -4500;
            let above_b = p[0] < -4500 && p[1] < -4500
                && p[2] > 4500 && p[3] > 4500;
            let centered = r.iter().all(|v| v.abs() < 0.005) && neutral;
            if phase == 0 && raw_a && neutral {
                eprintln!("STAGE53_ORIGINAL_BELOW_A_SUPPRESSED");
                STAGE53_OBS_PHASE.store(1, Ordering::Relaxed);
            } else if phase == 1 && raw_a && above_a {
                eprintln!("STAGE53_ORIGINAL_ABOVE_A_PASSED");
                STAGE53_OBS_PHASE.store(2, Ordering::Relaxed);
            } else if phase == 2 && centered {
                eprintln!("STAGE53_ORIGINAL_CENTER_AFTER_A");
                STAGE53_OBS_PHASE.store(3, Ordering::Relaxed);
            } else if phase == 3 && raw_b && neutral {
                eprintln!("STAGE53_ORIGINAL_BELOW_B_SUPPRESSED");
                STAGE53_OBS_PHASE.store(4, Ordering::Relaxed);
            } else if phase == 4 && raw_b && above_b {
                eprintln!("STAGE53_ORIGINAL_ABOVE_B_PASSED");
                STAGE53_OBS_PHASE.store(5, Ordering::Relaxed);
            } else if phase == 5 && centered {
                eprintln!("STAGE53_ORIGINAL_CENTER_AFTER_B");
                STAGE53_OBS_PHASE.store(6, Ordering::Relaxed);
            }
        }
'''


def patch_source(source: str) -> str:
    if PULSE in source or OBSERVE in source:
        if source.count(PULSE) == 1 and source.count(OBSERVE) == 1:
            return source
        raise RuntimeError("partial or duplicated Stage53 source patch")
    if "NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE" in source:
        raise RuntimeError("Stage53 source patch drift")
    if source.count(BUTTON_ANCHOR) != 1 or source.count(SNAPSHOT_ANCHOR) != 1:
        raise RuntimeError("original InputBackend anchors absent")
    if source.count("NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE") != 2:
        raise RuntimeError("Stage52 predecessor not installed")
    if "let dz = |v: f32, limit: f32| if v.abs() < limit { 0.0 } else { v };" not in source:
        raise RuntimeError("original deadzone semantics changed")
    if "snap.raw_sticks = [lx, ly, rx, ry];" not in source:
        raise RuntimeError("original raw stick snapshot changed")
    if source.count("desc.axis_mask = 0x3fu32;") != 1:
        raise RuntimeError("four-axis SDL virtual descriptor missing")
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
        print("STAGE53_THRESHOLD_PATCH_APPLIED" if before != after
              else "STAGE53_THRESHOLD_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as exc:
        print("STAGE53_THRESHOLD_PATCH_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
