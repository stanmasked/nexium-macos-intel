"""Synthetic wrapped NRO header layout tests; no game bytes."""
import importlib.util
from pathlib import Path
import struct
import unittest

FILE = Path(__file__).with_name("inspect_layout.py")
spec = importlib.util.spec_from_file_location("nro_layout_probe", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def synthetic(data_end: int, file_length: int = 0x200) -> bytes:
    payload = bytearray(file_length)
    payload[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", payload, 0x18, file_length)
    for offset, start, size in ((0x20, 0x80, 0x40),
                                (0x28, 0xc0, 0x40),
                                (0x30, 0x100, data_end - 0x100)):
        struct.pack_into("<II", payload, offset, start, size)
    return bytes(payload)


class SegmentBoundsTests(unittest.TestCase):
    def test_full_file_end_is_not_same_as_nro_body_end(self):
        parsed = module.layout(synthetic(0x200))
        data = parsed["segments"]["data"]
        self.assertEqual(parsed["file_length"], 0x200)
        self.assertEqual(parsed["nexium_parser_sliced_body_length"], 0x1f0)
        self.assertFalse(data["fits_nexium_sliced_nro_body"])
        self.assertTrue(data["fits_original_full_nro_file"])
        self.assertEqual(data["offset_to_sliced_body_end"], -16)
        self.assertTrue(parsed["data_end_crosses_only_the_first_16_bytes_of_slicing"])

    def test_standard_interior_data_end_passes_both_bounds(self):
        parsed = module.layout(synthetic(0x1a0))
        self.assertTrue(parsed["segments"]["data"]["fits_nexium_sliced_nro_body"])
        self.assertFalse(parsed["data_end_crosses_only_the_first_16_bytes_of_slicing"])

    def test_genuinely_truncated_segment_fails_both_bounds(self):
        parsed = module.layout(synthetic(0x210))
        self.assertFalse(parsed["segments"]["data"]["fits_nexium_sliced_nro_body"])
        self.assertFalse(parsed["segments"]["data"]["fits_original_full_nro_file"])

    def test_missing_or_truncated_nro0_rejected(self):
        for body in (b"NRO0", bytes(144)):
            with self.assertRaisesRegex(ValueError, "missing NRO0"):
                module.layout(body)


if __name__ == "__main__":
    unittest.main()
