"""Stage53 strict source/guest boundary-crossing and fail-closed tests."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_deadzone_threshold import (
    patch_source, PULSE, OBSERVE, BUTTON_ANCHOR, SNAPSHOT_ANCHOR,
)
from audit_guest_deadzone_threshold import (
    audit, GUEST, HOST_PULSE, HOST_SOURCE, B_PRESS, B_RELEASE,
)


def source_fixture():
    return (
        "desc.axis_mask = 0x3fu32;\n"
        "NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE\n"
        "NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE\n"
        "let dz = |v: f32, limit: f32| if v.abs() < limit { 0.0 } else { v };\n"
        "snap.raw_sticks = [lx, ly, rx, ry];\n"
        + BUTTON_ANCHOR + "\n" + SNAPSHOT_ANCHOR + "\n"
    )


def runtime_fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    host = root / "nexium-console.log"
    host.write_text(
        "\n".join((B_PRESS, *HOST_PULSE, *HOST_SOURCE, B_RELEASE)) + "\n",
        encoding="utf-8",
    )
    logdir = root / "data-root" / "logs"
    logdir.mkdir(parents=True)
    guest = logdir / "nexium-stage53-fixture.log"
    guest.write_text(
        "Auto-loaded NRO: stage53.nro\n"
        "Booting NRO: stage53.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        + "".join("OutputDebugString: " + marker + "\n" for marker in GUEST)
        + "[hid-publish] npad=[0x0, 0x0]\n",
        encoding="utf-8",
    )
    return host, guest


class Stage53SourceTests(unittest.TestCase):
    def test_pinned_threshold_source_instrumentation(self):
        patched = patch_source(source_fixture())
        self.assertIn(PULSE, patched)
        self.assertIn(OBSERVE, patched)
        for i in range(4):
            self.assertIn(f"SDL_SetJoystickVirtualAxis(ptr, {i},", patched)
        self.assertIn("snap.raw_sticks", patched)
        self.assertIn("snap.sticks", patched)
        self.assertIn("6000", patched)
        self.assertIn("3000", patched)

    def test_idempotent(self):
        result = patch_source(source_fixture())
        self.assertEqual(patch_source(result), result)

    def test_missing_stage52_predecessor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("NEXIUM_MACOS_GUEST_DEADZONE_JITTER_PROBE", "", 1))

    def test_original_deadzone_algorithm_change_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("let dz =", "let unrelated =", 1))

    def test_original_snapshot_source_drift_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("snap.raw_sticks =", "snap.changed =", 1))

    def test_original_virtual_axis_descriptor_drift_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("desc.axis_mask = 0x3fu32;", ""))

    def test_partial_patch_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(BUTTON_ANCHOR, PULSE + BUTTON_ANCHOR))

    def test_original_snapshot_anchor_missing_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(SNAPSHOT_ANCHOR, ""))


class Stage53GuestTests(unittest.TestCase):
    def test_source_bound_deadzone_threshold_fixture_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_fixture(root)
            report = audit(root)
            self.assertTrue(report["same_process_guest_deadzone_threshold_passed"])
            self.assertTrue(report["original_source_below_zero_above_signed_all_four_axes"])
            self.assertFalse(report["physical_controller_verified"])

    def test_only_host_console_guest_marker_not_a_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, guest = runtime_fixture(root)
            marker = "OutputDebugString: " + GUEST[4] + "\n"
            guest.write_text(guest.read_text().replace(marker, ""), encoding="utf-8")
            with host.open("a", encoding="utf-8") as stream:
                stream.write(marker)
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_missing_below_threshold_pulse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_PULSE[0], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_missing_above_threshold_source_observer_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_SOURCE[4], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_missing_npad_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace("[hid-publish] npad=[0x0, 0x0]\n", ""),
                             encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_original_hid_map_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace("recognized as HID shared memory\n", ""),
                             encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_guest_timeout_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as stream:
                stream.write("OutputDebugString: STAGE53_GUEST_THRESHOLD_INCOMPLETE\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_unexpected_guest_digital_button_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as stream:
                stream.write("OutputDebugString: STAGE53_GUEST_UNEXPECTED_DIGITAL_BUTTON\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_host_axis_failure_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            with host.open("a", encoding="utf-8") as stream:
                stream.write("STAGE53_THRESHOLD_VIRTUAL_AXIS_FAILED\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])

    def test_host_b_release_before_above_phase_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(B_PRESS + "\n", "")
                            .replace(B_RELEASE + "\n", "") + B_PRESS + "\n" + B_RELEASE + "\n",
                            encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_threshold_passed"])


if __name__ == "__main__":
    unittest.main()
