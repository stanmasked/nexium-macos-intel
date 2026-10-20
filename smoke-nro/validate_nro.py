#!/usr/bin/env python3
"""Structural gate for our public, locally built libnx Nintendo Switch NRO.

Checking the NRO0 header is not an emulator execution test.
No private assets, keys, ROMs, or Nintendo firmware are needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect_nro(path: Path) -> dict:
    payload = path.read_bytes()
    if len(payload) < 0x40:
        raise ValueError("NRO header truncated")
    if payload[0x10:0x14] != b"NRO0":
        raise ValueError("NRO magic missing at byte 0x10")
    declared_size = struct.unpack_from("<I", payload, 0x18)[0]
    if declared_size < 0x40 or declared_size > len(payload):
        raise ValueError(f"invalid NRO image-size field {declared_size}")
    return {
        "name": path.name,
        "kind": "nro0_homebrew",
        "actual_bytes": len(payload),
        "declared_image_bytes": declared_size,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "runtime_test": "not_performed",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nro", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_nro(args.nro)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
