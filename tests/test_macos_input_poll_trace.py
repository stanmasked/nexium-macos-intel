"""Stage34: ten source-bound checks for non-invasive SDL3 poll execution trace."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_input_poll_trace as stage

SOURCE = (
    "pub struct InputBackend { /* unrelated original code */ }\n"
    "impl InputBackend {\n" + stage.START
    + '        if std::env::var_os("NEXIUM_NO_GAMEPAD").is_some() {\n'
      '            return InputSnapshot::new();\n'
      '        }\n'
      '        if let Ok(mut ep) = self.sdl.event_pump() {\n'
      '            ep.pump_events();\n'
      '        }\n'
    + stage.PUMP_ANCHOR + "\n"
    + stage.PAD_ANCHOR + "\n"
    + "        self.sync_motion();\n"
    + "        self.sync_host_kind();\n"
    + "        self.motion.pump();\n"
    + "        self.sync_rumble();\n"
    + stage.END + "\n"
    + "        snap\n"
      "    }\n"
      "    pub fn other_method(&self) -> bool { true }\n"
      "}\n"
)


class TestStage34GenuineInputPollMarkers(unittest.TestCase):
    def test_three_one_time_checkpoints_in_order(self):
        got=stage.patch_source(SOURCE)
        self.assertEqual(got.count(stage.PREFIX),3)
        keys=[stage.PREFIX+"ENTRY",stage.PREFIX+"AFTER_EVENT_PUMP",
              stage.PREFIX+"AFTER_GAMEPAD_UPDATE"]
        self.assertEqual([got.index(k) for k in keys],
                         sorted(got.index(k) for k in keys))

    def test_no_sdl3_operations_removed_or_reordered(self):
        got=stage.patch_source(SOURCE)
        operations=["self.sdl.event_pump()", "ep.pump_events()",
                    "self.gamepad.update()", "self.ensure_pad()",
                    "self.sync_motion()", "self.sync_host_kind()",
                    "self.motion.pump()", "self.sync_rumble()"]
        self.assertEqual([got.index(x) for x in operations],
                         sorted(got.index(x) for x in operations))
        self.assertIn('std::env::var_os("NEXIUM_NO_GAMEPAD")',got)

    def test_no_gamepad_event_data_exported(self):
        got=stage.patch_source(SOURCE)
        for phase in ("ENTRY","AFTER_EVENT_PUMP","AFTER_GAMEPAD_UPDATE"):
            self.assertIn('eprintln!("STAGE34_INPUT_POLL_'+phase+'");',got)
        self.assertNotIn("println!(snap)",got)

    def test_marker_once_per_process_with_macos_opt_in(self):
        got=stage.patch_source(SOURCE)
        self.assertEqual(got.count('std::sync::atomic::AtomicBool::new(false)'),3)
        self.assertEqual(got.count('OBSERVED.swap(true'),3)
        self.assertEqual(got.count('NEXIUM_MACOS_INPUT_POLL_TRACE'),3)
        self.assertEqual(got.count('#[cfg(target_os = "macos")]'),3)

    def test_idempotent(self):
        got=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(got),got)

    def test_reject_missing_exact_input_poll(self):
        with self.assertRaisesRegex(RuntimeError,"poll method"):
            stage.patch_source(SOURCE.replace(stage.START,"    fn wrong() {\n"))

    def test_reject_drifted_sdl3_update_call(self):
        with self.assertRaisesRegex(RuntimeError,"pump/update"):
            stage.patch_source(SOURCE.replace("self.gamepad.update()","self.gamepad.change()"))
        with self.assertRaisesRegex(RuntimeError,"pump/update"):
            stage.patch_source(SOURCE.replace("self.ensure_pad()","self.ensure_other()"))

    def test_reject_reordered_event_update_calls(self):
        a,b=stage.PUMP_ANCHOR,stage.PAD_ANCHOR
        scrambled=SOURCE.replace(a,"TEMP").replace(b,a).replace("TEMP",b)
        with self.assertRaisesRegex(RuntimeError,"ordering"):
            stage.patch_source(scrambled)

    def test_partial_marker_refused(self):
        with self.assertRaisesRegex(RuntimeError,"incomplete"):
            stage.patch_source(SOURCE+stage.PREFIX+"ENTRY")

    def test_fail_closed_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/"nexium-gui/src/input.rs"
            p.parent.mkdir(parents=True)
            p.write_text(SOURCE)
            self.assertEqual(stage.main([tmp]),0)
            expected=stage.patch_source(SOURCE)
            self.assertEqual(p.read_text(),expected)
            self.assertEqual(stage.main([tmp]),0)
            broken=SOURCE.replace(stage.PUMP_ANCHOR,"bad thing")
            p.write_text(broken)
            self.assertEqual(stage.main([tmp]),2)
            self.assertEqual(p.read_text(),broken)


if __name__=="__main__":
    unittest.main()
