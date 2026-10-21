"""Synthetic Stage30 guarantees: absent checkpoints are data, not assertions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stage30_original_phase_replay as stage


def row():
    return {
        "probe":"no_nro_gui_process_only",
        "emulator_sha256":stage.EXPECTED_SHA256,
        "nro_verified":False, "gameplay_verified":False, "gui_verified":False,
        "outcome":"exited_nonzero", "exit_signal":"SIGABRT",
        "alive_at_deadline":False, "window_found":False,
    }


def authentic_rows():
    return {
        "full-horizonapp":(row(),"STAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n"),
        "constructor-only":(row(),"STAGE26_HORIZON_CTOR_ENTERED\nSTAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n"),
        "full-init-minimal":(row(),"STAGE25_HOST_INIT_MINIMAL_APP_ENTERED\n"),
    }


class Stage30OriginalPhaseReplay(unittest.TestCase):
    def test_true_partial_prefix_accepted_without_inventing_cause(self):
        data=stage.phase_evidence("STAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n")
        self.assertEqual(data["contiguous_prefix_length"],1)
        self.assertEqual(data["unobserved_predecessors_before_highest"],[])
        self.assertEqual(data["last_emitted_phase"],"00_BEFORE_THEME")

    def test_noncontiguous_marker_list_is_diagnostic_not_failure(self):
        data=stage.phase_evidence("STAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n"+
                                  "STAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT\n")
        self.assertEqual(data["contiguous_prefix_length"],1)
        self.assertEqual(data["unobserved_predecessors_before_highest"],
                         ["01_BEFORE_UI_AUDIO","02_AFTER_UI_AUDIO"])
        self.assertEqual(data["last_emitted_phase"],"03_BEFORE_INPUT")

    def test_absence_of_any_phase_is_meaningful(self):
        data=stage.phase_evidence("thread main panicked\n")
        self.assertIsNone(data["highest_index_observed"])
        self.assertIsNone(data["last_emitted_phase"])
        self.assertFalse(data["phase_trace_present"])

    def test_requires_full_line_not_log_quotation(self):
        data=stage.phase_evidence('source: eprintln!("STAGE28_HORIZON_CTOR_PHASE_10_BEFORE_RESCAN");\n')
        self.assertFalse(data["phase_trace_present"])

    def test_duplicate_marker_does_not_masquerade_as_single_call(self):
        line="STAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n"
        data=stage.phase_evidence(line+line)
        self.assertEqual(data["duplicate_phase_identifiers"],["00_BEFORE_THEME"])

    def test_reject_unknown_whitelisted_phase(self):
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            stage.phase_evidence("STAGE28_HORIZON_CTOR_PHASE_99_FORGED\n")

    def test_authentic_triplet_includes_crash_and_negative_control(self):
        data=stage.classify_rows(authentic_rows())
        self.assertEqual(data["single_original_binary_sha256"],stage.EXPECTED_SHA256)
        self.assertFalse(data["root_cause_verified"])
        self.assertFalse(data["raw_private_logs_uploaded"])
        self.assertEqual(data["variants"]["constructor-only"]["outcome"],"exited_nonzero")

    def test_same_executable_and_no_game_enforced(self):
        d=authentic_rows()
        d["full-horizonapp"][0]["emulator_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"authenticated"):
            stage.classify_rows(d)
        d=authentic_rows()
        d["constructor-only"][0]["gameplay_verified"]=True
        with self.assertRaisesRegex(ValueError,"unsupported"):
            stage.classify_rows(d)

    def test_no_constructor_marker_or_bad_negative_control_fails(self):
        d=authentic_rows()
        d["constructor-only"]=(row(),"STAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n")
        with self.assertRaisesRegex(ValueError,"never entered"):
            stage.classify_rows(d)
        d=authentic_rows()
        d["full-init-minimal"]=(row(),"STAGE25_HOST_INIT_MINIMAL_APP_ENTERED\nSTAGE28_HORIZON_CTOR_PHASE_00_BEFORE_THEME\n")
        with self.assertRaisesRegex(ValueError,"negative control"):
            stage.classify_rows(d)

    def test_return_without_last_phase_is_invalid(self):
        d=authentic_rows()
        d["constructor-only"]=(row(),"STAGE26_HORIZON_CTOR_ENTERED\nSTAGE26_HORIZON_CTOR_RETURNED\n")
        with self.assertRaisesRegex(ValueError,"return marker"):
            stage.classify_rows(d)


if __name__=="__main__":
    unittest.main()
