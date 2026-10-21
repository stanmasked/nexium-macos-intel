"""Source safety tests for real HorizonApp full UI/poll checkpoints."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_stage42_full_ui_poll as stage

SOURCE = (
    "struct HorizonApp;\n"
    "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED\n"
    + stage.START + "\n"
    + "    fn on_exit(&mut self) { }\n"
    + stage.UI + "\n"
    + "        let ctx = &ui.ctx().clone();\n"
    + stage.POLL + "\n"
    + "        if self.last_input.connected { }\n"
    + "    }\n}\n"
)


class Stage42SourceTests(unittest.TestCase):
    def test_ui_and_poll_are_both_instrumented(self):
        patched=stage.patch_source(SOURCE)
        self.assertIn(stage.UI_GUARD,patched)
        self.assertIn(stage.POLL_GUARD,patched)
        self.assertLess(patched.index(stage.MARK_UI), patched.index(stage.MARK_POLL))

    def test_original_input_poll_preserved_exactly(self):
        patched=stage.patch_source(SOURCE)
        self.assertEqual(patched.count(stage.POLL),1)
        self.assertIn("self.last_input.connected",patched)

    def test_trace_requires_runtime_optin_and_macos(self):
        patched=stage.patch_source(SOURCE)
        self.assertEqual(patched.count('NEXIUM_MACOS_SDL3_POLL_TRACE'),2)
        self.assertEqual(patched.count('#[cfg(target_os = "macos")]'),2)
        self.assertNotIn("unsafe ",patched)

    def test_no_buttons_or_axes_in_diagnostic_markers(self):
        patched=stage.patch_source(SOURCE)
        self.assertNotIn('eprintln!("{}", self.last_input',patched)
        self.assertNotIn("last_input.buttons",stage.POLL_GUARD)
        self.assertNotIn("last_input.sticks",stage.POLL_GUARD)

    def test_full_ui_marker_distinct_from_constructor_wrapper(self):
        patched=stage.patch_source(SOURCE)
        self.assertIn(stage.MARK_UI,patched)
        self.assertNotIn("STAGE26_HORIZON_CTOR_ENTERED",stage.UI_GUARD)

    def test_first_poll_marker_is_one_time(self):
        patched=stage.patch_source(SOURCE)
        self.assertIn("POLL_SEEN.swap(true",patched)
        self.assertIn("UI_SEEN.swap(true",patched)

    def test_controller_connection_marker_is_one_time(self):
        patched=stage.patch_source(SOURCE)
        self.assertIn("CONNECTED_SEEN.swap(true",patched)
        self.assertIn("STAGE42_CONTROLLER_CONNECTED",patched)

    def test_idempotent(self):
        once=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(once),once)

    def test_partial_patch_rejected(self):
        with self.assertRaisesRegex(ValueError,"partial"):
            stage.patch_source(SOURCE+stage.MARK_UI)

    def test_missing_stage40_rejected(self):
        with self.assertRaisesRegex(ValueError,"Stage40"):
            stage.patch_source(SOURCE.replace("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",""))

    def test_missing_ui_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,"anchors"):
            stage.patch_source(SOURCE.replace(stage.UI,"another ui fn"))

    def test_duplicate_poll_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,"anchors"):
            stage.patch_source(SOURCE.replace(stage.POLL,stage.POLL+"\n"+stage.POLL))

    def test_file_patch_and_no_partial_write(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"nexium-gui/src/app.rs"
            target.parent.mkdir(parents=True)
            target.write_text(SOURCE)
            self.assertEqual(stage.main([d]),0)
            first=target.read_text()
            self.assertEqual(stage.main([d]),0)
            self.assertEqual(target.read_text(),first)
            wrong=SOURCE.replace(stage.UI,"not valid")
            target.write_text(wrong)
            self.assertEqual(stage.main([d]),2)
            self.assertEqual(target.read_text(),wrong)


if __name__=="__main__":
    unittest.main()
