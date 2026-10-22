"""Stage68 bounded actual guest OutputDebugString classification fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from probe_intel_graphics_runtime import (
    FAILURE_MARKERS, PROGRESS_MARKERS, MARKER_PREFIX,
    source_graphics_audit,
)
from observe_intel_integrated_window import inspect_gui_evidence

MACHO = "a" * 64
NRO = "b" * 64


class Stage68ActualGuestGraphicsMarkerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.log_dir = self.root / "data-root" / "logs"
        self.log_dir.mkdir(parents=True)
        self.log = self.log_dir / "nexium-guest.log"
        self.smoke = {
            "emulator_sha256": MACHO,
            "nro_sha256": NRO,
            "status": "exited_nonzero",
            "gameplay_verified": False,
            "window_capture": {
                "requested": True,
                "frames": 0,
                "unique_hashes": 0,
                "status": "no_window_frames_unverified",
            },
        }
        self.update(smoke=True, markers=(
            PROGRESS_MARKERS[0], FAILURE_MARKERS[0],
        ))

    def update(self, *, smoke=False, markers=None):
        if smoke:
            (self.root / "smoke_result.json").write_text(json.dumps(self.smoke))
        if markers is not None:
            self.log.write_text("".join(
                "[guest] " + MARKER_PREFIX + m + "\n" for m in markers
            ))

    def test_guest_start_and_window_failure_is_real_api_limit(self):
        result = source_graphics_audit(self.root, MACHO, NRO)
        self.assertTrue(result["original_libnx_graphics_guest_started"])
        self.assertEqual(result["original_guest_failure_marker"],
                         FAILURE_MARKERS[0])
        self.assertEqual(result["last_original_guest_marker"],
                         FAILURE_MARKERS[0])
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertFalse(result["guest_framebuffer_created_observed"])

    def test_guest_framebuffer_creation_failure_localized(self):
        self.update(markers=(
            PROGRESS_MARKERS[0], PROGRESS_MARKERS[1], FAILURE_MARKERS[1],
        ))
        report = source_graphics_audit(self.root, MACHO, NRO)
        self.assertEqual(report["original_guest_progress_markers"], 2)
        self.assertEqual(report["original_guest_failure_marker"], FAILURE_MARKERS[1])

    def test_linear_framebuffer_failure_is_not_presented(self):
        self.update(markers=(
            *PROGRESS_MARKERS[:3], FAILURE_MARKERS[2],
        ))
        report = source_graphics_audit(self.root, MACHO, NRO)
        self.assertTrue(report["guest_framebuffer_created_observed"])
        self.assertFalse(report["guest_framebuffer_end_call_returned_observed"])

    def test_first_frame_submitted_call_only_not_guest_gpu_verified(self):
        self.update(markers=(*PROGRESS_MARKERS[:6], FAILURE_MARKERS[4]))
        r = source_graphics_audit(self.root, MACHO, NRO)
        self.assertFalse(r["guest_framebuffer_end_call_returned_observed"])
        self.assertFalse(r["guest_gpu_frames_verified"])

    def test_four_guest_framebuffer_calls_do_not_prove_graphics(self):
        self.smoke["status"] = "exited_zero_unverified"
        self.update(smoke=True, markers=PROGRESS_MARKERS)
        report = source_graphics_audit(self.root, MACHO, NRO)
        self.assertTrue(report["guest_framebuffer_api_loop_complete_observed"])
        self.assertTrue(report["guest_framebuffer_end_call_returned_observed"])
        self.assertFalse(report["guest_gpu_frames_verified"])
        self.assertFalse(report["commercial_gameplay_verified"])

    def test_compiled_marker_bytes_without_original_log_do_not_pass(self):
        self.update(markers=())
        with self.assertRaisesRegex(ValueError, "start was not observed"):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_missing_original_first_marker_fails_closed(self):
        self.update(markers=(PROGRESS_MARKERS[1],))
        with self.assertRaisesRegex(ValueError, "start was not observed"):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_repeated_marker_is_rejected(self):
        self.update(markers=(
            PROGRESS_MARKERS[0], PROGRESS_MARKERS[0], FAILURE_MARKERS[0],
        ))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_out_of_order_markers_rejected(self):
        self.update(markers=(
            PROGRESS_MARKERS[0], PROGRESS_MARKERS[2],
        ))
        with self.assertRaises(ValueError):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_conflicting_failure_markers_rejected(self):
        self.update(markers=(PROGRESS_MARKERS[0], FAILURE_MARKERS[0],
                             FAILURE_MARKERS[1]))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_forged_native_binary_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            source_graphics_audit(self.root, "c"*64, NRO)

    def test_forged_guest_nro_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            source_graphics_audit(self.root, MACHO, "c"*64)

    def test_success_and_failure_markers_mutually_exclusive(self):
        self.smoke["status"] = "exited_zero_unverified"
        self.update(smoke=True, markers=(*PROGRESS_MARKERS, FAILURE_MARKERS[0]))
        with self.assertRaises(ValueError):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_nonzero_failed_graphics_guest_can_be_window_observed_only_when_opted_in(self):
        with self.assertRaisesRegex(ValueError, "not from valid"):
            inspect_gui_evidence(self.root, MACHO, NRO)
        report = inspect_gui_evidence(
            self.root, MACHO, NRO, allow_nonzero_guest=True,
        )
        self.assertEqual(report["observation"], "no_capture_report")
        self.assertFalse(report["guest_gpu_frames_verified"])

    def test_any_unexpected_guest_log_symlink_rejected(self):
        source = self.root / "other.log"
        source.write_text("sensitive fake logger contents")
        self.log.unlink()
        self.log.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            source_graphics_audit(self.root, MACHO, NRO)

    def test_refuse_multiple_guest_logger_files(self):
        (self.log_dir / "nexium-another.log").write_text("other process")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            source_graphics_audit(self.root, MACHO, NRO)


if __name__ == "__main__":
    unittest.main()
