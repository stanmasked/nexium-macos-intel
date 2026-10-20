"""Pure synthetic safety tests for the Stage22 guarded source patch."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import apply_macos_minimal_eframe as stage

PINNED_SHAPE = '''mod app;
fn host_wgpu_setup(x: Option<&str>) {}
fn host_surface_config(x: bool) {}
fn main() -> Result<(), eframe::Error> {
    let settings = AppSettings::load();
    eframe::run_native("NeXium", options, creator)
}
'''

class Stage22MinimalEframeTests(unittest.TestCase):
    def test_patch_is_opt_in(self):
        updated=stage.patch_text(PINNED_SHAPE)
        self.assertEqual(updated.count(stage.MARKER),1)
        self.assertIn('NEXIUM_MACOS_MINIMAL_EFRAME',updated)
        self.assertIn('== Some("1")',updated)
        self.assertIn('cfg(target_os = "macos")',updated)
        self.assertIn('AppSettings::load()',updated)

    def test_pinned_eframe_037_trait_uses_ui_not_update(self):
        patched = stage.patch_text(PINNED_SHAPE)
        self.assertIn("fn ui(&mut self, ui: &mut egui::Ui", patched)
        self.assertNotIn("fn update(&mut self", patched)
        self.assertNotIn("egui::CentralPanel::default().show(ctx", patched)

    def test_patcher_idempotent(self):
        first=stage.patch_text(PINNED_SHAPE)
        self.assertEqual(stage.patch_text(first),first)

    def test_fail_closed_missing_anchor(self):
        with self.assertRaisesRegex(RuntimeError,'anchors missing'):
            stage.patch_text(PINNED_SHAPE.replace(stage.ANCHOR,''))

    def test_fail_closed_duplicate_anchor(self):
        with self.assertRaisesRegex(RuntimeError,'anchors missing'):
            stage.patch_text(PINNED_SHAPE+stage.ANCHOR)

    def test_fail_closed_missing_wgpu(self):
        with self.assertRaisesRegex(RuntimeError,'anchors missing'):
            stage.patch_text(PINNED_SHAPE.replace('fn host_wgpu_setup(', 'fn missing('))

    def test_fail_closed_partly_inserted(self):
        with self.assertRaisesRegex(RuntimeError,'partly edited'):
            stage.patch_text(PINNED_SHAPE+stage.MARKER)

    def test_real_tempfile_only_main_is_edited(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nexium-gui/src/main.rs'
            path.parent.mkdir(parents=True)
            path.write_text(PINNED_SHAPE)
            self.assertTrue(stage.apply(Path(d)))
            self.assertFalse(stage.apply(Path(d)))
            self.assertEqual(path.read_text(),stage.patch_text(PINNED_SHAPE))

if __name__=='__main__':
    unittest.main()
