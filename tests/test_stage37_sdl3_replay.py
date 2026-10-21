"""Stage37 source-specific own-process marker rules."""
from pathlib import Path
import sys
import tempfile
import json
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stage37_sdl3_replay as m

def receipt():
    return {
        "probe":"no_nro_gui_process_only",
        "nro_verified":False,"gameplay_verified":False,"gui_verified":False,
        "outcome":"alive_without_gui_verification","alive_at_deadline":True,
        "window_found":True,"emulator_sha256":"a"*64,
    }

ENTRY="STAGE26_HORIZON_CTOR_ENTERED"
RETURN="STAGE26_HORIZON_CTOR_RETURNED"
SKIP="STAGE29_SDL3_INPUT_SKIPPED"
ENABLE="STAGE29_SDL3_INPUT_ENABLED"
CONTROL="STAGE25_HOST_INIT_MINIMAL_APP_ENTERED"
PHASE="STAGE28_HORIZON_CTOR_PHASE_03_BEFORE_INPUT"

def src(name):
    if name=="ctor-input-enabled": return ENTRY+"\n"+PHASE+"\n"+ENABLE+"\n"
    if name=="ctor-input-skipped": return ENTRY+"\n"+PHASE+"\n"+SKIP+"\n"+RETURN+"\n"
    if name=="full-input-skipped": return PHASE+"\n"+SKIP+"\n"
    return CONTROL+"\n"

class ReplayTests(unittest.TestCase):
    def test_all_four_valid_modes(self):
        for name in m.VARIANTS:
            with self.subTest(name=name):
                value=m.observe(name,receipt(),src(name))
                self.assertEqual(value["own_window_found"],True)
                if name=="full-input-skipped":
                    self.assertFalse(value["stage26_wrapper_entered"])
                    self.assertTrue(value["sdl3_skipped_marker"])

    def test_original_full_ctor_not_required_to_emit_wrapper(self):
        evidence=m.observe("full-input-skipped",receipt(),PHASE+"\n"+SKIP)
        self.assertFalse(evidence["stage26_wrapper_entered"])

    def test_old_false_assumption_is_caught_in_wrapper_only(self):
        with self.assertRaisesRegex(ValueError,"wrapper was not entered"):
            m.observe("ctor-input-enabled",receipt(),PHASE+"\n"+ENABLE)

    def test_contradictory_sdl_branches_rejected(self):
        with self.assertRaisesRegex(ValueError,"mutually exclusive"):
            m.observe("full-input-skipped",receipt(),PHASE+"\n"+SKIP+"\n"+ENABLE)

    def test_control_must_not_initialize_input(self):
        with self.assertRaisesRegex(ValueError,"negative control"):
            m.observe("full-init-minimal",receipt(),CONTROL+"\n"+SKIP)

    def test_nro_and_game_claims_rejected(self):
        for key in ("nro_verified","gameplay_verified","gui_verified"):
            r=receipt()
            r[key]=True
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"invalid game"):
                m.observe("full-input-skipped",r,src("full-input-skipped"))

    def test_marker_substring_not_enough(self):
        with self.assertRaisesRegex(ValueError,"negative control"):
            m.observe("full-init-minimal",receipt(),
                "a log quoting STAGE25_HOST_INIT_MINIMAL_APP_ENTERED text\n")

    def test_full_classifier_identical_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in m.VARIANTS:
                run=root/name
                run.mkdir()
                (run/"gui_process_probe.json").write_text(json.dumps(receipt()))
                (run/"nexium-stdout-stderr.log").write_text(src(name))
            result=m.classify(root)
            self.assertEqual(len(result["variants"]),4)
            self.assertFalse(result["gameplay_verified"])
            self.assertFalse(result["guest_instructions_verified"])
            r=receipt();r["emulator_sha256"]="b"*64
            (root/"full-input-skipped"/"gui_process_probe.json").write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,"different native Mach-O"):
                m.classify(root)

if __name__=="__main__":
    unittest.main()
