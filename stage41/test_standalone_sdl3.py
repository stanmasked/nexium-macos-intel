"""Stage41 native source-bound audit regression tests (no SDL3 runner needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_standalone_sdl3 as stage


def log(*names):
    return "".join("STAGE41_" + name + "\n" for name in names)


BARE = ("PROCESS_ENTERED", "BEFORE_HINTS", "AFTER_HINTS",
        "BEFORE_SDL_INIT", "AFTER_SDL_INIT", "BEFORE_GAMEPAD",
        "AFTER_GAMEPAD", "AFTER_QUIT")
APPKIT = ("PROCESS_ENTERED", "BEFORE_APPKIT", "AFTER_APPKIT") + BARE[1:]


class Stage41AuditTests(unittest.TestCase):
    def test_bare_full_success(self):
        row = stage.audit_one("bare", 0, log(*BARE))
        self.assertTrue(row["gamepad_initialization_returned"])
        self.assertTrue(row["clean_sdl_quit"])

    def test_appkit_full_success(self):
        row = stage.audit_one("appkit", 0, log(*APPKIT))
        self.assertTrue(row["gamepad_initialization_returned"])

    def test_bare_abort_before_gamepad_return(self):
        row = stage.audit_one("bare", -6, log(*BARE[:6]))
        self.assertEqual(row["exit_signal"], "SIG6")
        self.assertFalse(row["gamepad_initialization_returned"])

    def test_native_abort_during_appkit_is_kept(self):
        row = stage.audit_one("appkit", -6, log("PROCESS_ENTERED", "BEFORE_APPKIT"))
        self.assertEqual(row["outcome"], "exited_nonzero")

    def test_explicit_gamepad_init_failure(self):
        row = stage.audit_one("bare", 4, log(*BARE[:6], "GAMEPAD_FAILED"))
        self.assertEqual(row["exit_code"], 4)

    def test_explicit_sdl_init_failure(self):
        row = stage.audit_one("bare", 3, log(*BARE[:4], "SDL_INIT_FAILED"))
        self.assertFalse(row["gamepad_initialization_returned"])

    def test_missing_entry_rejected(self):
        with self.assertRaisesRegex(ValueError, "entry"):
            stage.audit_one("bare", 0, log(*BARE[1:]))

    def test_gamepad_success_cannot_omit_quit(self):
        with self.assertRaisesRegex(ValueError, "shutdown"):
            stage.audit_one("bare", 0, log(*BARE[:-1]))

    def test_bare_control_cannot_emulate_appkit(self):
        with self.assertRaisesRegex(ValueError, "AppKit"):
            stage.audit_one("bare", -6, log("PROCESS_ENTERED", "BEFORE_APPKIT"))

    def test_reordered_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            stage.audit_one("bare", -6, log("PROCESS_ENTERED", "AFTER_SDL_INIT"))

    def test_duplicate_source_phase_rejected(self):
        with self.assertRaisesRegex(ValueError, "repeated"):
            stage.audit_one("bare", -6, log("PROCESS_ENTERED", "PROCESS_ENTERED"))

    def test_unknown_source_phase_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            stage.audit_one("bare", -6, log("PROCESS_ENTERED", "SECRET"))

    def test_timeout_classified_separately(self):
        row = stage.audit_one("bare", None, log(*BARE[:3]), timeout=True)
        self.assertEqual(row["outcome"], "timeout")

    def test_timeout_returncode_contradiction_rejected(self):
        with self.assertRaisesRegex(ValueError, "contradiction"):
            stage.audit_one("bare", 0, log(*BARE), timeout=True)

    def test_no_private_native_logs_leak(self):
        row = stage.audit_one("appkit", -6, log(*APPKIT[:3]) +
                              "/Users/somebody/PrivateFile\nTOKEN=secret\n")
        self.assertNotIn("Users", repr(row))
        self.assertNotIn("secret", repr(row))

    def test_control_mode_unknown_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            stage.audit_one("accidental", 0, log(*BARE))


if __name__ == "__main__":
    unittest.main()
