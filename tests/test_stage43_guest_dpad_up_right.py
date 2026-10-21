import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_dpad_probe import (
    patch_source, STAGE42_MASK, STAGE43_MASK, STAGE43_DPAD_PULSES, BUTTON_ANCHOR,
)
from audit_guest_dpad_up_right import audit, npad_direction_sequence, B, UP, RIGHT


def original_stage42_source():
    return (
        STAGE42_MASK + "\n"
        + 'NEXIUM_MACOS_GUEST_HID_PROBE\n'
        + 'NEXIUM_MACOS_GUEST_AB_PROBE\n'
        + BUTTON_ANCHOR + "\n"
    )


def fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    console = root / "nexium-console.log"
    console.write_text(
        "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE\n"
        "STAGE43_DPAD_UP_PRESS_SENT\n"
        "STAGE43_DPAD_UP_RELEASE_SENT\n"
        "STAGE43_DPAD_RIGHT_PRESS_SENT\n"
        "STAGE43_DPAD_RIGHT_RELEASE_SENT\n"
        "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE\n",
        encoding="utf-8",
    )
    logs = root / "data-root" / "logs"
    logs.mkdir(parents=True)
    log = logs / "nexium-test.log"
    log.write_text(
        "Auto-loaded NRO: nexium-guest-dpad.nro\n"
        "Booting NRO: nexium-guest-dpad.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "OutputDebugString: STAGE43_GUEST_DPAD_PROBE_START\n"
        "OutputDebugString: STAGE43_GUEST_B_ONLY_FIRST\n"
        "[hid-publish] npad=[0x2002, 0x2002]\n"
        "OutputDebugString: STAGE43_GUEST_B_AND_UP\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "OutputDebugString: STAGE43_GUEST_B_ONLY_AFTER_UP\n"
        "[hid-publish] npad=[0x4002, 0x4002]\n"
        "OutputDebugString: STAGE43_GUEST_B_AND_RIGHT\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "OutputDebugString: STAGE43_GUEST_B_ONLY_AFTER_RIGHT\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
        "OutputDebugString: STAGE43_GUEST_ALL_RELEASED\n"
        "OutputDebugString: STAGE43_GUEST_DPAD_PASS\n",
        encoding="utf-8",
    )
    return console, log


class Stage43DpadSourcePatchTests(unittest.TestCase):
    def test_pinned_stage42_patch_works(self):
        output = patch_source(original_stage42_source())
        self.assertIn(STAGE43_MASK, output)
        self.assertIn(STAGE43_DPAD_PULSES, output)
        self.assertEqual(output.count("NEXIUM_MACOS_GUEST_DPAD_PROBE"), 2)

    def test_patch_is_idempotent(self):
        output = patch_source(original_stage42_source())
        self.assertEqual(output, patch_source(output))

    def test_missing_stage40_gate_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(original_stage42_source().replace("NEXIUM_MACOS_GUEST_HID_PROBE", ""))

    def test_partial_instrumentation_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(original_stage42_source().replace(STAGE42_MASK, STAGE43_MASK))

    def test_duplicate_button_anchor_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(original_stage42_source() + BUTTON_ANCHOR)


class Stage43GuestDpadAuditTests(unittest.TestCase):
    def test_realistic_b_up_b_right_b_neutral_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            r = audit(root)
            self.assertTrue(r["same_process_guest_dpad_readback_passed"])
            self.assertEqual(r["original_npad_serialized_sample_count"], 7)

    def test_guest_marker_forged_in_host_console_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, log = fixture(root)
            msg = "OutputDebugString: STAGE43_GUEST_B_AND_UP\n"
            log.write_text(log.read_text(encoding="utf-8").replace(msg, ""), encoding="utf-8")
            with console.open("a", encoding="utf-8") as fd:
                fd.write(msg)
            self.assertFalse(audit(root)["same_process_guest_dpad_readback_passed"])

    def test_missing_hid_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = fixture(root)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "recognized as HID shared memory\n", ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_dpad_readback_passed"])

    def test_unexpected_guest_button_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = fixture(root)
            with log.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE43_GUEST_DPAD_UNEXPECTED_BUTTON\n")
            self.assertFalse(audit(root)["same_process_guest_dpad_readback_passed"])

    def test_host_right_press_before_up_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = fixture(root)
            console.write_text(console.read_text(encoding="utf-8").replace(
                "STAGE43_DPAD_UP_RELEASE_SENT\n",
                "STAGE43_DPAD_RIGHT_PRESS_SENT\nSTAGE43_DPAD_UP_RELEASE_SENT\n",
            ).replace(
                "STAGE43_DPAD_RIGHT_PRESS_SENT\nSTAGE43_DPAD_RIGHT_RELEASE_SENT",
                "STAGE43_DPAD_RIGHT_RELEASE_SENT",
            ), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_dpad_readback_passed"])

    def test_npad_missing_up_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = fixture(root)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "[hid-publish] npad=[0x2002, 0x2002]\n",
                "[hid-publish] npad=[0x2, 0x2]\n",
            ), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_dpad_readback_passed"])

    def test_npad_wrong_button_a_rejected(self):
        self.assertFalse(npad_direction_sequence([
            [B], [B | UP], [B], [B | RIGHT | 1], [B], [0],
        ]))

    def test_npad_wrong_order_rejected(self):
        self.assertFalse(npad_direction_sequence([
            [0], [B], [B | RIGHT], [B], [B | UP], [B], [0],
        ]))

    def test_npad_up_and_right_simultaneous_rejected(self):
        self.assertFalse(npad_direction_sequence([
            [B], [B | UP], [B], [B | UP | RIGHT], [B], [0],
        ]))


if __name__ == "__main__":
    unittest.main()
