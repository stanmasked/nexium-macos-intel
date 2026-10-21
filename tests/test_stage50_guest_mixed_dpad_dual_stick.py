import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_guest_mixed_dpad_dual_stick import (
    audit, GUEST, HOST_MIXED, SOURCE_SNAPSHOT,
)


def fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    host = root / "nexium-console.log"
    host.write_text(
        "\n".join((*HOST_MIXED, *SOURCE_SNAPSHOT)) + "\n", encoding="utf-8"
    )
    logs = root / "data-root" / "logs"
    logs.mkdir(parents=True)
    guest = logs / "nexium-stage50-fixture.log"
    guest.write_text(
        "Auto-loaded NRO: stage50.nro\n"
        "Booting NRO: stage50.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "[hid-publish] npad=[0x2002, 0x2002]\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "[hid-publish] npad=[0x4002, 0x4002]\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
        + "".join("OutputDebugString: " + m + "\n" for m in GUEST),
        encoding="utf-8",
    )
    return host, guest


class Stage50MixedDigitalAnalogAuditTests(unittest.TestCase):
    def test_realistic_original_three_channel_fixture_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            result = audit(root)
            self.assertTrue(result["same_process_guest_mixed_digital_analog_passed"])
            self.assertEqual(result["original_npad_serialized_sample_count"], 6)
            self.assertFalse(result["physical_controller_verified"])

    def test_guest_marker_forged_only_in_host_stdout_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, guest = fixture(root)
            marker = "OutputDebugString: " + GUEST[4] + "\n"
            guest.write_text(guest.read_text().replace(marker, ""), encoding="utf-8")
            with host.open("a", encoding="utf-8") as fd:
                fd.write(marker)
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_missing_sdl_up_press_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = fixture(root)
            host.write_text(
                host.read_text().replace("STAGE43_DPAD_UP_PRESS_SENT", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_wrong_interleave_of_dpad_right_and_second_diagonal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = fixture(root)
            text = host.read_text()
            text = text.replace(
                "STAGE43_DPAD_RIGHT_PRESS_SENT\nSTAGE48_DUAL_DIAGONAL_B_SENT\n",
                "STAGE48_DUAL_DIAGONAL_B_SENT\nSTAGE43_DPAD_RIGHT_PRESS_SENT\n",
            )
            host.write_text(text, encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_one_original_four_axis_snapshot_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = fixture(root)
            host.write_text(
                host.read_text().replace(SOURCE_SNAPSHOT[2], ""), encoding="utf-8"
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_guest_up_combination_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            marker = "OutputDebugString: STAGE50_GUEST_B_UP_AND_DUAL_DIAGONAL_A\n"
            guest.write_text(guest.read_text().replace(marker, ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_npad_up_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            guest.write_text(
                guest.read_text().replace("[hid-publish] npad=[0x2002, 0x2002]\n", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_npad_right_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            guest.write_text(
                guest.read_text().replace("[hid-publish] npad=[0x4002, 0x4002]\n", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_npad_unexpected_a_button_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            guest.write_text(
                guest.read_text().replace("npad=[0x4002, 0x4002]", "npad=[0x4003, 0x4003]"),
                encoding="utf-8",
            )
            report = audit(root)
            self.assertFalse(report["same_process_guest_mixed_digital_analog_passed"])
            self.assertTrue(report["original_npad_unexpected_button_bits_observed"])

    def test_npad_up_right_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            guest.write_text(
                guest.read_text().replace("npad=[0x2002, 0x2002]", "npad=[0x6002, 0x6002]"),
                encoding="utf-8",
            )
            receipt = audit(root)
            self.assertFalse(receipt["same_process_guest_mixed_digital_analog_passed"])
            self.assertTrue(
                receipt["original_npad_opposite_directions_same_sample_observed"]
            )

    def test_guest_spurious_button_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            with guest.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE50_GUEST_SPURIOUS_OR_OVERLAPPED_DIGITAL\n")
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_guest_timeout_incomplete_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            with guest.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE50_GUEST_MIXED_INCOMPLETE\n")
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_virtual_axis_failure_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = fixture(root)
            with host.open("a", encoding="utf-8") as fd:
                fd.write("STAGE48_DUAL_AXIS_SET_FAILED\n")
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_host_dpad_button_set_failed_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = fixture(root)
            with host.open("a", encoding="utf-8") as fd:
                fd.write("STAGE43_DPAD_RIGHT_SET_FAILED\n")
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_guest_hid_mapping_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            guest.write_text(
                guest.read_text().replace("recognized as HID shared memory\n", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_no_npad_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = fixture(root)
            guest.write_text(
                guest.read_text().replace("[hid-publish] npad=[0x0, 0x0]\n", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])

    def test_missing_host_b_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = fixture(root)
            host.write_text(
                host.read_text().replace("STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_mixed_digital_analog_passed"])


if __name__ == "__main__":
    unittest.main()
