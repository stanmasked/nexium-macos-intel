"""Stage42 input/UI audit synthetic tests, with private data never emitted."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import audit_stage42_full_ui_poll as stage

SHA="e"*64
def receipt(alive=True,window=True):
    return {
        "probe":"no_nro_gui_process_only",
        "emulator_sha256":SHA,
        "duration_limit_seconds":12,
        "nro_verified":False,
        "gameplay_verified":False,
        "gui_verified":False,
        "outcome":"alive_without_gui_verification" if alive else "exited_nonzero",
        "alive_at_deadline":alive,
        "window_found":window,
        "window_probe":"own_visible_window_observed" if window else "not_requested",
        "exit_signal":None if alive else "SIGABRT",
    }
def markers(*args):
    return "".join(x+"\n" for x in args)
PREWARM=("STAGE40_PREWARM_MAIN_BEFORE_EFRAME","STAGE40_PREWARM_MAIN_READY",
         "STAGE29_SDL3_INPUT_ENABLED","STAGE40_PREWARM_CONSTRUCTOR_CONSUMED")
PHASES=tuple("STAGE38_SDL3_INPUT_"+p for p in stage.PHASES)

class Stage42AuditTests(unittest.TestCase):
    def test_constructor_prewarms_without_full_ui(self):
        row=stage.classify("ctor-prewarm",receipt(),markers(*PHASES,*PREWARM))
        self.assertTrue(row["prewarm_consumed"])
        self.assertFalse(row["original_ui_entered"])

    def test_full_ui_poll_has_distinct_markers(self):
        row=stage.classify("full-prewarm",receipt(),markers(
            *PHASES,*PREWARM,"STAGE42_FULL_UI_ENTERED","STAGE42_INPUT_POLL_FIRST"))
        self.assertTrue(row["original_sdl3_poll_invoked"])
        self.assertFalse(row["controller_connection_seen"])

    def test_connected_pad_not_button_proof(self):
        row=stage.classify("full-prewarm",receipt(),markers(
            *PHASES,*PREWARM,"STAGE42_FULL_UI_ENTERED",
            "STAGE42_INPUT_POLL_FIRST","STAGE42_CONTROLLER_CONNECTED"))
        self.assertTrue(row["controller_connection_seen"])

    def test_full_ui_original_crash_is_valid_negative(self):
        row=stage.classify("full-prewarm",receipt(False,False),
                           markers(*PHASES[:3],PREWARM[0]))
        self.assertEqual(row["exit_signal"],"SIGABRT")

    def test_skipped_original_ui_can_still_render(self):
        row=stage.classify("full-skipped",receipt(),markers(
            "STAGE29_SDL3_INPUT_SKIPPED","STAGE42_FULL_UI_ENTERED"))
        self.assertTrue(row["original_ui_entered"])
        self.assertFalse(row["original_sdl3_poll_invoked"])

    def test_skipped_mode_cannot_claim_input_poll(self):
        with self.assertRaisesRegex(ValueError,"disabled input"):
            stage.classify("full-skipped",receipt(),markers(
                "STAGE29_SDL3_INPUT_SKIPPED","STAGE42_FULL_UI_ENTERED",
                "STAGE42_INPUT_POLL_FIRST"))

    def test_ctor_only_cannot_claim_original_ui(self):
        with self.assertRaisesRegex(ValueError,"ctor-only"):
            stage.classify("ctor-prewarm",receipt(),markers(
                *PHASES,*PREWARM,"STAGE42_FULL_UI_ENTERED"))

    def test_survival_without_actual_handoff_rejected(self):
        with self.assertRaisesRegex(ValueError,"prewarm handoff"):
            stage.classify("full-prewarm",receipt(),markers(
                "STAGE29_SDL3_INPUT_ENABLED","STAGE42_FULL_UI_ENTERED"))

    def test_poll_requires_original_ui(self):
        with self.assertRaisesRegex(ValueError,"without original UI"):
            stage.classify("full-prewarm",receipt(False,False),markers(
                "STAGE29_SDL3_INPUT_ENABLED","STAGE42_INPUT_POLL_FIRST"))

    def test_connected_requires_poll(self):
        with self.assertRaisesRegex(ValueError,"before poll"):
            stage.classify("full-prewarm",receipt(False,False),markers(
                "STAGE29_SDL3_INPUT_ENABLED","STAGE42_FULL_UI_ENTERED",
                "STAGE42_CONTROLLER_CONNECTED"))

    def test_false_game_claim_rejected(self):
        data=receipt()
        data["gameplay_verified"]=True
        with self.assertRaisesRegex(ValueError,"unsupported"):
            stage.classify("full-skipped",data,markers("STAGE29_SDL3_INPUT_SKIPPED"))

    def test_source_phase_order_must_match(self):
        with self.assertRaisesRegex(ValueError,"unordered"):
            stage.classify("full-prewarm",receipt(False,False),markers(
                "STAGE29_SDL3_INPUT_ENABLED",PHASES[2]))

    def test_no_private_input_or_paths_in_derived_evidence(self):
        data=receipt()
        data["diagnostic_messages"]=["SECRET /Users/User/ROM"]
        row=stage.classify("full-prewarm",data,markers(
            *PHASES,*PREWARM,"STAGE42_FULL_UI_ENTERED",
            "STAGE42_INPUT_POLL_FIRST")+"\nPRIVATE BUTTON IDENTIFIERS\n")
        self.assertNotIn("SECRET",repr(row))
        self.assertNotIn("PRIVATE",repr(row))

if __name__=="__main__":
    unittest.main()
