"""Stage45 source-bound original InputSnapshot virtual contract assertions."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import audit_stage45_original_snapshot as stage

SHA="f"*64
BASE=("STAGE40_PREWARM_MAIN_BEFORE_EFRAME",
      "STAGE40_PREWARM_MAIN_READY",
      "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED",
      "STAGE42_FULL_UI_ENTERED",
      "STAGE42_INPUT_POLL_FIRST")
COMPLETE=BASE+stage.SNAP

def source(*markers):
    return "".join(x+"\n" for x in markers)

def receipt(alive=True,window=True):
    return {
        "probe":"no_nro_gui_process_only","duration_limit_seconds":12,
        "emulator_sha256":SHA,
        "nro_verified":False,"gameplay_verified":False,"gui_verified":False,
        "outcome":"alive_without_gui_verification" if alive else "exited_nonzero",
        "alive_at_deadline":alive,"window_found":window,
        "window_probe":"own_visible_window_observed" if window else "not_requested",
    }

class OriginalSnapshotAuditTests(unittest.TestCase):
    def test_authentic_original_full_snapshot_roundtrip(self):
        row=stage.classify("virtual-on",receipt(),source(*COMPLETE))
        self.assertTrue(row["original_snapshot_contract_passed"])
        self.assertTrue(row["original_snapshot_south_button_and_left_axis_readback"])
        self.assertTrue(row["original_snapshot_button_release_and_neutral_axis_readback"])

    def test_control_without_injection(self):
        row=stage.classify("virtual-off",receipt(),source(*BASE))
        self.assertFalse(row["real_input_backend_virtual_snapshot_test_requested"])

    def test_reject_control_with_synthetic_marker(self):
        with self.assertRaisesRegex(ValueError,"disabled"):
            stage.classify("virtual-off",receipt(),source(*BASE,stage.SNAP[0]))

    def test_missing_real_original_ui_rejected_when_alive(self):
        with self.assertRaisesRegex(ValueError,"UI or input poll"):
            stage.classify("virtual-on",receipt(),source(*stage.SNAP))

    def test_missing_request_rejected(self):
        with self.assertRaisesRegex(ValueError,"did not start"):
            stage.classify("virtual-on",receipt(False,False),
                source("STAGE45_VIRTUAL_SNAPSHOT_BEGIN"))

    def test_falsified_contract_without_release_rejected(self):
        partial=tuple(x for x in COMPLETE if x!="STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK")
        with self.assertRaisesRegex(ValueError,"lacks"):
            stage.classify("virtual-on",receipt(),source(*partial))

    def test_contradictory_failure_rejected(self):
        with self.assertRaisesRegex(ValueError,"contradictory"):
            stage.classify("virtual-on",receipt(),source(*COMPLETE,
                "STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_FAILED"))

    def test_real_negative_does_not_become_game_claim(self):
        row=stage.classify("virtual-on",receipt(False,False),
            source("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED",
                   "STAGE45_VIRTUAL_SNAPSHOT_BEGIN",
                   "STAGE45_VIRTUAL_SNAPSHOT_ATTACH_FAILED"))
        self.assertFalse(row["original_snapshot_contract_passed"])

    def test_original_only_readback_not_raw_data(self):
        result=stage.classify("virtual-on",receipt(),source(*COMPLETE)+
            "SDL input button=secret /Users/runner/my-device\n")
        self.assertNotIn("secret",repr(result))
        self.assertNotIn("Users",repr(result))
        self.assertNotIn("my-device",repr(result))

    def test_fake_gameplay_assertion_rejected(self):
        data=receipt()
        data["gameplay_verified"]=True
        with self.assertRaisesRegex(ValueError,"fake"):
            stage.classify("virtual-on",data,source(*COMPLETE))

    def test_duplicate_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicated"):
            stage.classify("virtual-on",receipt(),source(*COMPLETE,
                "STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED"))

    def test_unknown_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError,"unknown"):
            stage.classify("virtual-on",receipt(),source(*COMPLETE,
                "STAGE45_PRIVATE_CONTROLLER_NAME_LEAK"))

    def test_false_window_rejected(self):
        bad=receipt()
        bad["window_probe"]="not_requested"
        with self.assertRaisesRegex(ValueError,"window"):
            stage.classify("virtual-on",bad,source(*COMPLETE))

    def test_release_without_press_rejected(self):
        m=("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED","STAGE45_VIRTUAL_SNAPSHOT_BEGIN",
           "STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK")
        with self.assertRaisesRegex(ValueError,"release without"):
            stage.classify("virtual-on",receipt(False,False),source(*m))

if __name__=="__main__":
    unittest.main()
