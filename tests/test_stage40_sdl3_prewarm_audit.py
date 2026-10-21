"""Stage40 native SDL3 prewarm audit tests; no invented gameplay claims."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_sdl3_prewarm as stage

def receipt(alive=True,window=True):
    return {
        "probe":"no_nro_gui_process_only",
        "outcome":"alive_without_gui_verification" if alive else "exited_nonzero",
        "duration_limit_seconds":12,
        "emulator_sha256":"f"*64,
        "alive_at_deadline":alive,
        "window_found":window,
        "window_probe":"own_visible_window_observed" if window else "not_requested",
        "nro_verified":False,"gameplay_verified":False,"gui_verified":False,
        "exit_signal":None if alive else "SIGABRT",
    }

def markers(*values):
    return "".join(value+"\n" for value in values)

class PrewarmAuditTests(unittest.TestCase):
    def test_bypass_negative_control(self):
        value = stage.classify("skipped",receipt(),markers("STAGE29_SDL3_INPUT_SKIPPED"))
        self.assertTrue(value["own_window_found"])

    def test_normal_native_crash_kept(self):
        value = stage.classify("normal",receipt(False,False),
            markers("STAGE29_SDL3_INPUT_ENABLED","STAGE38_SDL3_INPUT_00_ENTRY",
                    "STAGE38_SDL3_INPUT_01_BEFORE_SDL_INIT",
                    "STAGE38_SDL3_INPUT_02_BEFORE_GAMEPAD_SUBSYSTEM")
            + stage.PANIC_TEXT)
        self.assertEqual(value["exit_signal"],"SIGABRT")
        self.assertTrue(value["winit_reentrant_panic_observed"])

    def test_prewarm_consume_is_distinct_from_input_verification(self):
        value = stage.classify("prewarm",receipt(),
            markers("STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
                    "STAGE38_SDL3_INPUT_00_ENTRY",
                    "STAGE38_SDL3_INPUT_01_BEFORE_SDL_INIT",
                    "STAGE38_SDL3_INPUT_02_BEFORE_GAMEPAD_SUBSYSTEM",
                    "STAGE38_SDL3_INPUT_03_BEFORE_RUMBLE",
                    "STAGE38_SDL3_INPUT_04_BEFORE_INPUT_STRUCT",
                    "STAGE40_PREWARM_MAIN_READY",
                    "STAGE29_SDL3_INPUT_ENABLED",
                    "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED"))
        self.assertIn("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",value["source_markers"])

    def test_source_prewarm_crash_is_conclusive_only_for_process(self):
        value = stage.classify("prewarm",receipt(False,False),
            markers("STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
                    "STAGE38_SDL3_INPUT_00_ENTRY",
                    "STAGE38_SDL3_INPUT_01_BEFORE_SDL_INIT",
                    "STAGE38_SDL3_INPUT_02_BEFORE_GAMEPAD_SUBSYSTEM"))
        self.assertFalse(value["alive_at_deadline"])

    def test_survival_without_handoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"handoff"):
            stage.classify("prewarm",receipt(),
                markers("STAGE40_PREWARM_MAIN_BEFORE_EFRAME"))

    def test_fake_gameplay_is_rejected(self):
        item=receipt()
        item["gameplay_verified"]=True
        with self.assertRaisesRegex(ValueError,"unsupported"):
            stage.classify("skipped",item,markers("STAGE29_SDL3_INPUT_SKIPPED"))

    def test_mutually_exclusive_markers_rejected(self):
        with self.assertRaisesRegex(ValueError,"contradictory"):
            stage.classify("prewarm",receipt(False,False),
                markers("STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
                        "STAGE40_PREWARM_MAIN_READY",
                        "STAGE40_PREWARM_MAIN_UNAVAILABLE"))

    def test_negative_control_must_own_window(self):
        with self.assertRaisesRegex(ValueError,"safe-window"):
            stage.classify("skipped",receipt(True,False),
                markers("STAGE29_SDL3_INPUT_SKIPPED"))

    def test_phases_need_exact_prefix(self):
        with self.assertRaisesRegex(ValueError,"out-of-order"):
            stage.classify("normal",receipt(False,False),
                markers("STAGE29_SDL3_INPUT_ENABLED",
                        "STAGE38_SDL3_INPUT_02_BEFORE_GAMEPAD_SUBSYSTEM"))

    def test_private_messages_never_appear_in_output(self):
        item=receipt()
        item["diagnostic_messages"]=["SECRET PRIVATE PATH"]
        result=stage.classify("skipped",item,
            markers("STAGE29_SDL3_INPUT_SKIPPED")+"SECRET PRIVATE PATH\n")
        self.assertNotIn("SECRET",repr(result))

if __name__=="__main__":
    unittest.main()
