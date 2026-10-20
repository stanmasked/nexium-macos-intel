"""Stage26 constructor-only source patch tests; never assert emulator boot."""
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_horizonapp_ctor_only as stage

SOURCE = '''fn dummy() { eprintln!("STAGE22_MINIMAL_EFRAME_ENTERED"); }
fn main() -> Result<(), eframe::Error> {
    let options = eframe::NativeOptions::default();
    eframe::run_native("NeXium",options,
''' + stage.STAGE25_CREATOR + '''
    )
}
'''

class Stage26CtorOnlySourceTests(unittest.TestCase):
    def test_opt_in_real_constructor_retained_with_simplified_ui(self):
        source=stage.patch_source(SOURCE)
        self.assertIn("NEXIUM_MACOS_HORIZON_CTOR_ONLY",source)
        self.assertIn("let inner = HorizonApp::new(",source)
        self.assertIn("Stage26HorizonCtorOnly { _inner: inner }",source)
        self.assertIn("impl eframe::App for Stage26HorizonCtorOnly",source)
        self.assertIn("fn ui(&mut self, ui: &mut egui::Ui",source)

    def test_normal_and_stage25_modes_preserved(self):
        result=stage.patch_source(SOURCE)
        self.assertIn("NEXIUM_MACOS_FULL_INIT_MINIMAL_APP",result)
        self.assertIn("STAGE25_HOST_INIT_MINIMAL_APP_ENTERED",result)
        self.assertIn("Stage22MinimalEframe",result)
        self.assertIn("log_feed_for_app.take()",result)
        self.assertIn("settings.clone()",result)
        self.assertIn("nro_arg.clone()",result)

    def test_two_constructor_execution_markers(self):
        result=stage.patch_source(SOURCE)
        self.assertEqual(result.count(stage.ENTER),1)
        self.assertEqual(result.count(stage.RETURNED),1)
        self.assertLess(result.index(stage.ENTER),result.index(stage.RETURNED))

    def test_idempotence(self):
        patched=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(patched),patched)

    def test_missing_stage22_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Stage22"):
            stage.patch_source(SOURCE.replace("STAGE22_MINIMAL_EFRAME_ENTERED","removed"))

    def test_missing_or_duplicate_stage25_creator_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Stage25"):
            stage.patch_source(SOURCE.replace("HorizonApp::new","AnotherApp::new"))
        with self.assertRaisesRegex(RuntimeError,"ambiguous"):
            stage.patch_source(SOURCE+stage.STAGE25_CREATOR)

    def test_partly_inserted_marker_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"partial"):
            stage.patch_source(SOURCE+stage.RETURNED)

    def test_file_patching_only_one_source_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"nexium-gui/src"
            directory.mkdir(parents=True)
            path=directory/"main.rs"
            path.write_text(SOURCE)
            self.assertEqual(stage.main([str(Path(temp))]),0)
            expected=stage.patch_source(SOURCE)
            self.assertEqual(path.read_text(),expected)
            self.assertEqual(stage.main([str(Path(temp))]),0)
            self.assertEqual(path.read_text(),expected)

    def test_fail_closed_unchanged_file(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"nexium-gui/src"
            directory.mkdir(parents=True)
            path=directory/"main.rs"
            bad=SOURCE.replace("HorizonApp::new","WrongApp::new")
            path.write_text(bad)
            self.assertEqual(stage.main([str(Path(temp))]),2)
            self.assertEqual(path.read_text(),bad)

if __name__=="__main__":
    unittest.main()
