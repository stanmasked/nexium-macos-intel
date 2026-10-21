"""Stage35 privacy/source-authenticity receipt regression tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stage35_full_gui_window_pixels as source


def frame(digest="a"*64, size=33000):
    return {"file":"/some/private/user/window.png",
            "sha256":digest, "dimensions":[832,620],"bytes":size}


class Stage35WindowPrivacy(unittest.TestCase):
    def test_no_capture_never_claims_frame_proof(self):
        d=source.receipt({"frames":[],"errors":["permission denied"]},
                         "full-preinitialized-sdl3",source.SOURCE_SHA,False,True)
        self.assertEqual(d["capture_status"],"no_window_png")
        self.assertEqual(d["valid_png_count"],0)
        self.assertEqual(d["capture_error_count"],1)
        self.assertFalse(d["gui_content_correctness_verified"])

    def test_only_metadata_no_paths_or_raw_png(self):
        d=source.receipt({"frames":[frame()]},"full-preinitialized-sdl3",
                         source.SOURCE_SHA,False,True)
        self.assertEqual(d["valid_png_count"],1)
        self.assertNotIn("/some/private",str(d))
        self.assertFalse(d["raw_pngs_uploaded"])
        self.assertFalse(d["desktop_captured"])
        self.assertFalse(d["nro_executed"])

    def test_identical_shas_do_not_claim_dynamic_game(self):
        d=source.receipt({"frames":[frame(),frame()]},
                         "full-preinitialized-sdl3",source.SOURCE_SHA,False,True)
        self.assertEqual(d["unique_frame_hashes"],1)
        self.assertFalse(d["vandal_hearts_game_verified"])

    def test_different_shas_are_only_hash_difference(self):
        d=source.receipt({"frames":[frame(),frame("b"*64)]},
                         "minimal-eframe",source.SOURCE_SHA,False,True)
        self.assertEqual(d["unique_frame_hashes"],2)
        self.assertFalse(d["gui_content_correctness_verified"])

    def test_reject_wrong_binary(self):
        with self.assertRaisesRegex(ValueError,"wrong original"):
            source.receipt({"frames":[]},source.MODES[0],"b"*64,False,False)

    def test_reject_unknown_mode(self):
        with self.assertRaisesRegex(ValueError,"invalid original"):
            source.receipt({"frames":[]},"desktop",source.SOURCE_SHA,False,False)

    def test_drop_malformed_and_tiny_frame_metadata(self):
        d=source.receipt({"frames":[None,{},frame("z"*64),
                 {"sha256":"a"*64,"dimensions":[1,999],"bytes":10000},
                 {"sha256":"a"*64,"dimensions":[400,300],"bytes":2},
                 {"sha256":"c"*64,"dimensions":[450,360],"bytes":11538}]},
                 "minimal-eframe",source.SOURCE_SHA,False,True)
        self.assertEqual(d["valid_png_count"],1)
        self.assertEqual(d["frames"][0]["sha256"],"c"*64)

    def test_early_exit_is_not_window_success(self):
        d=source.receipt({"frames":[]},source.MODES[0],source.SOURCE_SHA,True,False)
        self.assertTrue(d["process_exited_before_capture"])
        self.assertFalse(d["process_alive_after_capture"])
        self.assertEqual(d["capture_status"],"no_window_png")

    def test_source_modes_distinct(self):
        self.assertEqual(len(set(source.MODES)),2)
        self.assertIn("full-preinitialized-sdl3",source.MODES)
        self.assertIn("minimal-eframe",source.MODES)

if __name__=="__main__":
    unittest.main()
