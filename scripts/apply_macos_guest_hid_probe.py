#!/usr/bin/env python3
"""Stage40: extend the existing synthetic B hold only for guest HID testing.

This modifies the already-pinned Stage36 virtual-pad fixture. Normal Stage36-
38 runs retain the original 12-poll press. With the dedicated Stage40 runtime
environment flag, the press lasts 900 original InputBackend polls so a guest
NRO has time to initialize and read it. No guest state is injected directly.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

OLD_DOWN = "let down = n >= 1 && n < 12;"
NEW_DOWN = """let hold_ticks = if std::env::var("NEXIUM_MACOS_GUEST_HID_PROBE")
                .ok().as_deref() == Some("1")
            {
                900
            } else {
                12
            };
            let down = n >= 1 && n < hold_ticks;"""
OLD_RELEASE = "else if n == 12 {"
NEW_RELEASE = "else if n == hold_ticks {"


def patch_source(source: str) -> str:
    if NEW_DOWN in source or NEW_RELEASE in source:
        if source.count(NEW_DOWN) == 1 and source.count(NEW_RELEASE) == 1:
            return source
        raise RuntimeError("Stage40 partial or duplicate long-hold instrumentation")
    if source.count(OLD_DOWN) != 1 or source.count(OLD_RELEASE) != 1:
        raise RuntimeError("original Stage36 virtual-button hold anchors absent or doubled")
    updated = source.replace(OLD_DOWN, NEW_DOWN, 1).replace(OLD_RELEASE, NEW_RELEASE, 1)
    if updated.count("NEXIUM_MACOS_GUEST_HID_PROBE") != 1:
        raise RuntimeError("Stage40 guest-only hold gate is not unique")
    return updated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    path = args.source / "nexium-gui/src/input.rs"
    try:
        original = path.read_text(encoding="utf-8")
        updated = patch_source(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
        print("STAGE40_GUEST_HID_LONG_HOLD_PATCHED" if updated != original
              else "STAGE40_GUEST_HID_LONG_HOLD_ALREADY_PATCHED")
        return 0
    except (OSError, UnicodeError, RuntimeError) as error:
        print("STAGE40_GUEST_HID_LONG_HOLD_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
