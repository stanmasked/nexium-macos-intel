import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_guest_hid_no_virtual import audit_no_virtual


def fixture(root: Path):
    report_dir = root / "no-virtual"
    positive = root / "stage40-guest-hid-runtime.json"
    report_dir.mkdir()
    positive.write_text(json.dumps({
        "schema": "nexium-stage40-guest-npad-readback/v1",
        "same_process_guest_input_roundtrip_passed": True,
    }), encoding="utf-8")
    (report_dir / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    (report_dir / "nexium-console.log").write_text("", encoding="utf-8")
    log_dir = report_dir / "data-root" / "logs"
    log_dir.mkdir(parents=True)
    log = log_dir / "nexium-test.log"
    log.write_text(
        "Auto-loaded NRO: nexium-guest-hid-probe.nro\n"
        "Booting NRO: nexium-guest-hid-probe.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "OutputDebugString: STAGE40_GUEST_HID_PROBE_START\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
        "OutputDebugString: STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP\n",
        encoding="utf-8",
    )
    return report_dir, positive, log


class Stage41NoVirtualGuestControlTests(unittest.TestCase):
    def test_idle_guest_negative_control_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, _ = fixture(Path(td))
            r = audit_no_virtual(report_dir, positive)
            self.assertTrue(r["no_virtual_guest_control_passed"])
            self.assertTrue(r["negative_same_nro_guest_boot_and_hid_map_observed"])
            self.assertEqual(r["negative_original_npad_sample_count"], 1)
            self.assertFalse(r["physical_controller_verified"])

    def test_host_synthetic_b_press_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, _ = fixture(Path(td))
            (report_dir / "nexium-console.log").write_text(
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE\n",
                encoding="utf-8",
            )
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_host_synthetic_b_markers_absent"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_original_npad_b_sample_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            with log.open("a", encoding="utf-8") as stream:
                stream.write("[hid-publish] npad=[0x2, 0x0]\n")
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_published_npad_b_absent"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_guest_b_down_marker_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            with log.open("a", encoding="utf-8") as stream:
                stream.write("OutputDebugString: STAGE40_GUEST_HID_B_DOWN\n")
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_guest_b_markers_absent"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_orphan_guest_b_up_marker_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            with log.open("a", encoding="utf-8") as stream:
                stream.write("OutputDebugString: STAGE40_GUEST_HID_B_UP\\n")
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_guest_b_markers_absent"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_guest_end_marker_before_start_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            text = log.read_text(encoding="utf-8")
            marker = "OutputDebugString: STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP\\n"
            text = text.replace(marker, "")
            text = marker + text
            log.write_text(text, encoding="utf-8")
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_guest_probe_exited_without_b_observed"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_missing_guest_end_marker_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            log.write_text(
                log.read_text(encoding="utf-8").replace(
                    "OutputDebugString: STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP\n", ""
                ),
                encoding="utf-8",
            )
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_guest_probe_exited_without_b_observed"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_console_guest_end_marker_cannot_substitute_for_real_svc(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            log.write_text(
                log.read_text(encoding="utf-8").replace(
                    "OutputDebugString: STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP\n", ""
                ),
                encoding="utf-8",
            )
            (report_dir / "nexium-console.log").write_text(
                "OutputDebugString: STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP\n",
                encoding="utf-8",
            )
            self.assertFalse(audit_no_virtual(report_dir, positive)["no_virtual_guest_control_passed"])

    def test_guest_boot_failure_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            with log.open("a", encoding="utf-8") as stream:
                stream.write("Boot failed: simulated backend failure\n")
            r = audit_no_virtual(report_dir, positive)
            self.assertFalse(r["negative_same_nro_guest_boot_and_hid_map_observed"])
            self.assertFalse(r["no_virtual_guest_control_passed"])

    def test_no_hid_mapping_rejects_negative(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            log.write_text(
                log.read_text(encoding="utf-8").replace(
                    "recognized as HID shared memory\n", ""
                ), encoding="utf-8",
            )
            self.assertFalse(audit_no_virtual(report_dir, positive)["no_virtual_guest_control_passed"])

    def test_unverified_stage40_positive_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, _ = fixture(Path(td))
            positive.write_text(json.dumps({
                "schema": "nexium-stage40-guest-npad-readback/v1",
                "same_process_guest_input_roundtrip_passed": False,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "positive"):
                audit_no_virtual(report_dir, positive)

    def test_no_filelogger_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir, positive, log = fixture(Path(td))
            log.unlink()
            with self.assertRaisesRegex(ValueError, "exactly one"):
                audit_no_virtual(report_dir, positive)


if __name__ == "__main__":
    unittest.main()
