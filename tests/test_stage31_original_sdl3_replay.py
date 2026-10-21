"""Stage31: original Intel process receipt verification synthetic tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stage31_original_sdl3_replay as stage


def receipt(alive, signal=None, window=False):
    return {
        "probe":"no_nro_gui_process_only",
        "emulator_sha256":stage.PINNED_SHA256,
        "nro_verified":False,"gameplay_verified":False,"gui_verified":False,
        "outcome":"alive_without_gui_verification" if alive else "exited_nonzero",
        "exit_signal":signal,
        "alive_at_deadline":alive,"window_found":window,
    }


def valid_rows():
    modes = {
        "ctor-input-enabled":(receipt(False,"SIGABRT"),
            "STAGE26_HORIZON_CTOR_ENTERED\nSTAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT\n"
            "STAGE29_SDL3_INPUT_ENABLED\n"),
        "ctor-input-skipped":(receipt(True,window=True),
            "STAGE26_HORIZON_CTOR_ENTERED\nSTAGE29_SDL3_INPUT_SKIPPED\n"
            "STAGE26_HORIZON_CTOR_RETURNED\n"),
        "full-input-skipped":(receipt(True,window=True),
            "STAGE29_SDL3_INPUT_SKIPPED\nSTAGE28_HORIZON_CTOR_PHASE_12_BEFORE_RETURN\n"),
        "full-init-minimal":(receipt(True,window=True),
            "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED\n"),
    }
    return {(m,rep):(r.copy(),c) for m,(r,c) in modes.items()
            for rep in stage.REPETITIONS}


class Stage31GenuineIntelTests(unittest.TestCase):
    def test_two_repeats_of_all_four_modes(self):
        data=stage.classify_all(valid_rows())
        self.assertEqual(data["result"],"EIGHT_REAL_NATIVE_INTEL_PROCESS_RUNS_CLASSIFIED")
        self.assertEqual(data["modes"]["ctor-input-enabled"]["sigabrt_count"],2)
        self.assertEqual(data["modes"]["full-input-skipped"]["survived_12s_count"],2)
        self.assertFalse(data["causal_root_cause_proven"])

    def test_normal_full_gui_does_not_require_stage26_wrapper_marker(self):
        d=stage.classify_one("full-input-skipped",receipt(True),
                             "STAGE29_SDL3_INPUT_SKIPPED\n")
        self.assertFalse(d["horizon_constructor_entered"])
        self.assertTrue(d["actual_sdl3_input_skipped_marker"])

    def test_inert_wrapper_requires_constructor_enter_and_return_if_alive(self):
        with self.assertRaisesRegex(ValueError,"return"):
            stage.classify_one("ctor-input-skipped",receipt(True),
                               "STAGE26_HORIZON_CTOR_ENTERED\nSTAGE29_SDL3_INPUT_SKIPPED\n")

    def test_sdl3_enabled_crash_before_constructor_return_stays_evidence(self):
        p=stage.classify_one("ctor-input-enabled",receipt(False,"SIGABRT"),
                             "STAGE26_HORIZON_CTOR_ENTERED\n"
                             "STAGE29_SDL3_INPUT_ENABLED\n")
        self.assertFalse(p["horizon_constructor_returned"])
        self.assertEqual(p["exit_signal"],"SIGABRT")

    def test_bypass_switch_without_actual_branch_rejected_on_survival(self):
        with self.assertRaisesRegex(ValueError,"bypass"):
            stage.classify_one("full-input-skipped",receipt(True),"")
        with self.assertRaisesRegex(ValueError,"SDL3 skip"):
            stage.classify_one("ctor-input-skipped",receipt(True),
                               "STAGE26_HORIZON_CTOR_ENTERED\nSTAGE26_HORIZON_CTOR_RETURNED\n")

    def test_negative_control_does_not_execute_horizon(self):
        with self.assertRaisesRegex(ValueError,"control"):
            stage.classify_one("full-init-minimal",receipt(True),
                               "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED\nSTAGE29_SDL3_INPUT_SKIPPED\n")

    def test_refuses_wrong_binary_and_unverified_game(self):
        r=receipt(True)
        r["emulator_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"original Stage29"):
            stage.classify_one("full-init-minimal",r,
                               "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED\n")
        r=receipt(True)
        r["nro_verified"]=True
        with self.assertRaisesRegex(ValueError,"unsupported"):
            stage.classify_one("full-init-minimal",r,
                               "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED\n")

    def test_requires_all_eight_authentic_processes(self):
        rows=valid_rows()
        rows.pop(("full-init-minimal","2"))
        with self.assertRaisesRegex(ValueError,"two authentic"):
            stage.classify_all(rows)

    def test_deny_conflicting_sdl3_markers(self):
        with self.assertRaisesRegex(ValueError,"mutually exclusive"):
            stage.classify_one("full-input-skipped",receipt(True),
                               "STAGE29_SDL3_INPUT_SKIPPED\nSTAGE29_SDL3_INPUT_ENABLED\n")

    def test_actual_phase_emission_is_not_inferred_from_missing_marker(self):
        d=stage.classify_one("ctor-input-enabled",receipt(False,"SIGABRT"),
                             "STAGE26_HORIZON_CTOR_ENTERED\n"
                             "STAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n"
                             "STAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT\n"
                             "STAGE29_SDL3_INPUT_ENABLED\n")
        self.assertEqual(d["actual_constructor_phases_in_emission_order"],
                         ["00_BEFORE_THEME","03_BEFORE_INPUT"])
        self.assertEqual(d["last_emitted_phase"],"03_BEFORE_INPUT")

    def test_no_original_private_text_echo(self):
        rows=valid_rows()
        result=stage.classify_all(rows)
        self.assertNotIn("private-root",str(result))
        self.assertFalse(result["original_console_or_png_uploaded"])


if __name__=="__main__":
    unittest.main()
