"""Stage70: exact guest framebuffer state machine, nonzero exits and timeouts."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from probe_intel_graphics_runtime import (
    PROGRESS_MARKERS, FAILURE_MARKERS, FAILURE_PREFIX_LENGTHS,
    MARKER_PREFIX, source_graphics_audit,
)
MACHO, NRO = "a" * 64, "b" * 64


class Stage70GuestFramebufferStates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.logs = self.root / "data-root" / "logs"
        self.logs.mkdir(parents=True)
        self.log = self.logs / "nexium-graphics.log"

    def run_guest(self, marker_names, status):
        (self.root / "smoke_result.json").write_text(json.dumps({
            "emulator_sha256": MACHO, "nro_sha256": NRO,
            "status": status, "gameplay_verified": False
        }))
        self.log.write_text("".join(
            "[original guest] " + MARKER_PREFIX + marker + "\n"
            for marker in marker_names
        ))
        return source_graphics_audit(self.root, MACHO, NRO)

    def test_first_window_error_is_explicit_failure_not_rendered(self):
        r = self.run_guest((PROGRESS_MARKERS[0], FAILURE_MARKERS[0]),
                           "exited_nonzero")
        self.assertEqual(r["graphics_guest_runtime_classification"],
                         "explicit_guest_framebuffer_failure")
        self.assertFalse(r["guest_framebuffer_runtime_completed"])

    def test_create_error_requires_correct_two_event_prefix(self):
        r = self.run_guest((*PROGRESS_MARKERS[:2], FAILURE_MARKERS[1]),
                           "exited_nonzero")
        self.assertEqual(r["original_guest_progress_markers"], 2)

    def test_linear_error_requires_correct_three_event_prefix(self):
        r = self.run_guest((*PROGRESS_MARKERS[:3], FAILURE_MARKERS[2]),
                           "exited_nonzero")
        self.assertTrue(r["guest_framebuffer_created_observed"])

    def test_buffer_error_allowed_at_first_frame(self):
        r = self.run_guest((*PROGRESS_MARKERS[:4], FAILURE_MARKERS[4]),
                           "exited_nonzero")
        self.assertEqual(r["original_guest_failure_marker"], FAILURE_MARKERS[4])

    def test_buffer_error_allowed_after_first_frame(self):
        r = self.run_guest((*PROGRESS_MARKERS[:6], FAILURE_MARKERS[4]),
                           "exited_nonzero")
        self.assertFalse(r["guest_framebuffer_runtime_completed"])

    def test_early_begin_error_after_only_guest_start_is_impossible(self):
        with self.assertRaisesRegex(ValueError, "impossible"):
            self.run_guest((PROGRESS_MARKERS[0], FAILURE_MARKERS[4]),
                           "exited_nonzero")

    def test_window_unavailable_after_successful_window_is_impossible(self):
        with self.assertRaisesRegex(ValueError, "impossible"):
            self.run_guest((*PROGRESS_MARKERS[:2], FAILURE_MARKERS[0]),
                           "exited_nonzero")

    def test_guest_nonzero_without_explicit_failure_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "without an explicit"):
            self.run_guest(PROGRESS_MARKERS[:3], "exited_nonzero")

    def test_guest_zero_without_complete_api_calls_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "without an explicit"):
            self.run_guest(PROGRESS_MARKERS[:6], "exited_zero_unverified")

    def test_guest_failure_and_process_timeout_rejected(self):
        with self.assertRaisesRegex(ValueError, "without nonzero"):
            self.run_guest((PROGRESS_MARKERS[0], FAILURE_MARKERS[0]),
                           "timeout_alive_unverified")

    def test_partial_progress_timeout_is_unverified_not_completion(self):
        r = self.run_guest(PROGRESS_MARKERS[:2], "timeout_alive_unverified")
        self.assertEqual(r["graphics_guest_runtime_classification"],
                         "partial_guest_progress_timeout_unverified")
        self.assertTrue(r["guest_runtime_timeout_unverified"])
        self.assertFalse(r["guest_framebuffer_runtime_completed"])
        self.assertFalse(r["guest_gpu_frames_verified"])

    def test_full_guest_completion_requires_zero_exit(self):
        r = self.run_guest(PROGRESS_MARKERS, "exited_zero_unverified")
        self.assertEqual(r["graphics_guest_runtime_classification"],
                         "all_guest_framebuffer_api_calls_returned")
        self.assertTrue(r["guest_framebuffer_runtime_completed"])
        self.assertFalse(r["guest_gpu_frames_verified"])

    def test_full_progress_followed_by_nonzero_exit_rejected(self):
        with self.assertRaisesRegex(ValueError, "without successful"):
            self.run_guest(PROGRESS_MARKERS, "exited_nonzero")

    def test_all_failure_states_have_reviewed_valid_prefix(self):
        self.assertEqual(set(FAILURE_PREFIX_LENGTHS), set(FAILURE_MARKERS))
        self.assertEqual(FAILURE_PREFIX_LENGTHS[FAILURE_MARKERS[0]], {1})
        self.assertEqual(FAILURE_PREFIX_LENGTHS[FAILURE_MARKERS[1]], {2})
        self.assertEqual(FAILURE_PREFIX_LENGTHS[FAILURE_MARKERS[2]], {3})

    def test_no_actual_guest_start_marker_is_never_pass(self):
        with self.assertRaisesRegex(ValueError, "start was not observed"):
            self.run_guest((), "timeout_alive_unverified")


if __name__ == "__main__":
    unittest.main()
