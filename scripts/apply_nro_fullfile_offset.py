#!/usr/bin/env python3
"""Stage33: strictly scoped NeXium NRO0 full-file segment-offset correction.

NRO0 magic is at file offset 0x10 in standard libnx/switchbrew NROs.
The first 16-byte NroStart is part of .text and segment file_off fields
are relative to the ORIGINAL file, not a sliced buffer starting at 0x10.
Do not alter user NROs, bypass bounds, or patch non-NRO containers.
Research-only until native Intel actual NRO boot has been verified.
"""
from pathlib import Path
import argparse
import sys

OLD_HEADER = '''        let nro_offset = Self::detect_nro_offset(&mmap)?;
        let nro_slice = &mmap[nro_offset..];
        let header = NroHeader::from_bytes(nro_slice)?;'''
NEW_HEADER = '''        let nro_offset = Self::detect_nro_offset(&mmap)?;
        // Official NRO0 has a 16-byte NroStart at file offset zero.
        // Its NRO0 magic is at 0x10, but all segment file_off values
        // remain relative to the beginning of the FULL NRO image.
        let standard_nro_start = nro_offset == 16;
        let file_origin = if standard_nro_start { 0 } else { nro_offset };
        let nro_slice = &mmap[file_origin..];
        let header = NroHeader::from_bytes(&mmap[nro_offset..])?;'''

OLD_SEGMENTS = '''        const HEADER_SIZE: u32 = 128;
        let text_offset = if header.text_offset < HEADER_SIZE {
            header.text_offset + HEADER_SIZE
        } else {
            header.text_offset
        };
        let ro_offset = if header.ro_offset < HEADER_SIZE {
            header.ro_offset + HEADER_SIZE
        } else {
            header.ro_offset
        };
        let data_offset = if header.data_offset < HEADER_SIZE {
            header.data_offset + HEADER_SIZE
        } else {
            header.data_offset
        };'''
NEW_SEGMENTS = '''        const HEADER_SIZE: u32 = 128;
        // Standard NRO0 .text starts at offset 0 and includes NroStart,
        // unlike old experimental magic-at-zero header-only fixtures.
        let text_offset = if standard_nro_start {
            header.text_offset
        } else if header.text_offset < HEADER_SIZE {
            header.text_offset + HEADER_SIZE
        } else {
            header.text_offset
        };
        let ro_offset = if standard_nro_start {
            header.ro_offset
        } else if header.ro_offset < HEADER_SIZE {
            header.ro_offset + HEADER_SIZE
        } else {
            header.ro_offset
        };
        let data_offset = if standard_nro_start {
            header.data_offset
        } else if header.data_offset < HEADER_SIZE {
            header.data_offset + HEADER_SIZE
        } else {
            header.data_offset
        };'''

OLD_BOUNDS = '''        if (text_offset + header.text_size) as usize > nro_slice.len() {
            return Err("Text segment out of bounds".to_string());
        }
        if (ro_offset + header.ro_size) as usize > nro_slice.len() {
            return Err("RO segment out of bounds".to_string());
        }
        if (data_offset + header.data_size) as usize > nro_slice.len() {
            return Err("Data segment out of bounds".to_string());
        }'''
NEW_BOUNDS = '''        // NRO header size excludes optional appended ASET resources.
        // Reject genuinely truncated images and segments reaching into assets.
        let image_limit = if standard_nro_start {
            let declared = header.size as usize;
            if declared < HEADER_SIZE as usize || declared > nro_slice.len() {
                return Err("NRO declared image size out of bounds".to_string());
            }
            declared
        } else {
            nro_slice.len()
        };
        if (text_offset as usize).checked_add(header.text_size as usize)
            .is_none_or(|end| end > image_limit)
        {
            return Err("Text segment out of bounds".to_string());
        }
        if (ro_offset as usize).checked_add(header.ro_size as usize)
            .is_none_or(|end| end > image_limit)
        {
            return Err("RO segment out of bounds".to_string());
        }
        if (data_offset as usize).checked_add(header.data_size as usize)
            .is_none_or(|end| end > image_limit)
        {
            return Err("Data segment out of bounds".to_string());
        }'''

RANGE_REWRITES = (
    ("(nro_offset + text_offset as usize)", "(file_origin + text_offset as usize)"),
    ("(nro_offset + (text_offset + header.text_size) as usize)",
     "(file_origin + text_offset as usize + header.text_size as usize)"),
    ("(nro_offset + ro_offset as usize)", "(file_origin + ro_offset as usize)"),
    ("(nro_offset + (ro_offset + header.ro_size) as usize)",
     "(file_origin + ro_offset as usize + header.ro_size as usize)"),
    ("(nro_offset + data_offset as usize)", "(file_origin + data_offset as usize)"),
    ("(nro_offset + (data_offset + header.data_size) as usize)",
     "(file_origin + data_offset as usize + header.data_size as usize)"),
)


def patch(source: str) -> str:
    if NEW_HEADER in source:
        if NEW_SEGMENTS not in source or NEW_BOUNDS not in source:
            raise RuntimeError("partial Stage33 NRO loader patch")
        for before, after in RANGE_REWRITES:
            if before in source or after not in source:
                raise RuntimeError("Stage33 segment range drift")
        return source
    if source.count("pub fn parse_mmap(mmap: Arc<Mmap>) -> Result<Self, String> {") != 1:
        raise RuntimeError("pinned parse_mmap NRO entry missing")
    for name, expected in (("header", OLD_HEADER), ("segments", OLD_SEGMENTS),
                           ("strict-bounds", OLD_BOUNDS)):
        if source.count(expected) != 1:
            raise RuntimeError(f"pinned NRO {name} anchor missing or duplicated")
    for old, _ in RANGE_REWRITES:
        if source.count(old) != 1:
            raise RuntimeError("NRO segment range anchor missing or duplicated")
    source = source.replace(OLD_HEADER, NEW_HEADER, 1)
    source = source.replace(OLD_SEGMENTS, NEW_SEGMENTS, 1)
    source = source.replace(OLD_BOUNDS, NEW_BOUNDS, 1)
    for old, new in RANGE_REWRITES:
        source = source.replace(old, new, 1)
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    target = args.checkout / "nexium-loader/src/nro.rs"
    try:
        original = target.read_text(encoding="utf-8")
        modified = patch(original)
        if modified != original:
            target.write_text(modified, encoding="utf-8")
        print("STAGE33_NRO_FILE_ORIGIN_APPLIED" if modified != original
              else "STAGE33_NRO_FILE_ORIGIN_ALREADY_APPLIED")
    except (OSError, UnicodeError, RuntimeError) as err:
        print(f"STAGE33_NRO_FILE_ORIGIN_BLOCKED: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
