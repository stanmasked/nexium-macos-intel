#!/usr/bin/env python3
"""Stage39 opt-in early-return SDL3 cutpoints; no production default changes.

Return None before one pinned InputBackend initializer anchor. Every cutpoint
preserves all preceding real operations, but returning may trigger SDL cleanup;
observed survival/crashes are contrasts, not proof of a native root cause.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from apply_macos_sdl3_subphase_trace import START, END, PHASES

PREFIX = "STAGE39_SDL3_STOP_BEFORE_"
CHOICES = (
    ("hints", PHASES[0][1]),
    ("init", PHASES[1][1]),
    ("gamepad", PHASES[2][1]),
    ("rumble", PHASES[3][1]),
    ("struct", PHASES[4][1]),
)

def guard(name: str) -> str:
    return (
        '        #[cfg(target_os = "macos")]\n'
        '        if std::env::var("NEXIUM_MACOS_SDL3_STOP_BEFORE")\n'
        f'            .ok().as_deref() == Some("{name}")\n'
        '        {\n'
        f'            eprintln!("{PREFIX}{name.upper()}");\n'
        '            return None;\n'
        '        }\n'
    )

def patch_source(source: str) -> str:
    """Fail closed on unknown, incomplete or reordered source instrumentation."""
    if PREFIX in source:
        if all(source.count(guard(name)) == 1 for name, _ in CHOICES) and (
            source.count(PREFIX) == len(CHOICES)
        ):
            return source
        raise ValueError("partial Stage39 cutpoint instrumentation")
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("pinned InputBackend::new section boundary missing")
    if source.count("STAGE38_SDL3_INPUT_") != 5:
        raise ValueError("Stage38 ordered trace must already be installed")
    head, tail = source.split(START, 1)
    body, suffix = tail.split(END, 1)
    body = START + body
    offsets = [body.find(anchor) for _, anchor in CHOICES]
    if any(pos < 0 for pos in offsets) or offsets != sorted(set(offsets)):
        raise ValueError("pinned SDL3 cutpoint order missing or changed")
    for name, anchor in CHOICES:
        if body.count(anchor) != 1:
            raise ValueError("ambiguous source anchor: " + name)
        body = body.replace(anchor, guard(name) + anchor, 1)
    return head + body + END + suffix

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args(argv)
    target = args.checkout / "nexium-gui/src/input.rs"
    try:
        old = target.read_text(encoding="utf-8")
        new = patch_source(old)
        if new != old:
            target.write_text(new, encoding="utf-8")
        print("STAGE39_SDL3_CUTPOINT_PATCH_APPLIED" if new != old
              else "STAGE39_SDL3_CUTPOINT_PATCH_IDEMPOTENT")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print("STAGE39_SDL3_CUTPOINT_BLOCKED: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
