from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_guest_ab_probe import (
    patch_source,
    OLD_MASK, NEW_MASK, OLD_SEND, NEW_SEND,
)
from audit_guest_ab_chord import audit, npad_chord_order, ordered


class Stage42AbSourcePatchTests(unittest.TestCase):
    def source(self):
        return (
            "fn injected() {\n"
            + OLD_MASK + "\n"
            + "NEXIUM_MACOS_GUEST_HID_PROBE\n"
            + OLD_SEND + "\n"
            + "}\n"
        )

    def test_exact_source_patch(self):
        after = patch_source(self.source())
        self.assertIn(NEW_MASK, after)
        self.assertIn(NEW_SEND, after)
        self.assertEqual(after.count("NEXIUM_MACOS_GUEST_AB_PROBE"), 2)

    def test_repeat_patch_is_idempotent(self):
        once = patch_source(self.source())
        self.assertEqual(patch_source(once), once)

    def test_missing_prior_stage40_source_is_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(self.source().replace("NEXIUM_MACOS_GUEST_HID_PROBE", ""))

    def test_missing_virtual_sdl_anchor_is_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(self.source().replace(OLD_MASK, ""))

    def test_partial_stage42_patch_is_rejected(self):
        with self.assertRaises(RuntimeError):
            patch_source(self.source().replace(OLD_MASK, NEW_MASK))


def fixture(root: Path):
    (root / "smoke_result.json").write_text(
        json.dumps({"status": "timeout_alive_unverified", "exit_code": None}),
        encoding="utf-8",
    )
    console = root / "nexium-console.log"
    console.write_text(
        "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE\n"
        "STAGE42_VIRTUAL_A_PRESS_SENT\n"
        "STAGE42_VIRTUAL_A_RELEASE_SENT\n"
        "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE\n",
        encoding="utf-8",
    )
    logger = root / "data-root" / "logs"
    logger.mkdir(parents=True)
    log = logger / "nexium-test.log"
    log.write_text(
        "Auto-loaded NRO: nexium-guest-ab-probe.nro\n"
        "Booting NRO: nexium-guest-ab-probe.nro\n"
        "cpu memory null policy: enabled\n"
        "svcMapSharedMemory handle=0x1 addr=0x1000 size=0x40000 perm=0x3\n"
        "recognized as HID shared memory\n"
        "svcOutputDebugString (X0=str_ptr, X1=str_len)\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "OutputDebugString: STAGE42_GUEST_AB_PROBE_START\n"
        "OutputDebugString: STAGE42_GUEST_B_ONLY_FIRST\n"
        "[hid-publish] npad=[0x3, 0x3]\n"
        "OutputDebugString: STAGE42_GUEST_A_AND_B\n"
        "[hid-publish] npad=[0x2, 0x2]\n"
        "OutputDebugString: STAGE42_GUEST_B_ONLY_AFTER_A\n"
        "[hid-publish] npad=[0x0, 0x0]\n"
        "OutputDebugString: STAGE42_GUEST_BOTH_RELEASED\n"
        "OutputDebugString: STAGE42_GUEST_AB_CHORD_PASS\n",
        encoding="utf-8",
    )
    return console, log


class Stage42AbGuestChordAuditTests(unittest.TestCase):
    def test_realistic_source_channels_pass(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            fixture(path)
            report = audit(path)
            self.assertTrue(report["same_process_guest_ab_chord_passed"])
            self.assertTrue(report["original_npad_b_ab_b_neutral_order_observed"])
            self.assertEqual(report["original_npad_serialized_sample_count"], 5)
            self.assertFalse(report["physical_controller_verified"])

    def test_guest_markers_only_in_console_cannot_fake_pass(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            console, log = fixture(path)
            data = log.read_text(encoding="utf-8")
            with console.open("a", encoding="utf-8") as stream:
                stream.write(data)
            log.write_text(data.replace("OutputDebugString: STAGE42_GUEST_A_AND_B", ""),
                           encoding="utf-8")
            self.assertFalse(audit(path)["same_process_guest_ab_chord_passed"])

    def test_missing_guest_boot_context_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            _, log = fixture(path)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "cpu memory null policy: enabled\n", ""), encoding="utf-8")
            self.assertFalse(audit(path)["same_process_guest_ab_chord_passed"])

    def test_missing_original_hid_map_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            _, log = fixture(path)
            log.write_text(log.read_text(encoding="utf-8").replace(
                "recognized as HID shared memory\n", ""), encoding="utf-8")
            self.assertFalse(audit(path)["same_process_guest_ab_chord_passed"])

    def test_guest_incomplete_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            _, log = fixture(path)
            with log.open("a", encoding="utf-8") as stream:
                stream.write("OutputDebugString: STAGE42_GUEST_AB_CHORD_INCOMPLETE\n")
            self.assertFalse(audit(path)["same_process_guest_ab_chord_passed"])

    def test_host_a_after_b_release_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            console, _ = fixture(path)
            console.write_text(
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE\n"
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE\n"
                "STAGE42_VIRTUAL_A_PRESS_SENT\n"
                "STAGE42_VIRTUAL_A_RELEASE_SENT\n", encoding="utf-8")
            self.assertFalse(audit(path)["same_process_guest_ab_chord_passed"])

    def test_wrong_serialized_npad_order_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            _, log = fixture(path)
            log.write_text(
                log.read_text(encoding="utf-8").replace(
                    "[hid-publish] npad=[0x3, 0x3]\n",
                    "[hid-publish] npad=[0x1, 0x1]\n",
                ), encoding="utf-8",
            )
            self.assertFalse(audit(path)["same_process_guest_ab_chord_passed"])

    def test_duplicate_guest_phase_cannot_skip_order(self):
        self.assertFalse(ordered("one two three", ("one", "three", "two")))

    def test_npad_state_machine(self):
        self.assertTrue(npad_chord_order([[0], [2], [3], [2], [0]]))
        self.assertFalse(npad_chord_order([[0], [2], [1], [3], [0]]))
        self.assertFalse(npad_chord_order([[0], [2], [3], [0]]))
        self.assertFalse(npad_chord_order([]))


if __name__ == "__main__":
    unittest.main()
