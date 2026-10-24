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
from test_intel_integrated_tree import safe_unittest_failure_summary

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

    def set_through(self, stage, vi_service="vi:u"):
        stages = [
            'IPC request service="sm:" cmd=1',
            f"SM::GetServiceHandle '{vi_service}' data_off=0x20",
            f'IPC request service="{vi_service}" cmd=2 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x101",
            'IPC request service="IApplicationDisplayService" cmd=100 in_data=0 is_domain=false',
            "→ IHOSBinderDriver sub-session handle=0x102",
            'IPC request service="IApplicationDisplayService" cmd=2020 in_data=8 is_domain=false',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2020 rc=0x00000000 response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=00",
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

    def test_register_client_cmd_zero_does_not_anchor_vi_u_service_handle(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=0 in_data=0 is_domain=false',
            "SM::GetServiceHandle 'vi:u' data_off=0x20",
            'IPC request service="vi:u" cmd=2 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x101",
            'IPC request service="IApplicationDisplayService" cmd=100 in_data=0 is_domain=false',
        ))
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "ipc_sequence_inconsistent_or_cross_path")
        self.assertFalse(result["expected_vi_u_display_ancestry_observed"])
        self.assertTrue(result["downstream_ipc_without_expected_ancestry"])

    def test_cmd_ten_does_not_match_service_manager_get_handle_cmd_one(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=10 in_data=0 is_domain=false',
            "SM::GetServiceHandle 'vi:u' data_off=0x20",
            'IPC request service="vi:u" cmd=2 in_data=0 is_domain=false',
        ))
        self.assertEqual(
            self.inspect()["observed_stage"],
            "service_manager_get_service_handle_request_not_observed",
        )
        self.assertFalse(self.inspect()["expected_vi_u_display_ancestry_observed"])

    def test_unrelated_cmd_one_cannot_be_reused_for_unpaired_vi_u_handler(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1 in_data=8 is_domain=false',
            "SM::GetServiceHandle 'appletOE' data_off=0x20",
            "SM::GetServiceHandle 'vi:u' data_off=0x20",
            'IPC request service="vi:u" cmd=2 in_data=0 is_domain=false',
        ))
        result = self.inspect()
        self.assertEqual(
            result["observed_stage"],
            "vi_u_service_handle_marker_without_correlated_cmd1",
        )
        self.assertFalse(result["expected_vi_u_display_ancestry_observed"])

    def test_legacy_unmatched_vi_service_marker_does_not_count(self):
        self.data = ('IPC request service="sm:" cmd=1\n'
                     'sm:GetServiceHandle name=vi:u raw=0000000000000000')
        self.assertEqual(self.inspect()["observed_stage"], "before_vi_u_service_handle_observed")
        self.assertFalse(self.inspect()["downstream_ipc_without_expected_ancestry"])

    def test_downstream_ipc_without_ordered_vi_u_ancestry_is_not_misclassified_as_early_stop(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1',
            "IApplicationDisplayService sub-session handle=0x101",
            'IPC request service="IApplicationDisplayService" cmd=100 in_data=0 is_domain=false',
            'IPC request service="IApplicationDisplayService" cmd=2020 in_data=8 is_domain=false',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2020 rc=0x00000000 response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=00",
            "IHOSBinderDriver sub-session handle=0x102",
            'IPC request service="IHOSBinderDriver" cmd=3 in_data=8 is_domain=false',
            "IGBP::Connect binder=256 api=1 1280x720",
            "IGBP::RequestBuffer binder=256 slot=0",
            "IGBP::QueueBuffer binder=256 swap_interval=1 (was None)",
        ))
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "ipc_sequence_inconsistent_or_cross_path")
        self.assertTrue(result["downstream_ipc_without_expected_ancestry"])
        self.assertFalse(result["expected_vi_u_display_ancestry_observed"])
        self.assertEqual(result["native_window_response_status"], "observed_but_unattributed")
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertNotIn("256", json.dumps(result))

    def test_vi_handle_without_vi_ipc_request(self):
        self.set_through(2)
        self.assertEqual(self.inspect()["observed_stage"], "vi_u_handle_created_ipc_request_not_observed")

    def test_vi_ipc_request_without_display_subsession(self):
        self.set_through(3)
        self.assertEqual(self.inspect()["observed_stage"], "vi_u_ipc_request_display_subsession_not_observed")

    def test_vi_m_service_path_is_not_misclassified_as_cross_path(self):
        self.set_through(13, "vi:m")
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "igbp_queue_observed_not_gpu_proof")
        self.assertEqual(result["observed_vi_service_variant"], "vi_m")
        self.assertTrue(result["expected_vi_display_ancestry_observed"])
        self.assertFalse(result["expected_vi_u_display_ancestry_observed"])
        self.assertFalse(result["downstream_ipc_without_expected_ancestry"])
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_vi_s_service_path_is_not_misclassified_as_cross_path(self):
        self.set_through(13, "vi:s")
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "igbp_queue_observed_not_gpu_proof")
        self.assertEqual(result["observed_vi_service_variant"], "vi_s")
        self.assertTrue(result["expected_vi_display_ancestry_observed"])
        self.assertFalse(result["expected_vi_u_display_ancestry_observed"])
        self.assertFalse(result["downstream_ipc_without_expected_ancestry"])
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_unmapped_vi_command_does_not_anchor_display_ancestry(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1 in_data=0 is_domain=false',
            "SM::GetServiceHandle 'vi:m' data_off=0x20",
            'IPC request service="vi:m" cmd=10 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x101",
            'IPC request service="IApplicationDisplayService" cmd=100 in_data=0 is_domain=false',
        ))
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "ipc_sequence_inconsistent_or_cross_path")
        self.assertFalse(result["expected_vi_display_ancestry_observed"])
        self.assertTrue(result["downstream_ipc_without_expected_ancestry"])

    def test_session_handles_correlate_vi_request_to_display_subsession(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1 in_data=0 is_domain=false',
            "SM::GetServiceHandle 'vi:m' data_off=0x20",
            "SM: returning handle 0x10 for service 'vi:m'",
            'IPC request service="vi:m" cmd=0 session=0x10 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x20 parent_session=0x10",
            'IPC request service="IApplicationDisplayService" cmd=100 session=0x20 in_data=0 is_domain=false',
            'IPC request service="IApplicationDisplayService" cmd=2020 session=0x20 in_data=0 is_domain=false',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=IApplicationDisplayService cmd=2020 session=0x20 rc=0x00000000 response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=",
        ))
        result = self.inspect()
        self.assertTrue(result["session_correlation_fields_observed"])
        self.assertTrue(result["vi_service_handle_return_correlated"])
        self.assertTrue(result["vi_request_session_correlated"])
        self.assertTrue(result["display_subsession_parent_correlated"])
        self.assertTrue(result["expected_vi_display_ancestry_observed"])
        self.assertEqual(result["observed_vi_service_variant"], "vi_m")
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertNotIn("0x10", json.dumps(result))
        self.assertNotIn("0x20", json.dumps(result))

    def test_mismatched_vi_session_handle_does_not_anchor_display_ancestry(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1 in_data=0 is_domain=false',
            "SM::GetServiceHandle 'vi:m' data_off=0x20",
            "SM: returning handle 0x10 for service 'vi:m'",
            'IPC request service="vi:m" cmd=0 session=0x11 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x20 parent_session=0x11",
            'IPC request service="IApplicationDisplayService" cmd=100 session=0x20 in_data=0 is_domain=false',
            'IGBP::RequestBuffer binder=7 slot=0',
        ))
        result = self.inspect()
        self.assertTrue(result["session_correlation_fields_observed"])
        self.assertTrue(result["vi_service_handle_return_correlated"])
        self.assertFalse(result["vi_request_session_correlated"])
        self.assertFalse(result["display_subsession_parent_correlated"])
        self.assertFalse(result["expected_vi_display_ancestry_observed"])
        self.assertTrue(result["downstream_ipc_without_expected_ancestry"])
        self.assertEqual(result["observed_stage"], "ipc_sequence_inconsistent_or_cross_path")

    def test_subsession_parent_mismatch_is_not_accepted_as_vi_ancestry(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1 in_data=0 is_domain=false',
            "SM::GetServiceHandle 'vi:s' data_off=0x20",
            "SM: returning handle 0x30 for service 'vi:s'",
            'IPC request service="vi:s" cmd=2 session=0x30 in_data=0 is_domain=false',
            "→ IApplicationDisplayService sub-session handle=0x40 parent_session=0x99",
            'IPC request service="IApplicationDisplayService" cmd=100 session=0x40 in_data=0 is_domain=false',
        ))
        result = self.inspect()
        self.assertTrue(result["vi_request_session_correlated"])
        self.assertFalse(result["display_subsession_parent_correlated"])
        self.assertFalse(result["expected_vi_display_ancestry_observed"])
        self.assertTrue(result["downstream_ipc_without_expected_ancestry"])


    def set_scoped_window_path(self):
        self.data = "\n".join((
            'IPC request service="sm:" cmd=1',
            "SM::GetServiceHandle 'vi:m' data_off=0x20",
            "SM: returning handle 0x10 for service 'vi:m'",
            'IPC request service="vi:m" cmd=0 session=0x10 in_data=0',
            "→ IApplicationDisplayService sub-session handle=0x20 parent_session=0x10",
            'IPC request service="IApplicationDisplayService" cmd=100 session=0x20 in_data=0',
            "→ IHOSBinderDriver sub-session handle=0x30 parent_session=0x20",
            'IPC request service="IApplicationDisplayService" cmd=2020 session=0x20 in_data=0',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 session=0x20 rc=0x00000000 "
            "response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=",
            'IPC request service="IHOSBinderDriver" cmd=0 session=0x30 in_data=0',
            "IGBP::Connect binder=256 api=1 1280x720",
            "IGBP::RequestBuffer binder=256 slot=0",
            "IGBP::QueueBuffer binder=256 swap_interval=1 (was None)",
        ))

    def test_scoped_display_and_binder_session_chain_succeeds_without_gpu_claim(self):
        self.set_scoped_window_path()
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "igbp_queue_observed_not_gpu_proof")
        for field in ("display_binder_request_session_correlated",
                      "binder_subsession_parent_correlated",
                      "native_window_request_session_correlated",
                      "native_window_response_session_correlated",
                      "binder_transaction_session_correlated"):
            self.assertTrue(result[field], field)
        self.assertFalse(result["guest_gpu_frames_verified"])
        for handle in ("0x10", "0x20", "0x30"):
            self.assertNotIn(handle, json.dumps(result))

    def test_scoped_other_display_session_binder_request_not_attributed(self):
        self.set_scoped_window_path()
        self.data = self.data.replace(
            'cmd=100 session=0x20', 'cmd=100 session=0x21')
        result = self.inspect()
        self.assertEqual(result["observed_stage"],
                         "display_subsession_binder_session_request_not_observed")
        self.assertFalse(result["display_binder_request_session_correlated"])

    def test_scoped_binder_subsession_wrong_parent_not_attributed(self):
        self.set_scoped_window_path()
        self.data = self.data.replace(
            "handle=0x30 parent_session=0x20",
            "handle=0x30 parent_session=0x21")
        result = self.inspect()
        self.assertEqual(result["observed_stage"],
                         "display_service_binder_subsession_not_observed")
        self.assertFalse(result["binder_subsession_parent_correlated"])

    def test_scoped_native_window_request_other_display_session_not_attributed(self):
        self.set_scoped_window_path()
        self.data = self.data.replace(
            'cmd=2020 session=0x20 in_data=0',
            'cmd=2020 session=0x21 in_data=0')
        result = self.inspect()
        self.assertEqual(result["observed_stage"],
                         "binder_subsession_created_native_window_request_not_observed")
        self.assertFalse(result["native_window_request_session_correlated"])

    def test_scoped_native_window_response_other_session_not_success(self):
        self.set_scoped_window_path()
        self.data = self.data.replace(
            "cmd=2020 session=0x20 rc=0x00000000",
            "cmd=2020 session=0x21 rc=0x00000000")
        result = self.inspect()
        self.assertEqual(result["observed_stage"],
                         "native_window_response_other_session_unverified")
        self.assertEqual(result["native_window_response_status"], "other_session")
        self.assertFalse(result["native_window_response_session_correlated"])
        self.assertNotIn("0x21", json.dumps(result))

    def test_scoped_binder_transaction_other_session_does_not_advance(self):
        self.set_scoped_window_path()
        self.data = self.data.replace(
            'cmd=0 session=0x30 in_data=0', 'cmd=0 session=0x31 in_data=0')
        result = self.inspect()
        self.assertEqual(result["observed_stage"],
                         "display_and_native_window_ready_binder_transact_not_observed")
        self.assertFalse(result["binder_transaction_session_correlated"])

    def test_scoped_interleaved_other_session_window_request_not_ambiguous(self):
        self.set_scoped_window_path()
        foreign = 'IPC request service="IApplicationDisplayService" cmd=2020 session=0x21 in_data=0'
        needle = "IPC FIRST-OCCURRENCE response (compare with RustSwitch)"
        self.data = self.data.replace(needle, foreign + "\n" + needle, 1)
        result = self.inspect()
        self.assertEqual(result["native_window_response_status"], "success")
        self.assertEqual(result["observed_stage"], "igbp_queue_observed_not_gpu_proof")

    def test_scoped_repeated_same_session_window_request_is_ambiguous(self):
        self.set_scoped_window_path()
        duplicate = 'IPC request service="IApplicationDisplayService" cmd=2020 session=0x20 in_data=0'
        needle = "IPC FIRST-OCCURRENCE response (compare with RustSwitch)"
        self.data = self.data.replace(needle, duplicate + "\n" + needle, 1)
        result = self.inspect()
        self.assertEqual(result["observed_stage"],
                         "native_window_request_response_correlation_ambiguous")
        self.assertEqual(result["native_window_response_status"], "ambiguous")

    def test_last_ipc_request_summary_recognizes_vi_m(self):
        result = last_ipc_request_summary("\n".join((
            'IPC request service="vi:m" cmd=2 in_data=0 is_domain=false',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=vi:m cmd=2 rc=0x00000000 response_len=0 response_first64= in_data_first32=",
        )))
        self.assertEqual(result["last_ipc_request_stage"], "vi_m_request_last_observed")
        self.assertTrue(result["last_ipc_request_response_after_request"])

    def test_last_ipc_request_summary_recognizes_vi_s(self):
        result = last_ipc_request_summary("\n".join((
            'IPC request service="vi:s" cmd=2 in_data=0 is_domain=false',
            "IPC FIRST-OCCURRENCE response (compare with RustSwitch) service=vi:s cmd=2 rc=0x00000000 response_len=0 response_first64= in_data_first32=",
        )))
        self.assertEqual(result["last_ipc_request_stage"], "vi_s_request_last_observed")
        self.assertTrue(result["last_ipc_request_response_after_request"])

    def test_display_subsession_without_either_followup_branch(self):
        self.set_through(4)
        self.assertEqual(self.inspect()["observed_stage"], "display_subsession_binder_or_native_window_request_not_observed")

    def test_native_window_branch_without_binder_session_request(self):
        self.set_through(4)
        self.data += (
            "\nIPC request service=\"IApplicationDisplayService\" "
            "cmd=2020 in_data=8 is_domain=false"
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=00"
        )
        self.assertEqual(
            self.inspect()["observed_stage"],
            "display_subsession_binder_session_request_not_observed",
        )
    def test_binder_session_request_without_subsession(self):
        self.set_through(5)
        self.assertEqual(self.inspect()["observed_stage"], "display_service_binder_subsession_not_observed")

    def test_binder_subsession_without_native_window_request(self):
        self.set_through(6)
        self.assertEqual(self.inspect()["observed_stage"], "binder_subsession_created_native_window_request_not_observed")

    def test_native_window_request_without_response(self):
        self.set_through(7)
        self.assertEqual(self.inspect()["observed_stage"], "native_window_request_response_not_observed")

    def test_native_window_response_without_binder_transact(self):
        self.set_through(8)
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "display_and_native_window_ready_binder_transact_not_observed")
        self.assertEqual(result["native_window_response_status"], "success")

    def test_native_window_error_response_does_not_advance_to_binder_path(self):
        self.set_through(7)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000001 response_len=12 response_first64=53,46,43,4f,00,00,00,00,01,00,00,00 in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_failed_response_observed")
        self.assertEqual(result["native_window_response_status"], "failure")
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertNotIn("0x00000001", json.dumps(result))

    def test_native_window_response_without_rc_is_unverified(self):
        self.set_through(7)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_response_status_unverified")
        self.assertEqual(result["native_window_response_status"], "unverified")


    def test_zero_rc_without_sfco_header_is_not_success(self):
        self.set_through(7)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 "
            "response_len=12 response_first64=00,00,00,00,00,00,00,00,00,00,00,00 "
            "in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_response_status_unverified")
        self.assertEqual(result["native_window_response_status"], "unverified")
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_repeated_native_window_request_makes_response_correlation_ambiguous(self):
        self.set_through(7)
        self.data += (
            '\nIPC request service="IApplicationDisplayService" cmd=2020 in_data=8 is_domain=false'
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 "
            "response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 "
            "in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_response_correlation_ambiguous")
        self.assertEqual(result["native_window_response_status"], "ambiguous")
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_overlong_response_length_is_unverified(self):
        self.set_through(7)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 "
            "response_len=999999999999999999999 response_first64="
            "53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_response_status_unverified")
        self.assertEqual(result["native_window_response_status"], "unverified")

    def test_implausibly_large_response_length_with_valid_sfco_is_unverified(self):
        self.set_through(7)
        preview = ",".join(["53", "46", "43", "4f", "00", "00", "00", "00", "00", "00", "00", "00"] + ["00"] * 52)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 "
            "response_len=99999999999999999999 response_first64="
            + preview + " in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_response_status_unverified")
        self.assertEqual(result["native_window_response_status"], "unverified")
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_overlong_response_preview_is_unverified_without_expanding_tokens(self):
        self.set_through(7)
        preview = ",".join(["00"] * 65)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 "
            "response_len=64 response_first64=" + preview + " in_data_first32=00"
        )
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "native_window_request_response_status_unverified")
        self.assertEqual(result["native_window_response_status"], "unverified")

    def test_binder_transact_without_connect(self):
        self.set_through(9)
        self.assertEqual(self.inspect()["observed_stage"], "binder_transact_igbp_connect_not_observed")

    def test_connect_without_request_buffer(self):
        self.set_through(10)
        self.assertEqual(self.inspect()["observed_stage"], "igbp_connect_request_buffer_not_observed")

    def test_request_buffer_without_debug_visible_later_marker_is_unverified(self):
        self.set_through(11)
        self.assertEqual(
            self.inspect()["observed_stage"],
            "igbp_request_buffer_observed_later_buffer_operations_unverified_at_debug_level",
        )

    def test_request_buffer_for_different_binder_does_not_advance_path(self):
        self.set_through(10)
        self.data += (
            "\nIGBP::RequestBuffer binder=512 slot=0"
            "\nIGBP::QueueBuffer binder=512 swap_interval=1 (was None)"
        )
        result = self.inspect()
        self.assertEqual(
            result["observed_stage"],
            "igbp_connect_request_buffer_binder_mismatch",
        )
        self.assertNotIn("512", json.dumps(result))

    def test_interleaved_request_buffer_selects_matching_binder(self):
        self.set_through(10)
        self.data += (
            "\nIGBP::RequestBuffer binder=512 slot=0"
            "\nIGBP::RequestBuffer binder=256 slot=1"
            "\\nIGBP::QueueBuffer binder=256 swap_interval=1 (was None)"
        )
        self.assertEqual(
            self.inspect()["observed_stage"],
            "igbp_queue_observed_not_gpu_proof",
        )

    def test_queue_for_different_binder_is_not_attributed(self):
        self.set_through(11)
        self.data += "\nIGBP::QueueBuffer binder=512 swap_interval=1 (was None)"
        self.assertEqual(
            self.inspect()["observed_stage"],
            "igbp_request_buffer_other_binder_activity_unverified",
        )

    def test_dequeue_retry_marker_is_positive_diagnostic(self):
        self.set_through(12)
        self.assertEqual(self.inspect()["observed_stage"], "igbp_dequeue_retry_or_timeout_observed")

    def test_dequeue_timeout_marker_is_positive_diagnostic(self):
        self.set_through(11)
        self.data += "\nIGBP::DequeueBuffer timed out waiting for a released slot binder=256 (free=0 deq=0 queued=0)"
        self.assertEqual(self.inspect()["observed_stage"], "igbp_dequeue_retry_or_timeout_observed")

    def test_out_of_order_queue_marker_does_not_advance_past_connect(self):
        self.set_through(10)
        self.data += "\nIGBP::QueueBuffer binder=256 swap_interval=1 (was None)"
        self.assertEqual(
            self.inspect()["observed_stage"],
            "igbp_connect_request_buffer_not_observed",
        )

    def test_response_before_native_window_request_does_not_count(self):
        self.set_through(6)
        self.data += (
            "\nIPC FIRST-OCCURRENCE response (compare with RustSwitch) "
            "service=IApplicationDisplayService cmd=2020 rc=0x00000000 response_len=12 response_first64=53,46,43,4f,00,00,00,00,00,00,00,00 in_data_first32=00"
            "\nIPC request service=\"IApplicationDisplayService\" "
            "cmd=2020 in_data=8 is_domain=false"
        )
        self.assertEqual(
            self.inspect()["observed_stage"],
            "native_window_request_response_not_observed",
        )

    def test_native_window_branch_can_precede_binder_session_branch(self):
        self.set_through(13)
        lines = self.data.splitlines()
        # Move native-window request/response ahead of cmd 100 and its session handle.
        self.data = "\n".join(lines[:4] + lines[6:8] + lines[4:6] + lines[8:])
        result = self.inspect()
        self.assertEqual(result["observed_stage"], "igbp_queue_observed_not_gpu_proof")
        self.assertFalse(result["guest_gpu_frames_verified"])
    def test_queue_is_not_guest_gpu_proof(self):
        self.set_through(13)
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
                'service=IApplicationDisplayService cmd=2020 rc=0x00000000')
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


    def test_scoped_last_request_rejects_another_sessions_response(self):
        result = last_ipc_request_summary("\n".join((
            'IPC request service="IApplicationDisplayService" cmd=2020 session=0x20',
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=IApplicationDisplayService cmd=2020 session=0x21 rc=0x00000000',
        )))
        self.assertEqual(result["last_ipc_request_stage"],
                         "native_window_layer_request_last_observed")
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertTrue(result["last_ipc_request_other_session_response_after_request"])
        self.assertTrue(result["last_ipc_request_session_scoped"])
        self.assertNotIn("0x20", json.dumps(result))
        self.assertNotIn("0x21", json.dumps(result))

    def test_scoped_last_request_accepts_same_session_response(self):
        result = last_ipc_request_summary("\n".join((
            'IPC request service="IApplicationDisplayService" cmd=2030 session=0x0020',
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=IApplicationDisplayService cmd=2030 session=0x20 rc=0x00000000',
        )))
        self.assertTrue(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_other_session_response_after_request"])

    def test_scoped_last_request_rejects_legacy_unscoped_response(self):
        result = last_ipc_request_summary("\n".join((
            'IPC request service="vi:m" cmd=2 session=0x30',
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=vi:m cmd=2 rc=0x00000000',
        )))
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertTrue(result["last_ipc_request_other_session_response_after_request"])

    def test_legacy_last_request_does_not_consume_scoped_response(self):
        result = last_ipc_request_summary("\n".join((
            'IPC request service="vi:m" cmd=2',
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=vi:m cmd=2 session=0x30 rc=0x00000000',
        )))
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_session_scoped"])

    def test_repeated_scoped_command_in_other_session_not_same_response(self):
        result = last_ipc_request_summary("\n".join((
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=vi:u cmd=1 session=0x10 rc=0x00000000',
            'IPC request service="vi:u" cmd=1 session=0x11',
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=vi:u cmd=1 session=0x10 rc=0x00000000',
        )))
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_same_response_seen_before"])
        self.assertTrue(result["last_ipc_request_other_session_response_after_request"])

    def test_scoped_response_before_latest_request_is_not_success(self):
        result = last_ipc_request_summary("\n".join((
            'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
            'service=vi:s cmd=1 session=0x10 rc=0x00000000',
            'IPC request service="vi:s" cmd=1 session=0x10',
        )))
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertTrue(result["last_ipc_request_same_response_seen_before"])
        self.assertFalse(result["last_ipc_request_other_session_response_after_request"])

    def test_nvdrv_response_from_different_service_alias_does_not_count(self):
        data = ('IPC request service="nvdrv:a" cmd=7\n'
                'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
                'service=nvdrv:s cmd=7')
        result = last_ipc_request_summary(data)
        self.assertEqual(result["last_ipc_request_stage"], "nvdrv_request_last_observed")
        self.assertFalse(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_same_response_seen_before"])

    def test_nvdrv_response_from_exact_service_alias_counts(self):
        data = ('IPC request service="nvdrv:a" cmd=7\n'
                'IPC FIRST-OCCURRENCE response (compare with RustSwitch) '
                'service=nvdrv:a cmd=7')
        result = last_ipc_request_summary(data)
        self.assertTrue(result["last_ipc_request_response_after_request"])
        self.assertFalse(result["last_ipc_request_same_response_seen_before"])

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

    def test_symlinked_report_directory_rejected(self):
        alias = self.root.with_name(self.root.name + "-alias")
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink)
        with self.assertRaisesRegex(ValueError, "report directory unsafe"):
            inspect_guest_display_ipc_path(alias, MACHO, NRO)

    def test_symlinked_data_root_rejected(self):
        real_root = self.root / "outside-data-root"
        (self.root / "data-root").rename(real_root)
        (self.root / "data-root").symlink_to(real_root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "log directory unsafe"):
            self.inspect()
    def test_symlinked_log_directory_rejected(self):
        real_dir = self.root / "outside-logs"
        self.logdir.rename(real_dir)
        self.logdir.symlink_to(real_dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "log directory unsafe"):
            self.inspect()
    def test_oversized_trace_rejected(self):
        self.log.touch()
        with self.log.open("r+b") as f:
            f.truncate(MAX_LOG_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "unsafe or oversized"):
            inspect_guest_display_ipc_path(self.root, MACHO, NRO)


class Stage73WorkflowTriggerTests(unittest.TestCase):
    def test_classifier_runs_on_draft_prs_and_gates_superseded_heads(self):
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows"
            / "nexium-intel-display-ipc-path-diagnostics.yml"
        )
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertRegex(
            workflow,
            r"(?m)^    types: \[opened, synchronize, reopened, ready_for_review\]$",
        )
        self.assertNotIn("github.event.pull_request.draft == false", workflow)
        self.assertIn(
            "github.head_ref == 'work/intel-stage73-display-ipc-path-final'",
            workflow,
        )
        self.assertIn("needs.current-head.outputs.is_current == 'true'", workflow)

    def test_native_trace_cache_requires_successful_executed_intel_job(self):
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows"
            / "nexium-intel-display-ipc-path-native.yml"
        )
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("last_successful_run_id", workflow)
        self.assertIn(
            "/actions/runs/$last_successful_run_id/jobs", workflow
        )
        self.assertIn(
            '.name == "integrated-intel-guest-graphics"', workflow
        )
        self.assertIn(
            '.status == "completed" and .conclusion == "success"', workflow
        )
        # Never substitute a workflow-level Success for guest-run proof.
        self.assertIn(
            'needs.private-archive-readiness.outputs.archive_ready == \'true\'',
            workflow,
        )
        self.assertIn('echo "archive_ready=false"', workflow)


