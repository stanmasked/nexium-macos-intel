#!/usr/bin/env python3
"""Stage67: prove original public libnx framebuffer test *compiles*, not renders.

Header and embedded source marker identities are required; this program
deliberately cannot infer guest VI/Nv services, frame presentation, real
on-screen pixels or emulator compatibility from compilation alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from audit_intel_controller_proof_structure import validate_nro

MAX_PUBLIC_NRO = 2 * 1024 * 1024
EXPECTED_MARKERS = (
    "STAGE67_GUEST_GRAPHICS_START",
    "STAGE67_GUEST_DEFAULT_WINDOW_OBTAINED",
    "STAGE67_GUEST_FRAMEBUFFER_CREATED",
    "STAGE67_GUEST_LINEAR_BUFFER_READY",
    "STAGE67_GUEST_CHECKERBOARD_A_WRITTEN",
    "STAGE67_GUEST_CHECKERBOARD_B_WRITTEN",
    "STAGE67_GUEST_FRAME_A_PRESENTED_CALL_RETURNED",
    "STAGE67_GUEST_FRAME_B_PRESENTED_CALL_RETURNED",
    "STAGE67_GUEST_FOUR_FRAMEBUFFER_CALLS_COMPLETE",
    "STAGE67_GUEST_WINDOW_UNAVAILABLE",
    "STAGE67_GUEST_FRAMEBUFFER_CREATE_FAILED",
    "STAGE67_GUEST_FRAMEBUFFER_LINEAR_FAILED",
    "STAGE67_GUEST_APPLET_EXIT_BEFORE_FRAMES",
    "STAGE67_GUEST_FRAMEBUFFER_BEGIN_FAILED",
)
REQUIRED_APIS = (
    "nwindowGetDefault(",
    "framebufferCreate(",
    "framebufferMakeLinear(",
    "framebufferBegin(",
    "framebufferEnd(",
    "framebufferClose(",
    "svcOutputDebugString(",
)
SOURCE_API_ORDER = (
    "NWindow *win = nwindowGetDefault();",
    "const Result create = framebufferCreate(",
    "const Result linear = framebufferMakeLinear(&fb);",
    "void *pixels = framebufferBegin(&fb, &stride);",
    "framebufferEnd(&fb);",
)


def verify_graphics_source(text: str) -> None:
    if not isinstance(text, str) or len(text) > 30000:
        raise ValueError("graphics probe source missing or oversized")
    if any(text.count('mark("' + m) != 1 for m in EXPECTED_MARKERS):
        raise ValueError("expected one exact graphics source marker per state")
    if any(api not in text for api in REQUIRED_APIS):
        raise ValueError("original libnx framebuffer calls missing")
    loc = [text.find(fragment) for fragment in SOURCE_API_ORDER]
    if -1 in loc or loc != sorted(loc):
        raise ValueError("guest graphics source call order changed")
    if ("R_FAILED(create)" not in text or "R_FAILED(linear)" not in text
            or "stride < FB_WIDTH * sizeof(u32)" not in text
            or "draw_checkerboard(pixels, stride, frame);" not in text
            or "framebufferEnd(&fb);" not in text):
        raise ValueError("guest framebuffer failure or pixel safeguards removed")
    if "framebufferClose(&fb);" not in text:
        raise ValueError("guest framebuffer release missing")


def validate_compiled_public_probe(path: Path, source: Path) -> dict:
    if (path.is_symlink() or not path.is_file() or path.suffix != ".nro"
            or source.is_symlink() or not source.is_file()):
        raise ValueError("expected direct public NRO and source files")
    if not 0 < path.stat().st_size <= MAX_PUBLIC_NRO:
        raise ValueError("public graphics NRO exceeds bounded size")
    verify_graphics_source(source.read_text(encoding="utf-8"))
    declared = validate_nro(path)
    blob = path.read_bytes()
    data = blob[:declared]
    for marker in EXPECTED_MARKERS:
        if data.count(marker.encode("ascii")) != 1:
            raise ValueError("compiled graphics NRO omitted required marker")
    return {
        "schema": "nexium-stage67-public-graphics-guest-build/v1",
        "libnx_public_graphics_probe_compiled": True,
        "nro_declared_bytes": declared,
        "nro_sha256": hashlib.sha256(blob).hexdigest(),
        "source_authentic_libnx_api_calls_verified": True,
        "guest_runtime_executed": False,
        "guest_framebuffer_initialized": False,
        "guest_frames_presented_verified": False,
        "macos_window_pixels_verified": False,
        "production_graphics_verified": False,
        "commercial_gameplay_verified": False,
        "raw_data_uploaded": False,
        "main_merge_approved": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guest-nro", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(validate_compiled_public_probe(args.guest_nro, args.source),
                         sort_keys=True))
        print("STAGE67_PUBLIC_GRAPHICS_NRO_BUILD_PASS_RUNTIME_NOT_TESTED")
        return 0
    except (ValueError, OSError, UnicodeError):
        print("STAGE67_PUBLIC_GRAPHICS_NRO_BUILD_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
