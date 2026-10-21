import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_right_stick_y import (
    patch_source, PULSE, OBSERVE, ANCHOR, OBSERVE_ANCHOR,
)
from apply_macos_guest_left_stick_x import (
    INSERT as STAGE44_PULSE, OBSERVE as STAGE44_OBSERVE,
)
from apply_macos_guest_left_stick_y import PULSE as STAGE45_PULSE, OBSERVE as STAGE45_OBSERVE
from apply_macos_guest_right_stick_x import PULSE as STAGE46_PULSE, OBSERVE as STAGE46_OBSERVE
from audit_guest_right_stick_y import audit, GUEST, HOST_AXIS, HOST_SNAPSHOT, B_DOWN, B_UP


def source_fixture():
    return (
        "desc.axis_mask = 0x3fu32;\n"
        + STAGE44_PULSE + STAGE45_PULSE + STAGE46_PULSE + ANCHOR + "\n"
        + STAGE44_OBSERVE + STAGE45_OBSERVE + STAGE46_OBSERVE
        + OBSERVE_ANCHOR + "\n"
    )


def runtime_fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    host = root / "nexium-console.log"
    host.write_text("\n".join((B_DOWN, *HOST_AXIS, *HOST_SNAPSHOT, B_UP)) + "\n",
                    encoding="utf-8")
    logdir = root / "data-root" / "logs"
    logdir.mkdir(parents=True)
    log = logdir / "nexium-test.log"
    log.write_text(
        "Auto-loaded NRO: stage47.nro\n"
        "Booting NRO: stage47.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        + "".join("OutputDebugString: " + mark + "\n" for mark in GUEST)
        + "[hid-publish] npad=[0x0, 0x0]\n",
        encoding="utf-8",
    )
    return host, log


class Stage47SourceTests(unittest.TestCase):
    def test_original_stick_y_pulse_and_read_only_snapshot_observer(self):
        patched = patch_source(source_fixture())
        self.assertIn(PULSE, patched)
        self.assertIn(OBSERVE, patched)
        self.assertIn("snap.sticks[3]", patched)
        self.assertIn("SDL_SetJoystickVirtualAxis(ptr, 3, y)", patched)

    def test_idempotent(self):
        patched = patch_source(source_fixture())
        self.assertEqual(patched, patch_source(patched))

    def test_missing_stage46_predecessor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(STAGE46_PULSE, ""))

    def test_missing_axis_mask_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("desc.axis_mask = 0x3fu32;", ""))

    def test_missing_original_snapshot_anchor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(OBSERVE_ANCHOR, ""))

    def test_partial_patch_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(ANCHOR, PULSE + ANCHOR))


class Stage47GuestTests(unittest.TestCase):
    def test_authentic_guest_positive_up_negative_down(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_fixture(root)
            result = audit(root)
            self.assertTrue(result["same_process_guest_right_y_roundtrip_passed"])
            self.assertTrue(result["original_input_snapshot_inverted_y_sign_observed"])
            self.assertFalse(result["physical_controller_verified"])

    def test_forged_guest_marker_only_in_stdout_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, guest = runtime_fixture(root)
            marker = "OutputDebugString: " + GUEST[3] + "\n"
            guest.write_text(guest.read_text().replace(marker, ""), encoding="utf-8")
            with console.open("a", encoding="utf-8") as stream:
                stream.write(marker)
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])

    def test_missing_sdl_down_pulse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = runtime_fixture(root)
            console.write_text(console.read_text().replace(HOST_AXIS[2], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])

    def test_missing_original_snapshot_up_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = runtime_fixture(root)
            console.write_text(console.read_text().replace(HOST_SNAPSHOT[0], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])

    def test_guest_incomplete_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = runtime_fixture(root)
            with log.open("a", encoding="utf-8") as stream:
                stream.write("OutputDebugString: STAGE47_GUEST_RIGHT_Y_INCOMPLETE\n")
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])

    def test_missing_hid_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = runtime_fixture(root)
            log.write_text(log.read_text().replace("recognized as HID shared memory\n", ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])

    def test_missing_npad_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, log = runtime_fixture(root)
            log.write_text(log.read_text().replace("[hid-publish] npad=[0x0, 0x0]\n", ""),
                           encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])

    def test_y_excursions_outside_b_hold_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console, _ = runtime_fixture(root)
            text = console.read_text().replace(B_DOWN + "\n", "") + B_DOWN + "\n"
            console.write_text(text, encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_y_roundtrip_passed"])


if __name__ == "__main__":
    unittest.main()
