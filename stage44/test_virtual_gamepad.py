"""Stage44 fail-closed audits for virtual synthetic SDL3 input on native Mac."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_virtual_gamepad as stage


def emit(*names):
    return "".join("STAGE44_" + x + "\n" for x in names)

class VirtualSDL3AuditTests(unittest.TestCase):
    def test_complete_virtual_roundtrip_bare(self):
        result=stage.classify("bare", 0, emit(*stage.SUCCESS))
        self.assertTrue(result["virtual_button_and_axis_readback"])
        self.assertTrue(result["virtual_release_readback"])

    def test_complete_virtual_roundtrip_appkit(self):
        phases=("PROCESS_ENTERED","BEFORE_APPKIT","AFTER_APPKIT") + stage.SUCCESS[1:]
        result=stage.classify("appkit",0,emit(*phases))
        self.assertTrue(result["clean_detach"])

    def test_early_injection_failure_remains_negative_result(self):
        phases=stage.SUCCESS[:7]+("INJECTION_FAILED",)
        result=stage.classify("bare",6,emit(*phases))
        self.assertFalse(result["virtual_button_and_axis_readback"])

    def test_success_requires_release(self):
        with self.assertRaisesRegex(ValueError,"success"):
            stage.classify("bare",0,emit(*stage.SUCCESS[:-3]))

    def test_duplicate_markers_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            stage.classify("bare",1,emit("PROCESS_ENTERED","PROCESS_ENTERED"))

    def test_out_of_order_readback_rejected(self):
        with self.assertRaisesRegex(ValueError,"ordering"):
            stage.classify("bare",1,emit("PROCESS_ENTERED","RELEASE_OBSERVED"))

    def test_unknown_labels_rejected(self):
        with self.assertRaisesRegex(ValueError,"ordering"):
            stage.classify("bare",1,emit("PROCESS_ENTERED","PRIVATE_USER_INPUT"))

    def test_no_raw_private_logs_are_published(self):
        result=stage.classify("bare",0,emit(*stage.SUCCESS)+"\nPASSWORD=secret\n/Users/alice/private\n")
        self.assertNotIn("PASSWORD",repr(result))
        self.assertNotIn("alice",repr(result))

    def test_negative_signal_is_not_clean_exit(self):
        result=stage.classify("bare",-6,emit(*stage.SUCCESS[:5]))
        self.assertEqual(result["exit_signal"],"SIG6")
        self.assertFalse(result["clean_detach"])

    def test_timeout_does_not_count_as_complete(self):
        result=stage.classify("bare",None,emit(*stage.SUCCESS[:3]),timeout=True)
        self.assertEqual(result["exit_type"],"timeout")
        self.assertFalse(result["virtual_gamepad_opened"])

    def test_wrong_mode_rejected(self):
        with self.assertRaisesRegex(ValueError,"unknown"):
            stage.classify("unknown",0,emit(*stage.SUCCESS))

if __name__=="__main__":
    unittest.main()
