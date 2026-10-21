#!/usr/bin/env python3
"""Stage42: add a second synthetic EAST/A to the proven SOUTH/B SDL3 probe.

Applies only after original pinned Stage36 and Stage40 transforms. The extra
A button is advertised and driven only with NEXIUM_MACOS_GUEST_AB_PROBE=1;
previous Stage36–41 controls and production use keep SOUTH/B behavior.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

OLD_MASK = "    desc.button_mask = 1u32; // SOUTH/A only"
NEW_MASK = """    desc.button_mask = if std::env::var("NEXIUM_MACOS_GUEST_AB_PROBE")
        .ok().as_deref() == Some("1") { 3u32 } else { 1u32 };
    // Stage42: SOUTH/B + EAST/A only with the guest A+B opt-in."""
OLD_SEND = "            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"
NEW_SEND = """            // The verified SOUTH/B hold remains unchanged; EAST/A is nested
            // within it to demonstrate B -> A+B -> B -> neutral in guest.
            if std::env::var("NEXIUM_MACOS_GUEST_AB_PROBE")
                .ok().as_deref() == Some("1")
            {
                let a_down = n >= 350 && n < 600;
                if !unsafe { SDL_SetJoystickVirtualButton(ptr, 1, a_down) } {
                    if n == 350 { eprintln!("STAGE42_VIRTUAL_A_SET_FAILED"); }
                } else if n == 350 {
                    eprintln!("STAGE42_VIRTUAL_A_PRESS_SENT");
                } else if n == 600 {
                    eprintln!("STAGE42_VIRTUAL_A_RELEASE_SENT");
                }
            }
            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {"""


def patch_source(source: str) -> str:
    if NEW_MASK in source or NEW_SEND in source:
        if source.count(NEW_MASK) == 1 and source.count(NEW_SEND) == 1:
            return source
        raise RuntimeError("Stage42 A+B source instrumentation partially installed")
    if source.count(OLD_MASK) != 1 or source.count(OLD_SEND) != 1:
        raise RuntimeError("Stage36 SDL3 button anchors missing or duplicated")
    if source.count("NEXIUM_MACOS_GUEST_HID_PROBE") != 1:
        raise RuntimeError("Stage40 sustained guest B hold must be installed first")
    updated = source.replace(OLD_MASK, NEW_MASK, 1).replace(OLD_SEND, NEW_SEND, 1)
    if updated.count("NEXIUM_MACOS_GUEST_AB_PROBE") != 2:
        raise RuntimeError("Stage42 must gate both the SDL descriptor and EAST pulse")
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
        print("STAGE42_GUEST_AB_PATCH_APPLIED" if after != before
              else "STAGE42_GUEST_AB_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as error:
        print("STAGE42_GUEST_AB_PATCH_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
