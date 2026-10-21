"""Stage45 exact-source fail-closed integration contracts for original input."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_stage45_original_snapshot as stage

INPUT = ("""use crate::controller_config::{ControllerConfig, GpButton, SwitchButton};
pub struct InputBackend {}
""" + stage.INPUT_ANCHOR + """
    let sdl = sdl3::init().ok()?;
    eprintln!("STAGE38_SDL3_INPUT_02_BEFORE_GAMEPAD_SUBSYSTEM");
    let gamepad = sdl.gamepad().ok()?;
    None
    }
    pub fn poll(&mut self, cfg: &ControllerConfig, left_dz: f32, right_dz: f32) -> InputSnapshot {
        InputSnapshot::new()
    }
}
""")
MAIN = 'fn main() {\n    eprintln!("STAGE40_PREWARM_MAIN_BEFORE_EFRAME");\n' + stage.MAIN_ANCHOR + '}\n'


class Stage45SourceTests(unittest.TestCase):
    def test_input_patch_uses_real_original_poll(self):
        patched=stage.patch_input(INPUT)
        self.assertIn("self.poll(&cfg, 0.12, 0.12)",patched)
        self.assertEqual(patched.count("self.poll(&cfg, 0.12, 0.12)"),3)

    def test_no_raw_ffi_or_unsafe(self):
        self.assertNotIn("unsafe",stage.INPUT_METHOD)
        self.assertNotIn("sdl3::sys::",stage.INPUT_METHOD)
        self.assertIn("VirtualJoystickDescription",stage.INPUT_METHOD)

    def test_real_switch_mapped_button_and_axis(self):
        self.assertIn("pressed.is(SwitchButton::B)",stage.INPUT_METHOD)
        self.assertIn("pressed.sticks[0] > 10000",stage.INPUT_METHOD)
        self.assertIn("pressed.raw_sticks[0] > 0.35",stage.INPUT_METHOD)
        self.assertIn("released.sticks[0].abs() < 500",stage.INPUT_METHOD)

    def test_release_does_not_leak_synthetic_button(self):
        self.assertIn("set_virtual_button(Button::South as u32, false)",stage.INPUT_METHOD)
        self.assertIn("set_virtual_axis(Axis::LeftX as u32, 0)",stage.INPUT_METHOD)
        self.assertIn("!released.is(SwitchButton::B)",stage.INPUT_METHOD)

    def test_handoff_restores_app_selection(self):
        self.assertIn("self.selected_id = saved_selected",stage.INPUT_METHOD)
        self.assertIn("self.preferred = saved_preferred",stage.INPUT_METHOD)
        self.assertIn("drop(connection)",stage.INPUT_METHOD)

    def test_motion_ranking_cannot_select_physical_controller(self):
        self.assertIn("let saved_motion_enabled = self.motion_enabled;",stage.INPUT_METHOD)
        self.assertIn("self.motion_enabled = false;",stage.INPUT_METHOD)
        self.assertIn("self.motion_enabled = saved_motion_enabled;",stage.INPUT_METHOD)

    def test_only_macos_explicit_opt_in(self):
        self.assertIn('NEXIUM_MACOS_VIRTUAL_SNAPSHOT_TEST',stage.MAIN_PATCH)
        self.assertIn('#[cfg(target_os = "macos")]',stage.MAIN_PATCH)
        self.assertIn('#[cfg(target_os = "macos")]',stage.INPUT_METHOD)

    def test_normal_stage40_preinit_retained(self):
        patched=stage.patch_main(MAIN)
        self.assertIn("input::InputBackend::new(",patched)
        self.assertIn("STAGE40_PREWARM_MAIN_BEFORE_EFRAME",patched)
        self.assertIn("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED",patched)

    def test_input_patch_idempotent(self):
        once=stage.patch_input(INPUT)
        self.assertEqual(stage.patch_input(once),once)

    def test_main_patch_idempotent(self):
        once=stage.patch_main(MAIN)
        self.assertEqual(stage.patch_main(once),once)

    def test_reject_ambiguous_input(self):
        with self.assertRaisesRegex(ValueError,"constructor"):
            stage.patch_input(INPUT+stage.INPUT_ANCHOR)

    def test_reject_main_without_stage40(self):
        with self.assertRaisesRegex(ValueError,"Stage40"):
            stage.patch_main(MAIN.replace("STAGE40_PREWARM_MAIN_BEFORE_EFRAME","gone"))

    def test_reject_non_original_poll(self):
        with self.assertRaisesRegex(ValueError,"poll"):
            stage.patch_input(INPUT.replace("pub fn poll(&mut self, cfg: &ControllerConfig","pub fn changed(&mut self, cfg: &ControllerConfig"))

    def test_validate_both_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"nexium-gui/src"
            root.mkdir(parents=True)
            (root/"input.rs").write_text(INPUT)
            bad=MAIN.replace("STAGE40_PREWARM_MAIN_BEFORE_EFRAME","gone")
            (root/"main.rs").write_text(bad)
            self.assertEqual(stage.main([d]),2)
            self.assertEqual((root/"input.rs").read_text(),INPUT)
            self.assertEqual((root/"main.rs").read_text(),bad)

    def test_full_two_file_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"nexium-gui/src"
            root.mkdir(parents=True)
            (root/"input.rs").write_text(INPUT)
            (root/"main.rs").write_text(MAIN)
            self.assertEqual(stage.main([d]),0)
            contents=[(root/f).read_text() for f in ("input.rs","main.rs")]
            self.assertEqual(stage.main([d]),0)
            self.assertEqual(contents,[(root/f).read_text() for f in ("input.rs","main.rs")])


if __name__=="__main__":
    unittest.main()
