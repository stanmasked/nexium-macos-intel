"""Ten fail-closed tests for opt-in SDL3 virtual pad plus actual InputSnapshot."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_virtual_input_snapshot as stage

SOURCE=("use sdl3::gamepad::Button;\n"+
        stage.IMPL+
        "    pub fn new(motion_enabled: bool, preferred: Option<String>) -> Option<Self> {\n"+
        "        let sdl = sdl3::init().ok()?;\n"+stage.CTOR+"\n"+
        "        Some(Self { gamepad, sdl })\n    }\n"+
        stage.POLL+
        '        if std::env::var_os("NEXIUM_NO_GAMEPAD").is_some() { return InputSnapshot::new(); }\n'+
        stage.POLL_EVENT+"\n"+
        "            ep.pump_events();\n        }\n"+
        "        self.gamepad.update();\n"+
        "        self.ensure_pad();\n"+
        "        let mut snap = InputSnapshot::new();\n"+
        "        snap.connected = true;\n"+
        "        snap.buttons = cfg.gamepad_pressed(0);\n"+
        stage.END+"(&mut self) -> Option<GpButton> {\n"+
        "        None\n    }\n}\n")


class Stage36VirtualInputTests(unittest.TestCase):
    def test_real_source_calls_preserved(self):
        result=stage.patch_source(SOURCE)
        for needle in ("sdl3::init().ok()?","sdl.gamepad().ok()?",
                       "self.sdl.event_pump()","ep.pump_events()",
                       "self.gamepad.update()","self.ensure_pad()",
                       "snap.buttons = cfg.gamepad_pressed(0);"):
            self.assertIn(needle,result)

    def test_real_sdl_virtual_attach_and_press_release(self):
        result=stage.patch_source(SOURCE)
        for key in ("SDL_AttachVirtualJoystick","SDL_OpenJoystick",
                    "SDL_SetJoystickVirtualButton(ptr, 0, down)",
                    'STAGE36_VIRTUAL_SYNTHETIC_PRESS_SENT',
                    'STAGE36_VIRTUAL_SYNTHETIC_RELEASE_SENT'):
            self.assertIn(key,result)
        self.assertLess(result.index(stage.CTOR),result.index("stage36_make_virtual_gamepad();"))
        self.assertLess(result.index("stage36_send_synthetic_button();"),
                        result.index(stage.POLL_EVENT))

    def test_marker_evidence_not_fabricated_button(self):
        result=stage.patch_source(SOURCE)
        self.assertIn("stage36_observe_synthetic_snapshot(",result)
        self.assertIn("snap.connected && virtual_pad_is_the_selected_source",result)
        self.assertIn("self.pad.as_ref().and_then(|pad| pad.id().ok())",result)
        self.assertIn("STAGE36_VIRTUAL_ID.with(|value| value.set(id.0))",result)
        self.assertIn("if connected && mapped_buttons != 0",result)
        self.assertIn("if pressed.replace(false)",result)
        self.assertNotIn("snap.buttons = 1",result)

    def test_mac_only_runtime_opt_in(self):
        r=stage.patch_source(SOURCE)
        self.assertIn('#[cfg(target_os = "macos")]',r)
        self.assertEqual(r.count('NEXIUM_MACOS_VIRTUAL_BUTTON_TEST'),3)
        self.assertEqual(r.count('Some("1")'),3)

    def test_one_process_only_virtual_lifetime(self):
        r=stage.patch_source(SOURCE)
        self.assertIn("thread_local!",r)
        self.assertIn("std::cell::Cell<*mut sdl3::sys::joystick::SDL_Joystick>",r)
        self.assertIn("saturating_add(1)",r)

    def test_idempotent(self):
        r=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(r),r)

    def test_reject_missing_original_sdl_gamepad(self):
        with self.assertRaisesRegex(RuntimeError,"structure"):
            stage.patch_source(SOURCE.replace(stage.CTOR,"gamepad = None"))

    def test_reject_missing_original_poll_method(self):
        with self.assertRaisesRegex(RuntimeError,"structure"):
            stage.patch_source(SOURCE.replace(stage.POLL,"    pub fn bad() {\n"))

    def test_reject_partial_patch_and_double_markers(self):
        with self.assertRaisesRegex(RuntimeError,"incomplete"):
            stage.patch_source(SOURCE+'STAGE36_VIRTUAL_FAKE_MARKER')
        a=stage.patch_source(SOURCE)
        with self.assertRaisesRegex(RuntimeError,"incomplete"):
            stage.patch_source(a+a)

    def test_file_fail_closed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as dir:
            file=Path(dir)/"nexium-gui/src/input.rs"
            file.parent.mkdir(parents=True)
            file.write_text(SOURCE)
            self.assertEqual(stage.main([dir]),0)
            self.assertEqual(file.read_text(),stage.patch_source(SOURCE))
            self.assertEqual(stage.main([dir]),0)
            broken=SOURCE.replace(stage.POLL_EVENT,"unknown_event_pump()")
            file.write_text(broken)
            self.assertEqual(stage.main([dir]),2)
            self.assertEqual(file.read_text(),broken)

if __name__=="__main__":
    unittest.main()
