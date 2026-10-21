import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_dual_stick import (
    patch_source, PULSE, OBSERVE, BUTTON_ANCHOR, SNAPSHOT_ANCHOR,
)
from audit_guest_dual_stick import (
    audit, GUEST, HOST_AXIS, HOST_SNAPSHOT, B_PRESS, B_RELEASE,
)


def source_fixture():
    return (
        "desc.axis_mask = 0x3fu32;\n"
        'NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE\n'
        'NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE\n'
        'NEXIUM_MACOS_GUEST_RIGHT_X_PROBE\n'
        'NEXIUM_MACOS_GUEST_RIGHT_X_PROBE\n'
        + BUTTON_ANCHOR + "\n"
        + SNAPSHOT_ANCHOR + "\n"
    )


def runtime_fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    host = root / "nexium-console.log"
    host.write_text(
        "\n".join((B_PRESS, *HOST_AXIS, *HOST_SNAPSHOT, B_RELEASE)) + "\n",
        encoding="utf-8",
    )
    logs = root / "data-root" / "logs"
    logs.mkdir(parents=True)
    guest = logs / "nexium-stage48-fixture.log"
    guest.write_text(
        "Auto-loaded NRO: stage48.nro\n"
        "Booting NRO: stage48.nro\n"
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


class Stage48SourcePatchTests(unittest.TestCase):
    def test_inserts_two_sticks_simultaneously(self):
        patched = patch_source(source_fixture())
        self.assertIn(PULSE, patched)
        self.assertIn(OBSERVE, patched)
        self.assertIn("SDL_SetJoystickVirtualAxis(ptr, 3, ry)", patched)
        for i in range(4):
            self.assertIn(f"snap.sticks[{i}]", patched)

    def test_is_idempotent(self):
        patched = patch_source(source_fixture())
        self.assertEqual(patched, patch_source(patched))

    def test_missing_right_y_predecessor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("NEXIUM_MACOS_GUEST_RIGHT_Y_PROBE", "", 1))

    def test_missing_right_x_predecessor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("NEXIUM_MACOS_GUEST_RIGHT_X_PROBE", "", 1))

    def test_missing_snapshot_anchor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(SNAPSHOT_ANCHOR, ""))

    def test_partial_instrumentation_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(BUTTON_ANCHOR, PULSE + BUTTON_ANCHOR))


class Stage48GuestAuditTests(unittest.TestCase):
    def test_authentic_simultaneous_four_axis_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_fixture(root)
            report = audit(root)
            self.assertTrue(report["same_process_guest_dual_stick_passed"])
            self.assertTrue(report["original_single_input_snapshot_diagonal_phases_in_order"])
            self.assertFalse(report["physical_controller_verified"])

    def test_fake_guest_console_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, guest = runtime_fixture(root)
            marker = "OutputDebugString: " + GUEST[4] + "\n"
            guest.write_text(guest.read_text().replace(marker, ""), encoding="utf-8")
            with host.open("a", encoding="utf-8") as fd:
                fd.write(marker)
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_missing_host_diagonal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_AXIS[2], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_missing_original_simultaneous_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(
                host.read_text().replace(HOST_SNAPSHOT[2], ""), encoding="utf-8"
            )
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_guest_incomplete_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE48_GUEST_DUAL_STICK_INCOMPLETE\n")
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_guest_unexpected_button_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as fd:
                fd.write("OutputDebugString: STAGE48_GUEST_UNEXPECTED_DIGITAL_BUTTON\n")
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_virtual_axis_failure_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            with host.open("a", encoding="utf-8") as fd:
                fd.write("STAGE48_DUAL_AXIS_SET_FAILED\n")
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_missing_original_npad_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace(
                "[hid-publish] npad=[0x0, 0x0]\n", ""
            ), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_missing_hid_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(
                guest.read_text().replace("recognized as HID shared memory\n", ""),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])

    def test_axis_sent_after_b_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(
                host.read_text().replace(B_RELEASE + "\n", "")
                .replace(B_PRESS + "\n", B_PRESS + "\n" + B_RELEASE + "\n"),
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_dual_stick_passed"])


if __name__ == "__main__":
    unittest.main()
