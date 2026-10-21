import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_left_stick_x import patch_source, ANCHOR, INSERT, OBSERVE_ANCHOR, OBSERVE
from apply_macos_guest_dpad_probe import STAGE43_MASK, STAGE43_DPAD_PULSES
from audit_guest_left_stick_x import (
    audit, GUEST_MARKERS, HOST_AXIS_MARKERS, HOST_SNAPSHOT_MARKERS, HOST_B,
)


def source_fixture():
    return (
        STAGE43_MASK + "\n"
        + "desc.axis_mask = 0x3fu32;\n"
        + "NEXIUM_MACOS_GUEST_HID_PROBE\n"
        + STAGE43_DPAD_PULSES
        + ANCHOR + "\n"
        + OBSERVE_ANCHOR + "\n"
    )


def runtime_fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    console = root / "nexium-console.log"
    console.write_text("\n".join((
        HOST_B[0],
        *HOST_AXIS_MARKERS,
        *HOST_SNAPSHOT_MARKERS,
        HOST_B[1],
    )) + "\n", encoding="utf-8")
    logs = root / "data-root" / "logs"
    logs.mkdir(parents=True)
    log = logs / "nexium-test.log"
    log.write_text(
        "Auto-loaded NRO: stage44.nro\n"
        "Booting NRO: stage44.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        + "".join("OutputDebugString: " + m + "\n" for m in GUEST_MARKERS)
        + "[hid-publish] npad=[0x0, 0x0]\n",
        encoding="utf-8",
    )
    return console, log


class Stage44PatchContractTests(unittest.TestCase):
    def test_adds_axis_and_original_snapshot_observer(self):
        result = patch_source(source_fixture())
        self.assertIn(INSERT, result)
        self.assertIn(OBSERVE, result)

    def test_second_patch_idempotent(self):
        result = patch_source(source_fixture())
        self.assertEqual(result, patch_source(result))

    def test_incomplete_source_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(ANCHOR, ""))

    def test_missing_prior_dpad_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(STAGE43_DPAD_PULSES, ""))

    def test_missing_virtual_axis_decl_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("desc.axis_mask = 0x3fu32;", ""))

    def test_partial_patch_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(ANCHOR, INSERT + ANCHOR))


class Stage44GuestAnalogAuditTests(unittest.TestCase):
    def test_authentic_three_channel_fixture_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_fixture(root)
            report = audit(root)
            self.assertTrue(report["same_process_guest_left_x_roundtrip_passed"])
            self.assertTrue(report["original_sdl3_input_snapshot_left_x_ordered"])
            self.assertFalse(report["physical_controller_verified"])

    def test_guest_phase_only_in_host_console_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, log = runtime_fixture(root)
            marker = "OutputDebugString: " + GUEST_MARKERS[3] + "\n"
            log.write_text(log.read_text(encoding="utf-8").replace(marker, ""),
                           encoding="utf-8")
            with console.open("a", encoding="utf-8") as fd:
                fd.write(marker)
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])

    def test_missing_host_axis_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = runtime_fixture(root)
            console.write_text(console.read_text(encoding="utf-8").replace(
                HOST_AXIS_MARKERS[2], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])

    def test_missing_original_input_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = runtime_fixture(root)
            console.write_text(console.read_text(encoding="utf-8").replace(
                HOST_SNAPSHOT_MARKERS[2], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])

    def test_no_original_npad_b_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = runtime_fixture(root)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "[hid-publish] npad=[0x0, 0x0]\n", ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])

    def test_missing_guest_hid_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = runtime_fixture(root)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "recognized as HID shared memory\n", ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])

    def test_guest_incomplete_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = runtime_fixture(root)
            with log.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE44_GUEST_STICK_X_INCOMPLETE\n")
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])

    def test_axis_outside_b_hold_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = runtime_fixture(root)
            text = console.read_text(encoding="utf-8")
            text = text.replace(HOST_B[0] + "\n", "")
            text += HOST_B[0] + "\n"
            console.write_text(text, encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_left_x_roundtrip_passed"])


if __name__ == "__main__":
    unittest.main()