class Stage73IntegratedPythonFailureSummaryTests(unittest.TestCase):
    def test_failure_summary_keeps_counts_and_safe_case_ids_only(self):
        combined = (
            "Traceback (most recent call last):\n"
            '  File "/private/runner/path.py", line 12, in test_case\n'
            "FAIL: test_bad (module.SecretTest)\n"
            "AssertionError: private fixture payload\n"
            "Ran 492 tests in 0.12s\n"
            "FAILED (failures=1)\n"
        )
        summary = safe_unittest_failure_summary(
            combined, returncode=1, min_tests=497, reason="unittest_failure"
        )
        self.assertIn("reported_tests=492", summary)
        self.assertIn("min_tests=497", summary)
        self.assertIn("failures=1 errors=0", summary)
        self.assertIn("cases=module.SecretTest.test_bad", summary)
        self.assertNotIn("Traceback", summary)
        self.assertNotIn("/private/", summary)
        self.assertNotIn("private fixture payload", summary)

    def test_timeout_summary_does_not_require_or_emit_test_output(self):
        summary = safe_unittest_failure_summary(
            "", returncode=-1, min_tests=497, reason="timeout"
        )
        self.assertIn("reason=timeout", summary)
        self.assertIn("reported_tests=-1", summary)
        self.assertIn("min_tests=497", summary)
        self.assertNotIn("Traceback", summary)


if __name__ == "__main__":
    unittest.main()
