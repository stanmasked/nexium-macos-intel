#!/usr/bin/env python3
"""Stage56 fail-closed structural check of original CI proof input files.

Complements (not replaces) Stage54 hashes and Stage55 replay: verify a real
x86_64 MH_EXECUTE image with self-consistent load commands, a genuine NRO0
segment layout, and unambiguous privacy-limited Stage53 receipt JSON.

Passing only proves structural consistency, not executable authenticity,
runtime behavior, a physical controller, or a signed release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import struct
import sys

from audit_intel_controller_proof_manifest import read_sanitized_receipt

MAX_RECEIPT = 16384
MACH_MAGIC_64_LE = b"\xcf\xfa\xed\xfe"
CPU_TYPE_X86_64 = 0x01000007
MH_EXECUTE = 2
LC_SEGMENT_64 = 0x19


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError("proof input must be a direct regular file")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate receipt JSON property")
        result[key] = value
    return result


def _reject_nonfinite(_value: str):
    raise ValueError("non-finite JSON constant in receipt")


def validate_receipt(path: Path) -> int:
    if path.stat().st_size > MAX_RECEIPT:
        raise ValueError("receipt JSON exceeds sanitized size limit")
    receipt = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonfinite,
    )
    # The predecessor applies the complete Stage53 source/guest proof schema,
    # exact property allowlist, required Boolean values, and minimum samples.
    _, samples = read_sanitized_receipt(path)
    if not isinstance(receipt, dict):
        raise ValueError("sanitized receipt is not an object")
    return samples


def validate_macho(path: Path) -> int:
    size = path.stat().st_size
    if size < 32:
        raise ValueError("Intel executable header truncated")
    with path.open("rb") as stream:
        header = stream.read(32)
        if header[:4] != MACH_MAGIC_64_LE:
            raise ValueError("not a little-endian thin 64-bit Mach-O")
        _, cpu, _, kind, count, command_bytes, _, _ = struct.unpack("<8I", header)
        if cpu != CPU_TYPE_X86_64 or kind != MH_EXECUTE:
            raise ValueError("not an Intel x86_64 MH_EXECUTE image")
        if not 1 <= count <= 65536 or command_bytes < 8 * count:
            raise ValueError("Mach-O load command header invalid")
        if 32 + command_bytes > size:
            raise ValueError("Mach-O load commands truncated")

        offset = 32
        has_segment = False
        for _ in range(count):
            stream.seek(offset)
            command_header = stream.read(8)
            if len(command_header) != 8:
                raise ValueError("truncated Mach-O load command")
            kind, command_size = struct.unpack("<2I", command_header)
            if command_size < 8 or command_size % 8 != 0:
                raise ValueError("Mach-O load command length invalid")
            if offset + command_size > 32 + command_bytes:
                raise ValueError("Mach-O load command exceeds declared table")
            if kind == LC_SEGMENT_64:
                if command_size < 72:
                    raise ValueError("Mach-O 64-bit segment command truncated")
                has_segment = True
            offset += command_size
        if offset != 32 + command_bytes or not has_segment:
            raise ValueError("Mach-O commands incomplete or missing segments")
    return count


def validate_nro(path: Path) -> int:
    size = path.stat().st_size
    if size < 0x80:
        raise ValueError("NRO0 header truncated")
    with path.open("rb") as stream:
        header = stream.read(0x80)
    if header[0x10:0x14] != b"NRO0":
        raise ValueError("NRO0 magic invalid")

    declared_size = struct.unpack_from("<I", header, 0x18)[0]
    if declared_size < 0x80 or declared_size > size:
        raise ValueError("NRO declared file size invalid")
    segments = [struct.unpack_from("<II", header, off) for off in (0x20, 0x28, 0x30)]
    if segments[0][0] != 0 or segments[0][1] < 0x80:
        raise ValueError("NRO text segment does not contain header")
    previous_end = 0
    for off, length in segments:
        if length == 0 or off < previous_end or off + length > declared_size:
            raise ValueError("NRO segment missing, overlapping, or out of bounds")
        previous_end = off + length
    return declared_size


def audit_structure(binary: Path, nro: Path, receipt: Path) -> dict:
    inputs = (binary, nro, receipt)
    before = tuple(_identity(path) for path in inputs)
    command_count = validate_macho(binary)
    declared_nro = validate_nro(nro)
    samples = validate_receipt(receipt)
    if before != tuple(_identity(path) for path in inputs):
        raise ValueError("proof input changed during structural audit")
    return {
        "schema": "nexium-intel-controller-proof-structure/v1",
        "intel_macho_load_commands": command_count,
        "nro_declared_bytes": declared_nro,
        "sanitized_npad_samples": samples,
        "structure_audit_passed": True,
        "physical_controller_verified": False,
        "production_release_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intel-binary", type=Path, required=True)
    parser.add_argument("--guest-nro", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_structure(args.intel_binary, args.guest_nro, args.guest_receipt)
        # Only a tiny, source-independent summary appears in console output.
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        print("STAGE56_PROOF_STRUCTURE_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
