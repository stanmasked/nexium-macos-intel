import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_guest_hid_runtime.py"
SPEC = importlib.util.spec_from_file_location("guest_hid_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def fixture(root: Path, *, guest_up=True, mapping=True, exit_zero=True):
    report = {
        "status": "exited_zero_unverified" if exit_zero else "timeout_alive_unverified",
        "exit_code": 0 if exit_zero else None,
    }
    (root / "smoke_result.json").write_text(json.dumps(report), encoding="utf-8")
    mapping_lines = (
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\\n"
        "recognized as HID shared memory\\n"
    ) if mapping else ""
    up = "OutputDebugString: STAGE40_GUEST_HID_B_UP\\n" if guest_up else ""
    log = (
        mapping_lines
        + "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE\\n"
        + "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE\\n"
        + "[hid-publish] npad=[0x2, 0x0]\\n"
        + "[hid-publish] npad=[0x0, 0x0]\\n"
        + "OutputDebugString: STAGE40_GUEST_HID_PROBE_START\\n"
        + "OutputDebugString: STAGE40_GUEST_HID_B_DOWN\\n"
        + up
        + ("OutputDebugString: STAGE40_GUEST_HID_PRESS_RELEASE_PASS\\n" if guest_up else "")
    )
    (root / "nexium-console.log").write_text(log, encoding="utf-8")


class GuestHidRuntimeAuditTests(unittest.TestCase):
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

    def test_nonzero_or_timeout_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root, exit_zero=False)
            report = AUDIT.audit(root)
            self.assertFalse(report["same_process_guest_input_roundtrip_passed"])

    def test_missing_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "missing NRO smoke receipt"):
                AUDIT.audit(Path(td))


if __name__ == "__main__":
    unittest.main()
