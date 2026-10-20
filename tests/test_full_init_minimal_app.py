"""Positive and fail-closed negative tests for Stage25 pinned GUI ablation."""
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_full_init_minimal_app as stage25

SOURCE = '''fn main() {
    eprintln!("STAGE22_MINIMAL_EFRAME_ENTERED");
    let settings = AppSettings::load();
    let log_feed_for_app = log_feed;
    let result = eframe::run_native(
        "NeXium",
        options,
''' + stage25.ORIGINAL + '''
    );
}
'''

class TestStage25HostInitMinimalApp(unittest.TestCase):
    def test_separate_runtime_guard_after_host_init(self):
        patched=stage25.patch_source(SOURCE)
        self.assertIn('NEXIUM_MACOS_FULL_INIT_MINIMAL_APP',patched)
        self.assertIn(stage25.MARKER,patched)
        self.assertIn('let settings = AppSettings::load();',patched)
        self.assertIn('let result = eframe::run_native(',patched)
        self.assertIn('Box::new(Stage22MinimalEframe) as Box<dyn eframe::App>',patched)

    def test_normal_HorizonApp_still_retained(self):
        patched=stage25.patch_source(SOURCE)
        self.assertIn("HorizonApp::new(",patched)
        self.assertIn("log_feed_for_app.take()",patched)
        self.assertIn("nro_arg.clone()",patched)
        self.assertIn("as Box<dyn eframe::App>",patched)

    def test_idempotent_patch(self):
        patched=stage25.patch_source(SOURCE)
        self.assertEqual(stage25.patch_source(patched),patched)

    def test_missing_stage22_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Stage22"):
            stage25.patch_source(SOURCE.replace("STAGE22_MINIMAL_EFRAME_ENTERED","removed"))

    def test_missing_horizonapp_anchor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"exactly one"):
            stage25.patch_source(SOURCE.replace("HorizonApp::new","OtherApp::new"))

    def test_duplicate_closure_anchor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"exactly one"):
            stage25.patch_source(SOURCE+stage25.ORIGINAL)

    def test_partial_patch_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"partial"):
            stage25.patch_source(SOURCE+stage25.MARKER)

    def test_file_idempotent_and_no_other_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            main=root/"nexium-gui/src/main.rs"
            main.parent.mkdir(parents=True)
            main.write_text(SOURCE)
            self.assertTrue(stage25.apply(root))
            self.assertFalse(stage25.apply(root))
            self.assertEqual(main.read_text(),stage25.patch_source(SOURCE))

    def test_fail_closed_file_on_invalid_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            main=root/"nexium-gui/src/main.rs"
            main.parent.mkdir(parents=True)
            original=SOURCE.replace("HorizonApp::new","Another::new")
            main.write_text(original)
            self.assertEqual(stage25.main([str(root)]),2)
            self.assertEqual(main.read_text(),original)

if __name__=="__main__":
    unittest.main()
