"""Stage47 source-bound audit regressions for exact safe Rust SDL3."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_rust_sdl3 as stage

def lines(*markers):
    return "".join(f"STAGE47_{m}\n" for m in markers)

class RustSDL3AuditTests(unittest.TestCase):
    def test_success_direct(self):
        v=stage.inspect("direct-update",0,lines(*stage.EXPECTED))
        self.assertTrue(v["actual_rust_contract_passed"])
        self.assertTrue(v["real_sdl3_release_neutral_readback"])

    def test_success_event_pump(self):
        v=stage.inspect("event-pump",0,lines(*stage.EXPECTED))
        self.assertTrue(v["real_sdl3_button_axis_readback"])

    def test_failed_attach_preserved(self):
        seq=stage.EXPECTED[:4]+("ATTACH_FAILED",)
        v=stage.inspect("direct-update",3,lines(*seq))
        self.assertFalse(v["virtual_gamepad_opened"])

    def test_readback_failure_not_success(self):
        seq=stage.EXPECTED[:5]+("READBACK_FAILED",)
        v=stage.inspect("direct-update",3,lines(*seq))
        self.assertFalse(v["actual_rust_contract_passed"])

    def test_released_required(self):
        with self.assertRaisesRegex(ValueError,"zero status"):
            stage.inspect("direct-update",0,lines(*stage.EXPECTED[:6]))

    def test_reordered_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError,"reordered"):
            stage.inspect("event-pump",3,lines("PROCESS_ENTERED","BUTTON_AND_AXIS_OK"))

    def test_repeated_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError,"repeated"):
            stage.inspect("event-pump",3,lines("PROCESS_ENTERED","PROCESS_ENTERED"))

    def test_unknown_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError,"unknown"):
            stage.inspect("event-pump",3,lines("PROCESS_ENTERED","REAL_USER_ID"))

    def test_missing_source_start_rejected(self):
        with self.assertRaisesRegex(ValueError,"entry"):
            stage.inspect("event-pump",3,lines("BEFORE_SDL_INIT"))

    def test_no_private_log_fields(self):
        v=stage.inspect("direct-update",0,lines(*stage.EXPECTED)+
                        "/Users/private/SomeGame.nro TOKEN=something\n")
        self.assertNotIn("SomeGame",repr(v))
        self.assertNotIn("something",repr(v))

    def test_crash_not_success(self):
        v=stage.inspect("direct-update",-6,lines(*stage.EXPECTED[:4]))
        self.assertEqual(v["exit_signal"],"SIG6")
        self.assertFalse(v["actual_rust_contract_passed"])

    def test_timeout_not_exit_code(self):
        v=stage.inspect("direct-update",None,lines(*stage.EXPECTED[:3]),True)
        self.assertEqual(v["status"],"timeout")
        with self.assertRaisesRegex(ValueError,"contradiction"):
            stage.inspect("direct-update",0,lines(*stage.EXPECTED),True)

    def test_contract_marker_with_crash_is_not_success(self):
        with self.assertRaisesRegex(ValueError,"nonzero process exit"):
            stage.inspect("direct-update",-6,lines(*stage.EXPECTED))

    def test_contract_marker_with_timeout_is_not_success(self):
        with self.assertRaisesRegex(ValueError,"timeout/nonzero"):
            stage.inspect("direct-update",None,lines(*stage.EXPECTED),True)

if __name__=="__main__":
    unittest.main()
