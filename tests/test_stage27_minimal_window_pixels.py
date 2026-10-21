"""Stage27: no raw PNG / no outside-PID proofs in shared receipt."""
import importlib.util
from pathlib import Path
import unittest

modpath=Path(__file__).resolve().parents[1]/"scripts/stage27_minimal_window_pixels.py"
spec=importlib.util.spec_from_file_location("stage27",modpath)
stage=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class TestStage27ScopedPNG(unittest.TestCase):
    def test_no_images_retained_if_denied(self):
        r=stage.summarise_capture({"frames":[],"errors":["macOS access denied"]},
                                  stage.EXPECTED_SHA,False)
        self.assertEqual(r["capture_status"],"no_window_png_captured")
        self.assertEqual(r["valid_png_count"],0)
        self.assertFalse(r["original_pngs_uploaded"])

    def test_real_sha_required_for_provenance(self):
        r=stage.summarise_capture({"frames":[]}, "a"*64, False)
        self.assertFalse(r["original_stage25_binary_verified"])

    def test_valid_window_png_metadata_only(self):
        r=stage.summarise_capture({"frames":[{"file":"/secrets/window.png",
                 "sha256":"b"*64,"dimensions":[700,480],"bytes":17733}]},
                stage.EXPECTED_SHA, False)
        self.assertEqual(r["valid_png_count"],1)
        self.assertEqual(r["frames"][0]["sha256"],"b"*64)
        self.assertNotIn("/secrets",str(r))
        self.assertIsNone(r["window_content_is_correct_emulator_ui"])

    def test_reject_tiny_or_invalid_capture(self):
        r=stage.summarise_capture({"frames":[
            {"sha256":"z"*64,"dimensions":[200,200],"bytes":5000},
            {"sha256":"c"*64,"dimensions":[1,1],"bytes":5000},
            {"sha256":"d"*64,"dimensions":[500,400],"bytes":4},
        ]},stage.EXPECTED_SHA,False)
        self.assertEqual(r["valid_png_count"],0)

    def test_count_unique_hashes_without_claiming_frame_differences(self):
        a={"sha256":"a"*64,"dimensions":[500,350],"bytes":50200}
        b={"sha256":"b"*64,"dimensions":[500,350],"bytes":50300}
        r=stage.summarise_capture({"frames":[a,a,b]},stage.EXPECTED_SHA,False)
        self.assertEqual(r["valid_png_count"],3)
        self.assertEqual(r["unique_png_hashes"],2)
        self.assertFalse(r["gameplay_verified"])

    def test_process_early_exit_explicit(self):
        r=stage.summarise_capture({"frames":[]},stage.EXPECTED_SHA,True)
        self.assertTrue(r["process_exited_before_window_capture"])
        self.assertFalse(r["gameplay_verified"])

    def test_invalid_frame_structure_rejected(self):
        r=stage.summarise_capture({"frames":[{},None]},stage.EXPECTED_SHA,False)
        self.assertEqual(r["valid_png_count"],0)

if __name__=="__main__":
    unittest.main()
