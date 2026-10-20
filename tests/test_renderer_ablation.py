"""Stage23 opt-in Intel renderer patch: synthetic fail-closed tests."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import apply_macos_renderer_ablation as stage

SOURCE='''fn main() {
        eprintln!("STAGE22_MINIMAL_EFRAME_ENTERED");
        let options = eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_title("NeXium Intel eframe startup isolation")
                .with_inner_size([720.0, 480.0]),
            renderer: eframe::Renderer::Wgpu,
            wgpu_options: eframe::WgpuConfiguration {
                wgpu_setup: eframe::egui_wgpu::WgpuSetup::CreateNew(
                    host_wgpu_setup(None),
                ),
            },
        };
}
'''

class Stage23RendererTests(unittest.TestCase):
    def test_two_backends_only_in_minimal_branch(self):
        out=stage.patch_source(SOURCE)
        self.assertIn('"wgpu" => eframe::Renderer::Wgpu',out)
        self.assertIn('"glow" => eframe::Renderer::Glow',out)
        self.assertIn('NEXIUM_MACOS_MINIMAL_RENDERER',out)
        self.assertIn('stage23_renderer',out)
        self.assertIn('STAGE23_RENDERER_INVALID',out)

    def test_idempotence(self):
        out=stage.patch_source(SOURCE)
        self.assertEqual(out,stage.patch_source(out))

    def test_original_normal_startup_unmodified(self):
        out=stage.patch_source(SOURCE+'\nlet normal_renderer=eframe::Renderer::Wgpu;')
        self.assertIn('let normal_renderer=eframe::Renderer::Wgpu;',out)
        self.assertEqual(out.count('let stage23_renderer_name'),1)

    def test_missing_stage22_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Stage22'):
            stage.patch_source(SOURCE.replace('STAGE22_MINIMAL_EFRAME_ENTERED','no marker'))

    def test_wrong_renderer_anchor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'anchors'):
            stage.patch_source(SOURCE.replace('renderer: eframe::Renderer::Wgpu','renderer: bad'))

    def test_duplicate_renderer_anchor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'anchors'):
            stage.patch_source(SOURCE+stage.ORIGINAL)

    def test_duplicate_viewport_anchor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'anchors'):
            stage.patch_source(SOURCE+stage.INSERT_BEFORE)

    def test_partial_patch_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'partially patched'):
            stage.patch_source(SOURCE+stage.MARKER)

    def test_file_patch_idempotent_and_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'nexium-gui/src/main.rs'
            path.parent.mkdir(parents=True)
            path.write_text(SOURCE)
            once=stage.patch_source(path.read_text())
            path.write_text(once)
            self.assertEqual(stage.patch_source(path.read_text()),once)

if __name__=='__main__':
    unittest.main()
