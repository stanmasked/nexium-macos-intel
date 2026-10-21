"""Stage43 tests: real decoded pixels, genuine source markers, no private data."""
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import probe_stage43_owned_window_pixels as stage


class Stage43ImageTests(unittest.TestCase):
    def test_valid_nonuniform_decoded_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private.png"
            image = Image.new("RGB", (640, 480), color=(0,0,0))
            px=image.load()
            for y in range(480):
                for x in range(640):
                    if x < 320:
                        px[x,y]=(240,40,30) if y<240 else (20,200,40)
                    else:
                        px[x,y]=(40,30,230) if y<240 else (250,250,250)
            image.save(path, "PNG")
            output=stage.evaluate_pixels(path)
            self.assertTrue(output["spatially_nonuniform"])
            self.assertEqual(output["width"],640)
            self.assertEqual(output["height"],480)
            self.assertNotIn("private",str(output))

    def test_black_solid_png_not_real_ui_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"black.png"
            Image.new("RGB",(640,480),(0,0,0)).save(path,"PNG")
            output=stage.evaluate_pixels(path)
            self.assertEqual(output["sampled_unique_rgb_colors"],1)
            self.assertFalse(output["spatially_nonuniform"])

    def test_colored_solid_png_not_real_ui_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"solid.png"
            Image.new("RGB",(640,480),(255,30,40)).save(path,"PNG")
            output=stage.evaluate_pixels(path)
            self.assertFalse(output["spatially_nonuniform"])

    def test_invalid_png_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"broken.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not decoded pixels")
            with self.assertRaises((OSError,SyntaxError)):
                stage.evaluate_pixels(path)

    def test_too_small_image_is_not_gui_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"small.png"
            Image.new("RGB",(120,80),(40,40,40)).save(path,"PNG")
            with self.assertRaisesRegex(ValueError,"small"):
                stage.evaluate_pixels(path)

    def test_oversized_declared_image_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"too-wide.png"
            Image.new("RGB",(8193,200),(40,40,40)).save(path,"PNG")
            with self.assertRaisesRegex(ValueError,"large"):
                stage.evaluate_pixels(path)

    def test_expected_source_flags(self):
        log="\n".join("STAGE40_"+p for p in ()) + "\n" + "\n".join(stage.MARKERS)
        result=stage.extract_source_flags(log)
        for name in ("sdl3_before_eframe","sdl3_preinitialized",
                     "same_thread_input_consumed","original_ui_entered",
                     "sdl3_input_poll_returned"):
            self.assertTrue(result[name])

    def test_only_line_exact_source_markers(self):
        result=stage.extract_source_flags(
            "user wrote STAGE40_PREWARM_MAIN_READY\n"
            "STAGE40_PREWARM_MAIN_READY with private data\n")
        self.assertFalse(result["sdl3_preinitialized"])

    def test_private_data_never_emitted(self):
        result=stage.extract_source_flags(
            "STAGE42_FULL_UI_ENTERED\n"
            "/Users/private/MySecretFile.nro\n"
            "TOKEN=secret\nKEYDOWN=A\n")
        self.assertTrue(result["original_ui_entered"])
        self.assertNotIn("MySecretFile",repr(result))
        self.assertNotIn("KEYDOWN",repr(result))

    def test_unseen_actual_poll_not_conflated_with_window(self):
        result=stage.extract_source_flags(
            "STAGE40_PREWARM_MAIN_READY\nSTAGE42_FULL_UI_ENTERED\n")
        self.assertTrue(result["original_ui_entered"])
        self.assertFalse(result["sdl3_input_poll_returned"])

    def test_winit_panic_boolean_no_stderr(self):
        msg="tried to handle event while another event is currently being handled"
        result=stage.extract_source_flags(msg+"\n/Users/private\n")
        self.assertTrue(result["winit_reentrant_panic_detected"])
        self.assertNotIn(msg,repr(result))


if __name__=="__main__":
    unittest.main()
