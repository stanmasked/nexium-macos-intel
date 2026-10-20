"""Synthetic header tests only. They do not prove guest execution."""
import tempfile
import unittest
from pathlib import Path
from validate_nro import inspect_nro


class HeaderTests(unittest.TestCase):
    def test_valid_header_reports_structural_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mock.nro"
            buf = bytearray(256)
            buf[0x10:0x14] = b"NRO0"
            buf[0x18:0x1c] = (256).to_bytes(4, "little")
            path.write_bytes(buf)
            result = inspect_nro(path)
            self.assertEqual(result["declared_image_bytes"], 256)
            self.assertEqual(result["runtime_test"], "not_performed")

    def test_corrupt_magic_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.nro"
            path.write_bytes(b"x" * 256)
            with self.assertRaises(ValueError):
                inspect_nro(path)

    def test_impossible_size_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "badsize.nro"
            buf = bytearray(256)
            buf[0x10:0x14] = b"NRO0"
            buf[0x18:0x1c] = (512).to_bytes(4, "little")
            path.write_bytes(buf)
            with self.assertRaises(ValueError):
                inspect_nro(path)


if __name__ == "__main__":
    unittest.main()
