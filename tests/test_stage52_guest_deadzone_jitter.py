"""Stage52 source-accurate low-amplitude analog jitter contract and negative tests."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_deadzone_jitter import (
    patch_source, PULSE, OBSERVE, BUTTON_ANCHOR, SNAPSHOT_ANCHOR,
)
from audit_guest_deadzone_jitter import (
    audit, GUEST, HOST_PULSE, HOST_ORIGINAL, B_PRESS, B_RELEASE,
)


def source_fixture():
    return (
        "desc.axis_mask = 0x3fu32;\n"
        "NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE\n"
        "NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE\n"
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
        "\n".join((B_PRESS, *HOST_PULSE, *HOST_ORIGINAL, B_RELEASE)) + "\n",
        encoding="utf-8",
    )
    logdir = root / "data-root" / "logs"
    logdir.mkdir(parents=True)
    guest = logdir / "nexium-stage52-fixture.log"
    guest.write_text(
        "Auto-loaded NRO: stage52.nro\n"
        "Booting NRO: stage52.nro\n"
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


class Stage52SourceTests(unittest.TestCase):
    def test_jitter_writes_four_virtual_axes_but_reads_real_snapshot(self):
        result = patch_source(source_fixture())
        self.assertIn(PULSE, result)
        self.assertIn(OBSERVE, result)
        for i in range(4):
            self.assertIn(f"SDL_SetJoystickVirtualAxis(ptr, {i},", result)
            self.assertIn(f"p[{i}] == 0", result)
        self.assertIn("let r = snap.raw_sticks;", result)
        self.assertIn("let p = snap.sticks;", result)

    def test_patch_idempotent(self):
        patched = patch_source(source_fixture())
        self.assertEqual(patched, patch_source(patched))

    def test_missing_existing_four_axis_source_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE", "", 1))

    def test_missing_original_deadzone_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("let dz =", "let removed =", 1))

    def test_missing_original_raw_snapshot_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace("snap.raw_sticks = [lx, ly, rx, ry];", ""))

    def test_missing_original_button_anchor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(BUTTON_ANCHOR, ""))

    def test_missing_original_snapshot_anchor_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(SNAPSHOT_ANCHOR, ""))

    def test_partial_install_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(source_fixture().replace(BUTTON_ANCHOR, PULSE + BUTTON_ANCHOR))


class Stage52GuestTests(unittest.TestCase):
    def test_original_three_channel_source_bound_fixture_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_fixture(root)
            receipt = audit(root)
            self.assertTrue(receipt["same_process_guest_deadzone_jitter_passed"])
            self.assertTrue(receipt["original_raw_nonzero_processed_zero_all_four_axes_observed"])
            self.assertFalse(receipt["physical_controller_verified"])

    def test_guest_marker_only_in_host_stdout_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, guest = runtime_fixture(root)
            m = "OutputDebugString: " + GUEST[2] + "\n"
            guest.write_text(guest.read_text().replace(m, ""), encoding="utf-8")
            with host.open("a", encoding="utf-8") as out:
                out.write(m)
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_missing_sdl_low_amplitude_pulse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_PULSE[2], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_missing_raw_processed_source_observation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(host.read_text().replace(HOST_ORIGINAL[0], ""), encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_host_pulses_outside_b_hold_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            host.write_text(
                host.read_text().replace(B_PRESS + "\n", "") + B_PRESS + "\n",
                encoding="utf-8",
            )
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_guest_analog_leak_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as out:
                out.write("OutputDebugString: STAGE52_GUEST_ANALOG_DEADZONE_LEAK\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_guest_hold_too_short_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as out:
                out.write("OutputDebugString: STAGE52_GUEST_B_HOLD_TOO_SHORT\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_guest_incomplete_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            with guest.open("a", encoding="utf-8") as out:
                out.write("OutputDebugString: STAGE52_GUEST_JITTER_INCOMPLETE\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_virtual_axis_error_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            host, _ = runtime_fixture(root)
            with host.open("a", encoding="utf-8") as out:
                out.write("STAGE52_JITTER_VIRTUAL_AXIS_SET_FAILED\n")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_missing_original_hid_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace("recognized as HID shared memory\n", ""),
                             encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])

    def test_original_npad_b_release_missing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, guest = runtime_fixture(root)
            guest.write_text(guest.read_text().replace("[hid-publish] npad=[0x0, 0x0]\n", ""),
                             encoding="utf-8")
            self.assertFalse(audit(root)["same_process_guest_deadzone_jitter_passed"])


if __name__ == "__main__":
    unittest.main()
