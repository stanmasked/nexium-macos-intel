"""Synthetic-only validation for the privacy-scoped macOS window collector."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/capture_macos_window.py"
spec = importlib.util.spec_from_file_location("window_capture_macos", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WindowCaptureTests(unittest.TestCase):
    def test_png_header_reports_dimensions_without_decoding_private_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "frame.png"
            path.write_bytes(
                module.PNG_MAGIC +
                (13).to_bytes(4, "big") + b"IHDR" +
                (1280).to_bytes(4, "big") + (720).to_bytes(4, "big")
            )
            self.assertEqual(module.png_dimensions(path), [1280, 720])

    def test_invalid_image_never_counts_as_frame(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "not-png.png"
            path.write_bytes(b"this is neither a png nor a screenshot")
            self.assertIsNone(module.png_dimensions(path))

    def test_nonexistent_pid_is_not_alive(self):
        # A negative PID should never be passed to os.kill because it can
        # target a process group. Check only nonexistent large positive PID.
        self.assertFalse(module.process_alive(2147483647))


if __name__ == "__main__":
    unittest.main()
