"""Stage57 structural Mach-O bounds fixtures; all bytes synthetic and public."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_intel_macho_segment_bounds import (
    verify_segment_bounds, SEGMENT64_SIZE, SECTION64_SIZE,
)


class Stage57MachOSegmentBoundsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.binary = Path(tmp.name) / "fake-intel-mach-o"
        # 32-byte Mach-O + LC_SEGMENT_64 with one section_64 + 32 data bytes.
        self.data_start = 32 + SEGMENT64_SIZE + SECTION64_SIZE
        self.assertEqual((SEGMENT64_SIZE, SECTION64_SIZE), (72, 80))
        payload_size = self.data_start + 32
        header = struct.pack("<8I", 0xFEEDFACF, 0x01000007,
                             3, 2, 1, SEGMENT64_SIZE + SECTION64_SIZE,
                             0, 0)
        segment = struct.pack(
            "<II16sQQQQiiII",
            0x19, SEGMENT64_SIZE + SECTION64_SIZE, b"__TEXT",
            0x1000, 0x1000, 0, payload_size,
            5, 5, 1, 0,
        )
        section = struct.pack(
            "<16s16sQQIIIIIIII",
            b"__text", b"__TEXT",
            0x1000, 16, self.data_start, 4,
            0, 0, 0, 0, 0, 0,
        )
        self.binary.write_bytes(header + segment + section + b"\x90" * 32)

    def poke(self, offset: int, value: int, fmt="<I"):
        data = bytearray(self.binary.read_bytes())
        struct.pack_into(fmt, data, offset, value)
        self.binary.write_bytes(data)

    def test_valid_file_backed_section_passes(self):
        result = verify_segment_bounds(self.binary)
        self.assertTrue(result["segment_bounds_passed"])
        self.assertEqual(result["segments_checked"], 1)
        self.assertEqual(result["sections_checked"], 1)
        self.assertFalse(result["physical_controller_verified"])

    def test_oversized_section_count_rejected(self):
        self.poke(32 + 64, 2)
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_segment_file_offset_past_eof_rejected(self):
        self.poke(32 + 40, 1000, "<Q")
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_segment_file_size_past_eof_rejected(self):
        self.poke(32 + 48, self.data_start + 1024, "<Q")
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_section_offset_past_eof_rejected(self):
        self.poke(32 + SEGMENT64_SIZE + 48, 1000)
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_section_size_past_eof_rejected(self):
        self.poke(32 + SEGMENT64_SIZE + 40, 900, "<Q")
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_section_before_segment_fileoff_rejected(self):
        self.poke(32 + 40, self.data_start + 1, "<Q")
        self.poke(32 + 48, 31, "<Q")
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_section_past_parent_segment_within_file_rejected(self):
        self.poke(32 + 48, self.data_start + 7, "<Q")
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_zerofill_section_without_file_bytes_allowed(self):
        self.poke(32 + SEGMENT64_SIZE + 40, 0x2000, "<Q")
        self.poke(32 + SEGMENT64_SIZE + 48, 0)
        self.poke(32 + SEGMENT64_SIZE + 64, 0x1)
        result = verify_segment_bounds(self.binary)
        self.assertTrue(result["segment_bounds_passed"])

    def test_thread_local_zerofill_allowed(self):
        self.poke(32 + SEGMENT64_SIZE + 40, 0x100, "<Q")
        self.poke(32 + SEGMENT64_SIZE + 48, 0)
        self.poke(32 + SEGMENT64_SIZE + 64, 0x12)
        self.assertTrue(verify_segment_bounds(self.binary)["segment_bounds_passed"])

    def test_no_file_backed_segment_rejected(self):
        self.poke(32 + 48, 0, "<Q")
        self.poke(32 + SEGMENT64_SIZE + 40, 0, "<Q")
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_damaged_x86_64_header_rejected_by_predecessor(self):
        self.poke(4, 0x0100000C)
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)

    def test_missing_segment_command_rejected_by_predecessor(self):
        self.poke(32, 0x1B)
        with self.assertRaises(ValueError):
            verify_segment_bounds(self.binary)


if __name__ == "__main__":
    unittest.main()
