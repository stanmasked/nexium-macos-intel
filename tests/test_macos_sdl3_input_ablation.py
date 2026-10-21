"""Stage29 fail-closed SDL3 constructor-only ablation regression tests."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_sdl3_input_ablation as stage

SOURCE=("fn unrelated() {}\n"+stage.START+"\n"+
        '        eprintln!("STAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT");\n'+
        stage.ORIGINAL+"\n"+
        '        eprintln!("STAGE28_HORIZON_CTOR_PHASE_04_AFTER_INPUT");\n'+
        '        let nextendo = true;\n'+stage.END+" {}\n")

class Stage29InputAblationTests(unittest.TestCase):
    def test_only_input_backend_replaced(self):
        d=stage.patch_source(SOURCE)
        self.assertIn("NEXIUM_MACOS_SKIP_SDL3_INPUT",d)
        self.assertIn("InputBackend::new(app_settings.motion_enabled, gamepad)",d)
        self.assertIn("let nextendo = true",d)
        self.assertIn('STAGE29_SDL3_INPUT_SKIPPED',d)
        self.assertIn('STAGE29_SDL3_INPUT_ENABLED',d)

    def test_normal_mode_keeps_original_input_call(self):
        d=stage.patch_source(SOURCE)
        self.assertIn("if stage29_skip_sdl3_input",d)
        self.assertIn("cfg!(target_os = \"macos\")",d)
        self.assertIn("InputBackend::new(",d)

    def test_idempotent_patch(self):
        d=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(d),d)

    def test_missing_stage28_phase_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Stage28"):
            stage.patch_source(SOURCE.replace("STAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT","missing"))
        with self.assertRaisesRegex(RuntimeError,"Stage28"):
            stage.patch_source(SOURCE.replace("STAGE28_HORIZON_CTOR_PHASE_04_AFTER_INPUT","missing"))

    def test_missing_or_duplicate_sdl3_input_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"SDL3"):
            stage.patch_source(SOURCE.replace("InputBackend::new","InputBackend::other"))
        with self.assertRaisesRegex(RuntimeError,"ambiguous"):
            stage.patch_source(SOURCE.replace(stage.ORIGINAL,stage.ORIGINAL+"\n"+stage.ORIGINAL))

    def test_partial_patch_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"partially"):
            stage.patch_source(SOURCE+stage.SKIP_MARKER)

    def test_outside_horizonapp_constructor_unchanged(self):
        d=stage.patch_source(SOURCE)
        self.assertTrue(d.startswith("fn unrelated() {}\n"))
        self.assertTrue(d.endswith(stage.END+" {}\n"))

    def test_duplicate_constructor_boundary_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"ctor"):
            stage.patch_source(SOURCE+stage.START)

    def test_file_patching_is_single_target_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"nexium-gui/src/app.rs"
            path.parent.mkdir(parents=True)
            path.write_text(SOURCE)
            self.assertEqual(stage.main([tmp]),0)
            self.assertEqual(path.read_text(),stage.patch_source(SOURCE))
            self.assertEqual(stage.main([tmp]),0)

    def test_fail_closed_does_not_edit_invalid_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"nexium-gui/src/app.rs"
            path.parent.mkdir(parents=True)
            broken=SOURCE.replace("InputBackend::new","unexpected")
            path.write_text(broken)
            self.assertEqual(stage.main([tmp]),2)
            self.assertEqual(path.read_text(),broken)

if __name__=="__main__":
    unittest.main()
