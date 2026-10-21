#!/usr/bin/env python3
"""Read NRO0 segment arithmetic to isolate NeXium's bounds-check failure.

This does not patch a private NRO, alter checksums, or declare a ROM valid.
Header fields follow the exact pinned nexium-loader NroHeader::from_bytes
layout at NRO0 magic offset 16; report both raw file and sliced-body bounds.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def u32(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<I", buf, offset)[0]


def layout(payload: bytes) -> dict:
    if len(payload) < 144 or payload[16:20] != b"NRO0":
        raise ValueError("missing NRO0 header at offset 16")
    start = 16
    body_length = len(payload) - start
    segments = {}
    for name, offset_field in (("text", 16), ("ro", 24), ("data", 32)):
        offset = u32(payload, start + offset_field)
        size = u32(payload, start + offset_field + 4)
        adjusted_offset = offset + 128 if offset < 128 else offset
        end = adjusted_offset + size
        segments[name] = {
            "header_offset": offset, "adjusted_offset": adjusted_offset,
            "size": size, "end": end,
            "fits_nexium_sliced_nro_body": end <= body_length,
            "fits_original_full_nro_file": end <= len(payload),
            "offset_to_sliced_body_end": body_length - end,
            "offset_to_full_file_end": len(payload) - end,
        }
    return {
        "schema": "nexium-intel-public-nro-segment-layout/v1",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "file_length": len(payload),
        "nro_magic_at_file_offset": start,
        "nexium_parser_sliced_body_length": body_length,
        "declared_nro_size": u32(payload, start + 8),
        "nro_version": u32(payload, start + 4),
        "segments": segments,
        "data_end_crosses_only_the_first_16_bytes_of_slicing": (
            not segments["data"]["fits_nexium_sliced_nro_body"]
            and segments["data"]["fits_original_full_nro_file"]
        ),
        "note": "Structural arithmetic only; no validity or guest execution claim.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = layout(args.nro.read_bytes())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
