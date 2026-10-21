import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_right_stick_x import (
    patch_source, PULSE, OBSERVE, BUTTON_ANCHOR, SNAPSHOT_ANCHOR,
)
from apply_macos_guest_left_stick_x import (
    INSERT as STAGE44_PULSE, OBSERVE as STAGE44_OBSERVE,
)
from apply_macos_guest_left_stick_y import (
    PULSE as STAGE45_PULSE, OBSERVE as STAGE45_OBSERVE,
)
from audit_guest_right_stick_x import (
    audit, GUEST, HOST_AXIS, HOST_SNAPSHOT, B_PRESS, B_RELEASE,
)


def source_fixture():
    return (
        "desc.axis_mask = 0x3fu32;\n"
        + STAGE44_PULSE + STAGE45_PULSE + BUTTON_ANCHOR + "\n"
        + STAGE44_OBSERVE + STAGE45_OBSERVE + SNAPSHOT_ANCHOR + "\n"
    )


def runtime_fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    host = root / "nexium-console.log"
    host.write_text("\n".join((B_PRESS, *HOST_AXIS, *HOST_SNAPSHOT, B_RELEASE)) + "\n",
                    encoding="utf-8")
    log_dir = root / "data-root" / "logs"
    log_dir.mkdir(parents=True)
    guest = log_dir / "nexium-fixture.log"
    guest.write_text(
        "Auto-loaded NRO: stage46.nro\n"
        "Booting NRO: stage46.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        + "".join("OutputDebugString: " + m + "\n" for m in GUEST)
        + "[hid-publish] npad=[0x0, 0x0]\n",
        encoding="utf-8",
    )
    return host, guest


class Stage46PatchTests(unittest.TestCase):
    def test_source_instruments_original_sdl_rightx_and_snapshot(self):
        result = patch_source(source_fixture())
        self.assertIn(PULSE, result)
        self.assertIn(OBSERVE, result)
        self.assertIn("SDL_SetJoystickVirtualAxis(ptr, 2, right_x)", result)
        self.assertIn("let rx = snap.sticks[2]", result)

    def test_idempotent(self):
        patched = patch_source(source_fixture())
        self.assertEqual(patched, patch_source(patched))

    def test_missing_stage45_predecessor_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(STAGE45_PULSE, ""))

    def test_missing_stage44_predecessor_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(STAGE44_OBSERVE, ""))

    def test_missing_button_anchor_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(BUTTON_ANCHOR, ""))

    def test_missing_original_snapshot_anchor_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(SNAPSHOT_ANCHOR, ""))

    def test_missing_virtual_right_axis_mask_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("desc.axis_mask = 0x3fu32;", ""))

    def test_partial_patch_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(BUTTON_ANCHOR, PULSE + BUTTON_ANCHOR))


class Stage46GuestTests(unittest.TestCase):
    def test_full_source_bound_guest_roundtrip_passes_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_fixture(root)
            result = audit(root)
            self.assertTrue(result["same_process_guest_right_x_roundtrip_passed"])
            self.assertTrue(result["original_input_snapshot_right_x_ordered"])
            self.assertFalse(result["physical_controller_verified"])

    def test_guest_marker_only_in_host_stdout_cannot_fake_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, guest = runtime_fixture(root)
            marker = "OutputDebugString: " + GUEST[3] + "\n"
            guest.write_text(guest.read_text().replace(marker, ""), encoding="utf-8")
            with host.open("a", encoding="utf-8") as fd:
                fd.write(marker)
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])

    def test_missing_virtual_positive_pulse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_AXIS[2], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])

    def test_missing_original_rightx_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_SNAPSHOT[0], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])

    def test_no_guest_hid_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace("recognized as HID shared memory\n", ""),
                             encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])

    def test_guest_incomplete_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE46_GUEST_RIGHT_X_INCOMPLETE\n")
            result = audit(root)
            self.assertFalse(result["same_process_guest_right_x_roundtrip_passed"])
            self.assertTrue(result["guest_incomplete_marker_observed"])

    def test_unexpected_guest_button_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE46_GUEST_UNEXPECTED_DIGITAL_BUTTON\n")
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])

    def test_original_npad_release_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace("[hid-publish] npad=[0x0, 0x0]\n", ""),
                             encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])

    def test_rightx_outside_host_b_hold_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(B_PRESS + "\n", "") + B_PRESS + "\n",
                            encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_right_x_roundtrip_passed"])


if __name__ == "__main__":
    unittest.main()
