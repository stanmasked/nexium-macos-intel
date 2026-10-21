#!/usr/bin/env python3
"""Stage57: check Mach-O segment/section bounds beyond Stage56 load commands.

Run only against the exact local Intel binary used by Stage54-56. No binary
contents, file paths or private data are included in stdout or artifacts.
Structural checks do not authenticate a Mach-O, verify a signature, or prove
that a physical controller, commercial game, or Nintendo Switch was tested.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

from audit_intel_controller_proof_structure import (
    LC_SEGMENT_64, _identity, validate_macho,
)

SEGMENT64_FORMAT = "<II16sQQQQiiII"
SECTION64_FORMAT = "<16s16sQQIIIIIIII"
SEGMENT64_SIZE = struct.calcsize(SEGMENT64_FORMAT)
SECTION64_SIZE = struct.calcsize(SECTION64_FORMAT)
ZERO_FILL_TYPES = frozenset((0x1, 0xC, 0x12))
SECTION_TYPE_MASK = 0xFF


def verify_segment_bounds(binary: Path) -> dict:
    before = _identity(binary)
    # Stage56 checks the x86_64 MH_EXECUTE header, command table bounds,
    # alignment and the presence of a 64-bit segment.
    commands = validate_macho(binary)
    file_size = before[2]
    with binary.open("rb") as source:
        header = source.read(32)
        command_count = struct.unpack_from("<I", header, 16)[0]
        if command_count != commands:
            raise ValueError("Mach-O command count changed while inspecting")
        command_pos = 32
        segments_seen = 0
        sections_seen = 0
        file_backed_segments = 0
        for _ in range(commands):
            source.seek(command_pos)
            command_data = source.read(8)
            if len(command_data) != 8:
                raise ValueError("Mach-O command header truncated")
            kind, command_size = struct.unpack("<II", command_data)
            if kind == LC_SEGMENT_64:
                source.seek(command_pos)
                fields = source.read(SEGMENT64_SIZE)
                if len(fields) != SEGMENT64_SIZE:
                    raise ValueError("Mach-O 64-bit segment structure truncated")
                (_, _, _, _, _, seg_fileoff, seg_filesize,
                 _, _, nsects, _) = struct.unpack(SEGMENT64_FORMAT, fields)
                if nsects > (command_size - SEGMENT64_SIZE) // SECTION64_SIZE:
                    raise ValueError("Mach-O section count exceeds segment command")
                if seg_fileoff > file_size or seg_filesize > file_size - seg_fileoff:
                    raise ValueError("Mach-O segment file span outside binary")
                if seg_filesize:
                    file_backed_segments += 1
                segments_seen += 1

                for index in range(nsects):
                    source.seek(command_pos + SEGMENT64_SIZE +
                                index * SECTION64_SIZE)
                    section_data = source.read(SECTION64_SIZE)
                    if len(section_data) != SECTION64_SIZE:
                        raise ValueError("Mach-O section structure truncated")
                    sec = struct.unpack(SECTION64_FORMAT, section_data)
                    sect_size = sec[3]
                    sect_off = sec[4]
                    sect_type = sec[8] & SECTION_TYPE_MASK
                    if sect_size and sect_type not in ZERO_FILL_TYPES:
                        if (sect_off < seg_fileoff or
                                sect_off > file_size or
                                sect_size > file_size - sect_off or
                                sect_off - seg_fileoff > seg_filesize or
                                sect_size > seg_filesize -
                                (sect_off - seg_fileoff)):
                            raise ValueError("Mach-O file-backed section out of bounds")
                    sections_seen += 1
            command_pos += command_size
    if file_backed_segments == 0:
        raise ValueError("Intel executable contains no file-backed segments")
    if before != _identity(binary):
        raise ValueError("Intel executable changed during segment audit")
    return {
        "schema": "nexium-intel-macho-segment-bounds/v1",
        "segment_bounds_passed": True,
        "segments_checked": segments_seen,
        "sections_checked": sections_seen,
        "physical_controller_verified": False,
        "production_release_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intel-binary", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify_segment_bounds(args.intel_binary),
                         sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError, struct.error) as error:
        print("STAGE57_MACHO_SEGMENTS_BLOCKED: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
