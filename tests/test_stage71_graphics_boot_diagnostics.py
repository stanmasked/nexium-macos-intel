"""Stage71 safe original guest graphical boot milestone classifications."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from classify_intel_guest_graphics_boot import inspect_original_graphics_boot

MACHO, NRO = "a" * 64, "b" * 64


class Stage71OriginalGraphicsBootDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.logger = self.root / "data-root" / "logs"
        self.logger.mkdir(parents=True)
        self.smoke = {
            "emulator_sha256": MACHO, "nro_sha256": NRO,
            "status": "timeout_alive_unverified", "gameplay_verified": False,
        }
        self.update()

    def update(self, log=None):
        (self.root / "smoke_result.json").write_text(json.dumps(self.smoke))
        if log is not None:
            (self.logger / "nexium-original.log").write_text(log)

    def classify(self):
        return inspect_original_graphics_boot(self.root, MACHO, NRO)

    def test_absent_logger_is_unverified_not_boot_pass(self):
        r = self.classify()
        self.assertEqual(r["observed_category"], "original_filelogger_unavailable")
        self.assertFalse(r["original_graphics_svc_start_observed"])

    def test_autoload_missing_is_distinct(self):
        self.update(log="Unrelated original host logger line")
        self.assertEqual(self.classify()["observed_category"],
                         "nro_autoload_not_observed")

    def test_boot_start_missing_is_distinct(self):
        self.update(log="Auto-loaded NRO: synthetic path")
        self.assertEqual(self.classify()["observed_category"],
                         "original_guest_boot_not_observed")

    def test_context_missing_is_distinct(self):
        self.update(log="Auto-loaded NRO:\nBooting NRO:\n")
        self.assertEqual(self.classify()["observed_category"],
                         "original_guest_context_not_observed")

    def test_original_guest_start_marker_classified_but_no_frame_claim(self):
        self.update(log=("Auto-loaded NRO:\nBooting NRO:\n"
                         "cpu memory null policy:\n"
                         "svcOutputDebugString:\n"
                         "OutputDebugString: STAGE67_GUEST_GRAPHICS_START"))
        x = self.classify()
        self.assertEqual(x["observed_category"], "graphics_guest_svc_start_observed")
        self.assertFalse(x["guest_gpu_frames_verified"])
        self.assertFalse(x["guest_framebuffer_runtime_completed"])
        self.assertFalse(x["main_merge_approved"])

    def test_boot_failure_preempts_other_markers(self):
        self.update(log=("Auto-loaded NRO:\nBooting NRO:\n"
                         "Boot failed:\nOutputDebugString: STAGE67_GUEST_GRAPHICS_START"))
        self.assertEqual(self.classify()["observed_category"],
                         "original_guest_boot_failed")

    def test_context_ready_without_guest_marker_remains_unverified(self):
        self.update(log="Auto-loaded NRO:\nBooting NRO:\ncpu memory null policy:")
        self.assertEqual(self.classify()["observed_category"],
                         "graphics_guest_svc_start_not_observed")

    def test_binary_identity_mismatch_rejected(self):
        self.update(log="Booting NRO:")
        with self.assertRaisesRegex(ValueError, "binary/NRO mismatch"):
            inspect_original_graphics_boot(self.root, "c" * 64, NRO)

    def test_nro_identity_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "binary/NRO mismatch"):
            inspect_original_graphics_boot(self.root, MACHO, "c" * 64)

    def test_malformed_smoke_process_status_rejected(self):
        self.smoke["status"] = "something_unsupported"
        self.update()
        with self.assertRaisesRegex(ValueError, "state untrusted"):
            self.classify()

    def test_multiple_original_loggers_rejected(self):
        self.update(log="Booting NRO:")
        (self.logger / "nexium-second.log").write_text("unrelated process")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.classify()

    def test_symlinked_original_logger_rejected(self):
        target = self.root / "outside.log"
        target.write_text("private content")
        (self.logger / "nexium-original.log").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.classify()

    def test_duplicate_receipt_property_rejected(self):
        self.update()
        path = self.root / "smoke_result.json"
        raw = path.read_text()
        path.write_text(raw[:-1] + ',"emulator_sha256":"' + MACHO + '"}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.classify()


if __name__ == "__main__":
    unittest.main()
