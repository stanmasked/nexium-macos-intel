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

    def test_cargo_enables_explicit_glow(self):
        original='eframe = { version = "0.37", features = ["wgpu"] }'
        patched=stage.patch_cargo(original)
        self.assertEqual(patched, stage.CARGO_UPDATED)
        self.assertIn('"glow"',patched)

    def test_cargo_idempotent(self):
        self.assertEqual(stage.patch_cargo(stage.CARGO_UPDATED), stage.CARGO_UPDATED)

    def test_cargo_source_drift_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'Cargo feature anchor'):
            stage.patch_cargo('eframe = "0.37"')
        with self.assertRaisesRegex(RuntimeError,'ambiguous'):
            stage.patch_cargo(stage.CARGO_ORIGINAL+'\n'+stage.CARGO_ORIGINAL)

    def test_dual_file_prevalidation_prevents_partial_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            directory=root/'nexium-gui'
            (directory/'src').mkdir(parents=True)
            mainfile=directory/'src/main.rs'
            cargo=directory/'Cargo.toml'
            mainfile.write_text(SOURCE)
            cargo.write_text('eframe = "unexpected"')
            self.assertEqual(stage.main([str(root)]),2)
            self.assertEqual(mainfile.read_text(), SOURCE)
            self.assertEqual(cargo.read_text(),'eframe = "unexpected"')

    def test_dual_file_patch_idempotent_and_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            directory=root/'nexium-gui'
            (directory/'src').mkdir(parents=True)
            mainfile=directory/'src/main.rs'
            cargo=directory/'Cargo.toml'
            mainfile.write_text(SOURCE)
            cargo.write_text(stage.CARGO_ORIGINAL+'\n[features]\ndefault=[]\n')
            self.assertEqual(stage.main([str(root)]),0)
            self.assertEqual(stage.main([str(root)]),0)
            self.assertEqual(mainfile.read_text(),stage.patch_source(SOURCE))
            self.assertEqual(cargo.read_text(),stage.CARGO_UPDATED+'\n[features]\ndefault=[]\n')

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
