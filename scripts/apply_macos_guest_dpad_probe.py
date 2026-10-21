#!/usr/bin/env python3
"""Stage43: opt-in SDL3 virtual DPad Up and Right, retaining verified Stage42.

Apply AFTER the pinned Stage36 + Stage40 + Stage42 transforms. In Stage43
only, SOUTH/B stays held for 900 InputBackend polls; DPad Up and Right are
pulsed separately inside that hold. Stage40/41/42 code paths remain unchanged
when NEXIUM_MACOS_GUEST_DPAD_PROBE is not exactly 1.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from apply_macos_guest_ab_probe import NEW_MASK as STAGE42_MASK

STAGE43_MASK = '''    desc.button_mask = if std::env::var("NEXIUM_MACOS_GUEST_DPAD_PROBE")
        .ok().as_deref() == Some("1")
    {
        1u32 | (1u32 << 11) | (1u32 << 14)
    } else if std::env::var("NEXIUM_MACOS_GUEST_AB_PROBE")
        .ok().as_deref() == Some("1") { 3u32 } else { 1u32 };
    // Stage43: SOUTH/B + DPad Up and Right for the guest opt-in only.'''

BUTTON_ANCHOR = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"

STAGE43_DPAD_PULSES = '''            // Stage43: mutually exclusive real SDL3 DPad Up and Right pulses.
            // SDL3 virtual gamepad maps advertised buttons densely: SOUTH raw 0,
            // DPad Up raw 1, DPad Right raw 2 (not their enum values).
            if std::env::var("NEXIUM_MACOS_GUEST_DPAD_PROBE")
                .ok().as_deref() == Some("1")
            {
                let up_down = n >= 250 && n < 390;
                let right_down = n >= 520 && n < 660;
                if !unsafe { SDL_SetJoystickVirtualButton(ptr, 1, up_down) } {
                    if n == 250 { eprintln!("STAGE43_DPAD_UP_SET_FAILED"); }
                } else if n == 250 {
                    eprintln!("STAGE43_DPAD_UP_PRESS_SENT");
                } else if n == 390 {
                    eprintln!("STAGE43_DPAD_UP_RELEASE_SENT");
                }
                if !unsafe { SDL_SetJoystickVirtualButton(ptr, 2, right_down) } {
                    if n == 520 { eprintln!("STAGE43_DPAD_RIGHT_SET_FAILED"); }
                } else if n == 520 {
                    eprintln!("STAGE43_DPAD_RIGHT_PRESS_SENT");
                } else if n == 660 {
                    eprintln!("STAGE43_DPAD_RIGHT_RELEASE_SENT");
                }
            }
'''


def patch_source(source: str) -> str:
    if STAGE43_MASK in source or STAGE43_DPAD_PULSES in source:
        if source.count(STAGE43_MASK) == 1 and source.count(STAGE43_DPAD_PULSES) == 1:
            return source
        raise RuntimeError("incomplete or duplicate Stage43 DPad instrumentation")
    if source.count(STAGE42_MASK) != 1 or source.count(BUTTON_ANCHOR) != 1:
        raise RuntimeError("pinned Stage42 descriptor/SDL3 B button anchors missing")
    if source.count('NEXIUM_MACOS_GUEST_HID_PROBE') != 1:
        raise RuntimeError("Stage40 long guest B hold is required first")
    if source.count('NEXIUM_MACOS_GUEST_AB_PROBE') != 2:
        raise RuntimeError("Stage42 conditional A support is required first")
    updated = source.replace(STAGE42_MASK, STAGE43_MASK, 1)
    updated = updated.replace(BUTTON_ANCHOR, STAGE43_DPAD_PULSES + BUTTON_ANCHOR, 1)
    if updated.count("NEXIUM_MACOS_GUEST_DPAD_PROBE") != 2:
        raise RuntimeError("Stage43 descriptor and input poll gates must be unique")
    return updated


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
        print("STAGE43_DPAD_PATCH_APPLIED" if before != after
              else "STAGE43_DPAD_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as error:
        print("STAGE43_DPAD_PATCH_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
