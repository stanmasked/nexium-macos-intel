"""Stage37 authentic NPad host input bridge source regression checks."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_hid_host_bridge_trace as stage

SOURCE=('impl HorizonApp {\n'
        '    fn process_input(&mut self) {\n'
        '        let (kb_buttons, kb_sticks) = self.controller_config.buttons_pressed(&pressed);\n'
        '        let (gp_buttons, gp_sticks) = if self.last_input.connected {\n'
        '            self.last_input.to_npad()\n'
        '        } else { (0u64, [0i32;4]) };\n'
        '        let mut buttons = kb_buttons | gp_buttons;\n'
        '        let sticks = gp_sticks;\n'
        '        let state = nexium_core::hid_state::get_hid_state();\n'
        '        let mut hid = state.lock();\n'
        +stage.ANCHOR+
        '        hid.publish_motion();\n'
        '    }\n'
        '}\n')


class Stage37HostBridgeTests(unittest.TestCase):
    def test_source_only_inserts_after_real_host_hid_update(self):
        s=stage.patch_source(SOURCE)
        self.assertEqual(s.count(stage.ANCHOR),1)
        self.assertLess(s.index(stage.ANCHOR),s.index("STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE"))
        self.assertLess(s.index("STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE"),s.index("hid.publish_motion();"))

    def test_guest_hid_not_artificially_set(self):
        s=stage.patch_source(SOURCE)
        self.assertEqual(s.count("hid.update_input("),1)
        self.assertIn("let host_hid_state_contains_b = hid.input.buttons & switch_b != 0;",s)
        self.assertIn("let original_snapshot_contains_b = gp_buttons & switch_b != 0;",s)
        self.assertNotIn("hid.input.buttons =",s)

    def test_correct_switch_b_explicit_bit(self):
        s=stage.patch_source(SOURCE)
        self.assertIn("SwitchButton::B.npad_bit()",s)
        self.assertNotIn("SwitchButton::A.npad_bit()",s)

    def test_release_derived_from_original_host_hid_and_snapshot(self):
        s=stage.patch_source(SOURCE)
        self.assertIn("!original_snapshot_contains_b && !host_hid_state_contains_b",s)
        self.assertIn("STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",s)
        self.assertIn("STAGE37_SWITCH_B_DOWN.swap(false",s)

    def test_does_not_claim_npad_guest_binding(self):
        s=stage.patch_source(SOURCE)
        self.assertIn("if hid.shmem_va.is_none()",s)
        self.assertIn("STAGE37_HID_BRIDGE_NO_GUEST_NPAD_SHMEM",s)
        self.assertIn("STAGE37_HID_BRIDGE_GUEST_SHMEM_MAPPING_PRESENT_UNVERIFIED",s)
        self.assertNotIn("STAGE37_GAME_NRO_VERIFIED",s)

    def test_macos_and_experiment_opt_in_double_guard(self):
        s=stage.patch_source(SOURCE)
        self.assertIn('#[cfg(target_os = "macos")]',s)
        self.assertIn("NEXIUM_MACOS_STAGE37_HID_BRIDGE_TRACE",s)
        self.assertIn("NEXIUM_MACOS_VIRTUAL_BUTTON_TEST",s)

    def test_idempotent(self):
        s=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(s),s)

    def test_reject_missing_original_hid_update(self):
        with self.assertRaisesRegex(RuntimeError,"update_input anchor"):
            stage.patch_source(SOURCE.replace("hid.update_input(","hid.other("))

    def test_reject_moved_original_npad_mapping(self):
        with self.assertRaisesRegex(RuntimeError,"mapping path"):
            stage.patch_source(SOURCE.replace("self.last_input.to_npad()","self.last_input.other()"))

    def test_reject_double_source_path_or_partial_marker(self):
        with self.assertRaisesRegex(RuntimeError,"merge no longer pinned"):
            stage.patch_source(SOURCE.replace("let mut buttons = kb_buttons | gp_buttons;",
                "let mut buttons = kb_buttons | gp_buttons;\n        let mut buttons = kb_buttons | gp_buttons;"))
        with self.assertRaisesRegex(RuntimeError,"partial/extra"):
            stage.patch_source(SOURCE+"STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE")

    def test_fail_closed_file_write(self):
        with tempfile.TemporaryDirectory() as rootstr:
            root=Path(rootstr)
            f=root/"nexium-gui/src/app.rs"
            f.parent.mkdir(parents=True)
            f.write_text(SOURCE)
            self.assertEqual(stage.main([rootstr]),0)
            self.assertEqual(f.read_text(),stage.patch_source(SOURCE))
            self.assertEqual(stage.main([rootstr]),0)
            bad=SOURCE.replace("self.last_input.to_npad()","other()")
            f.write_text(bad)
            self.assertEqual(stage.main([rootstr]),2)
            self.assertEqual(f.read_text(),bad)


if __name__=="__main__":
    unittest.main()
