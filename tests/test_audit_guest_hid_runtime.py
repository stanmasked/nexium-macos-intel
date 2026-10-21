import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_guest_hid_runtime.py"
SPEC = importlib.util.spec_from_file_location("guest_hid_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def fixture(root: Path, *, guest_up=True, mapping=True, include_trace=True, status="exited_zero_unverified"):
    report = {
        "status": status,
        "exit_code": 0 if status == "exited_zero_unverified" else 1 if status == "exited_nonzero" else None,
    }
    (root / "smoke_result.json").write_text(json.dumps(report), encoding="utf-8")
    mapping_lines = (
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
    ) if mapping else ""
    up = "OutputDebugString: STAGE40_GUEST_HID_B_UP\n" if guest_up else ""
    trace_lines = (
        "[hid-publish] npad=[0x2, 0x0]\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
    ) if include_trace else ""
    log = (
        mapping_lines
        + "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE\n"
        + "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE\n"
        + trace_lines
        + "OutputDebugString: STAGE40_GUEST_HID_PROBE_START\n"
        + "OutputDebugString: STAGE40_GUEST_HID_B_DOWN\n"
        + up
        + ("OutputDebugString: STAGE40_GUEST_HID_PRESS_RELEASE_PASS\n" if guest_up else "")
    )
    (root / "nexium-console.log").write_text(log, encoding="utf-8")


class GuestHidRuntimeAuditTests(unittest.TestCase):
    def test_reads_guest_svc_markers_from_isolated_file_logger(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            console_path = root / "nexium-console.log"
            lines = console_path.read_text(encoding="utf-8").splitlines()
            file_lines = [
                line for line in lines
                if (
                    "svcMapSharedMemory" in line
                    or "recognized as HID shared memory" in line
                    or "[hid-publish]" in line
                    or "OutputDebugString:" in line
                )
            ]
            host_lines = [line for line in lines if line not in file_lines]
            console_path.write_text("\n".join(host_lines) + "\n", encoding="utf-8")
            log_dir = root / "data-root" / "logs"
            log_dir.mkdir(parents=True)
            (log_dir / "nexium-test.log").write_text(
                "\n".join(file_lines) + "\n", encoding="utf-8"
            )

            report = AUDIT.audit(root)
            self.assertTrue(report["same_process_guest_input_roundtrip_passed"])
            self.assertEqual(report["file_logger_log_count"], 1)
            self.assertTrue(report["guest_libnx_b_down_observed"])
            self.assertTrue(report["guest_libnx_b_up_observed_after_down_marker"])

    def test_complete_guest_and_host_roundtrip_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            report = AUDIT.audit(root)
            self.assertTrue(report["same_process_guest_input_roundtrip_passed"])
            self.assertTrue(report["guest_hid_map_success_marker_observed"])
            self.assertTrue(report["serialized_npad_b_release_after_press_observed"])
            self.assertFalse(report["gameplay_verified"])
            self.assertFalse(report["real_switch_verified"])

    def test_guest_readback_passes_if_optional_host_trace_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, include_trace=False)
            report = AUDIT.audit(root)
            self.assertTrue(report["same_process_guest_input_roundtrip_passed"])
            self.assertFalse(report["serialized_npad_trace_roundtrip_observed"])

    def test_missing_guest_release_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, guest_up=False)
            report = AUDIT.audit(root)
            self.assertFalse(report["same_process_guest_input_roundtrip_passed"])

    def test_missing_hid_mapping_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, mapping=False)
            report = AUDIT.audit(root)
            self.assertFalse(report["same_process_guest_input_roundtrip_passed"])

    def test_nonzero_process_fails_even_if_markers_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, status="exited_nonzero")
            report = AUDIT.audit(root)
            self.assertFalse(report["same_process_guest_input_roundtrip_passed"])

    def test_timeout_without_guest_roundtrip_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, guest_up=False, status="timeout_alive_unverified")
            report = AUDIT.audit(root)
            self.assertFalse(report["same_process_guest_input_roundtrip_passed"])

    def test_timeout_after_complete_guest_roundtrip_is_acceptable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, status="timeout_alive_unverified")
            report = AUDIT.audit(root)
            self.assertTrue(report["same_process_guest_input_roundtrip_passed"])
            self.assertTrue(report["probe_process_outcome_acceptable"])

    def test_missing_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "missing NRO smoke receipt"):
                AUDIT.audit(Path(td))


if __name__ == "__main__":
    unittest.main()
