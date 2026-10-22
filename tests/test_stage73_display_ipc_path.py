"""Stage73 exact original guest display IPC stage and privacy gates."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from classify_guest_display_ipc_path import (
    inspect_guest_display_ipc_path, last_ipc_request_summary, MAX_LOG_BYTES,
)

MACHO, NRO = "a" * 64, "b" * 64


class Stage73GuestDisplayIpcPathTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.logdir = self.root / "data-root" / "logs"
        self.logdir.mkdir(parents=True)
        self.log = self.logdir / "nexium-stage73.log"
        self.receipt = {
            "emulator_sha256": MACHO, "nro_sha256": NRO,
            "status": "timeout_alive_unverified", "gameplay_verified": False,
        }
        (self.root / "smoke_result.json").write_text(json.dumps(self.receipt))
        self.data = ""

    def write_log(self):
        self.log.write_text(self.data)

    def inspect(self):
        self.write_log()
        return inspect_guest_display_ipc_path(self.root, MACHO, NRO)

    def set_through(self, stage):
        stages = [
            'IPC request service="sm:" cmd=1',
            "SM::GetServiceHandle 'vi:u' data_off=0x20",
            'IPC request service="vi:u" cmd=2 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x101",
            'IPC request service="IApplicationDisplayService" cmd=2020 in_data=8 is_domain=false',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2020 rc=0 response_len=64",
            "→ IHOSBinderDriver sub-session handle=0x102",
            'IPC request service="IHOSBinderDriver" cmd=0 in_data=8 is_domain=false',
            "IGBP::Connect binder=256 api=1 1280x720",
            "IGBP::RequestBuffer binder=256 slot=0",
            "IGBP::DequeueBuffer binder=256: request cannot be re-issued, polling in-SVC",
            "IGBP::QueueBuffer binder=256 swap_interval=1 (was None)",
        ]
        self.data = "\n".join(stages[:stage])

    def test_no_scoped_ipc_marker_is_insufficient_not_a_false_negative_claim(self):
        self.data = "Auto-loaded NRO:\nBooting NRO:\n"
        self.assertEqual(self.inspect()["observed_stage"], "ipc_request_markers_not_observed")

    def test_ipc_request_marker_without_vi_handle_request(self):
        self.data = 'IPC request service="sm:" cmd=1'
        self.assertEqual(self.inspect()["observed_stage"], "before_vi_u_service_handle_observed")

    def test_legacy_unmatched_vi_service_marker_does_not_count(self):
        self.data = ('IPC request service="sm:" cmd=1\n'
                     'sm:GetServiceHandle name=vi:u raw=0000000000000000')
        self.assertEqual(self.inspect()["observed_stage"], "before_vi_u_service_handle_observed")

    def test_vi_handle_without_vi_ipc_request(self):
        self.set_through(2)
        self.assertEqual(self.inspect()["observed_stage"], "vi_u_handle_created_ipc_request_not_observed")

    def test_vi_ipc_request_without_display_subsession(self):
        self.set_through(3)
        self.assertEqual(self.inspect()["observed_stage"], "vi_u_ipc_request_display_subsession_not_observed")

    def test_display_subsession_without_native_window_request(self):
        self.set_through(4)
        self.assertEqual(self.inspect()["observed_stage"], "display_subsession_created_native_window_request_not_observed")

    def test_native_window_request_without_response(self):
        self.set_through(5)
        self.assertEqual(self.inspect()["observed_stage"], "native_window_request_response_not_observed")

    def test_native_window_response_without_binder_subsession(self):
        self.set_through(6)
        self.assertEqual(self.inspect()["observed_stage"], "native_window_response_binder_subsession_not_observed")

    def test_binder_subsession_without_transact(self):
        self.set_through(7)
        self.assertEqual(self.inspect()["observed_stage"], "binder_subsession_transact_not_observed")

    def test_binder_transact_without_connect(self):
        self.set_through(8)
        self.assertEqual(self.inspect()["observed_stage"], "binder_transact_igbp_connect_not_observed")

    def test_connect_without_request_buffer(self):
        self.set_through(9)
        self.assertEqual(self.inspect()["observed_stage"], "igbp_connect_request_buffer_not_observed")

    def test_request_buffer_without_debug_visible_later_marker_is_unverified(self):
        self.set_through(10)
        self.assertEqual(
            self.inspect()["observed_stage"],
            "igbp_request_buffer_observed_later_buffer_operations_unverified_at_debug_level",
        )

    def test_dequeue_retry_marker_is_positive_diagnostic(self):
        self.set_through(11)
        self.assertEqual(self.inspect()["observed_stage"], "igbp_dequeue_retry_or_timeout_observed")

    def test_dequeue_timeout_marker_is_positive_diagnostic(self):
        self.set_through(10)
        self.data += "\nIGBP::DequeueBuffer timed out waiting for a released slot binder=256 (free=0 deq=0 queued=0)"
        self.assertEqual(self.inspect()["observed_stage"], "igbp_dequeue_retry_or_timeout_observed")

    def test_queue_is_not_guest_gpu_proof(self):
        self.set_through(12)
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "igbp_queue_observed_not_gpu_proof")
        self.assertFalse(result["guest_framebuffer_runtime_completed"])
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertFalse(result["commercial_gameplay_verified"])
        self.assertFalse(result["main_merge_approved"])
        self.assertFalse(result["raw_logs_uploaded"])

    def test_last_ipc_request_response_after_request_is_detected(self):
        data = ('IPC request service="IApplicationDisplayService" cmd=2020 in_data=8\n'
                'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
                'service=IApplicationDisplayService cmd=2020 rc=0')
        result = last_ipc_request_summary(data)
        self.assertEqual(result["last_ipc_request_stage"],
                         "native_window_layer_request_last_observed")
        self.assertTrue(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_same_response_seen_before"])
        self.assertNotIn("2020", json.dumps(result))

    def test_last_ipc_request_without_response_is_distinguished(self):
        data = ('IPC request service="vi:u" cmd=2\n'
                'IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=vi:u cmd=2\n'
                'IPC request service="IApplicationDisplayService" cmd=2020')
        result = last_ipc_request_summary(data)
        self.assertEqual(result["last_ipc_request_stage"],
                         "native_window_layer_request_last_observed")
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_same_response_seen_before"])

    def test_repeated_command_without_second_first_response_is_ambiguous(self):
        data = ('IPC request service="IApplicationDisplayService" cmd=2020\n'
                'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
                'service=IApplicationDisplayService cmd=2020\n'
                'IPC request service="IApplicationDisplayService" cmd=2020')
        result = last_ipc_request_summary(data)
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertTrue(result["last_ipc_request_same_response_seen_before"])

    def test_no_allowlisted_ipc_request_does_not_invent_a_stage(self):
        result = last_ipc_request_summary("unrelated debug text")
        self.assertEqual(result["last_ipc_request_stage"],
                         "no_allowlisted_ipc_request_observed")
        self.assertIsNone(result["last_ipc_request_response_after_request"])

    def test_wrong_native_binary_digest_rejected(self):
        self.write_log()
        with self.assertRaisesRegex(ValueError, "binary/NRO mismatch"):
            inspect_guest_display_ipc_path(self.root, "c" * 64, NRO)

    def test_wrong_nro_digest_rejected(self):
        self.write_log()
        with self.assertRaisesRegex(ValueError, "binary/NRO mismatch"):
            inspect_guest_display_ipc_path(self.root, MACHO, "c" * 64)

    def test_unknown_smoke_status_rejected(self):
        self.receipt["status"] = "success_verified"
        (self.root / "smoke_result.json").write_text(json.dumps(self.receipt))
        self.write_log()
        with self.assertRaisesRegex(ValueError, "status untrusted"):
            self.inspect()

    def test_missing_original_log_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            inspect_guest_display_ipc_path(self.root, MACHO, NRO)

    def test_duplicate_original_logs_rejected(self):
        self.write_log()
        (self.logdir / "nexium-second.log").write_text("second process")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.inspect()

    def test_symlinked_original_log_rejected(self):
        target = self.root / "outside.log"
        target.write_text("private trace")
        self.log.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "unsafe or oversized"):
            inspect_guest_display_ipc_path(self.root, MACHO, NRO)

    def test_oversized_trace_rejected(self):
        self.log.touch()
        with self.log.open("r+b") as f:
            f.truncate(MAX_LOG_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "unsafe or oversized"):
            inspect_guest_display_ipc_path(self.root, MACHO, NRO)


if __name__ == "__main__":
    unittest.main()
