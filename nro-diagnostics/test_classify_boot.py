"""Stage30 strict public-NRO receipt classifier synthetic tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("classify_boot.py")
spec = importlib.util.spec_from_file_location("safe_clean_nro", SCRIPT)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
DIGEST = "a" * 64
BASE = {"probe": "no_nro_gui_process_only", "emulator_sha256": DIGEST,
        "nro_verified": False, "gameplay_verified": False,
        "outcome": "alive_without_gui_verification", "alive_at_deadline": True,
        "window_found": True}
GUEST = {"emulator_sha256": DIGEST, "nro_file": "nexium_clean_smoke.nro",
         "nro_sha256": DIGEST, "status": "timeout_alive_unverified",
         "unique_frame_hashes": 0, "snapshots": [], "gameplay_verified": False}
EXPECTED = {"sha256": DIGEST}
FLAGS = {
    "auto_loaded_nro_log_marker": False, "nro_load_error_log_marker": False,
    "boot_command_log_marker": False, "winit_reentrant_panic": False,
    "log_data_examined": False,
}


class ClassificationTests(unittest.TestCase):
    def test_alive_guest_without_logs_is_not_success(self):
        report = stage.classify(BASE, GUEST, EXPECTED, FLAGS)
        self.assertFalse(report["actual_guest_instructions_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertEqual(report["conclusion"], "PROCESS_OBSERVED_GUEST_LOAD_UNVERIFIED")

    def test_auto_loader_marker_is_not_guest_execution(self):
        report = stage.classify(
            BASE, GUEST, EXPECTED, {**FLAGS, "auto_loaded_nro_log_marker": True})
        self.assertEqual(report["conclusion"], "NRO_LOADER_LOG_MARKER_OBSERVED")
        self.assertFalse(report["actual_guest_instructions_verified"])
        self.assertFalse(report["pixel_correctness_verified"])

    def test_abort_not_disguised_by_boot_marker(self):
        report = stage.classify(BASE, {**GUEST, "status": "exited_nonzero",
                                       "exit_code": -6}, EXPECTED,
                                {**FLAGS, "auto_loaded_nro_log_marker": True,
                                 "winit_reentrant_panic": True})
        self.assertEqual(report["conclusion"], "PROCESS_CRASHED_OR_EXITED")
        self.assertTrue(report["clean_nro_argument_run"]["winit_reentrant_panic"])

    def test_private_or_wrong_nro_digest_rejected(self):
        with self.assertRaisesRegex(ValueError, "digest"):
            stage.classify(BASE, GUEST, {"sha256": "b" * 64}, FLAGS)
        with self.assertRaisesRegex(ValueError, "public clean NRO"):
            stage.classify(BASE, {**GUEST, "nro_file": "private.nro"},
                           EXPECTED, FLAGS)

    def test_wrong_emulator_rejected(self):
        with self.assertRaisesRegex(ValueError, "same Intel binary"):
            stage.classify({**BASE, "emulator_sha256": "f" * 64},
                           GUEST, EXPECTED, FLAGS)

    def test_guest_gameplay_claim_rejected(self):
        with self.assertRaisesRegex(ValueError, "gameplay"):
            stage.classify(BASE, {**GUEST, "gameplay_verified": True},
                           EXPECTED, FLAGS)

    def test_only_bounded_log_keywords_not_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "nexium-console.log"
            log.write_text("Auto-loaded NRO: /Users/private/test.nro (CPU: rustarmic)\n"
                           "tried to handle event while another event is currently being handled\n")
            flags = stage.marker_flags(log, root / "data-root/logs")
            self.assertTrue(flags["auto_loaded_nro_log_marker"])
            self.assertTrue(flags["winit_reentrant_panic"])
            self.assertNotIn("Users", str(flags))
            self.assertNotIn("private", str(flags))

    def test_late_failed_load_marker_must_override_auto_loaded_marker(self):
        report = stage.classify(BASE, GUEST, EXPECTED,
                                {**FLAGS, "auto_loaded_nro_log_marker": True,
                                 "nro_load_error_log_marker": True})
        self.assertEqual(report["conclusion"],
                         "PROCESS_OBSERVED_GUEST_LOAD_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
