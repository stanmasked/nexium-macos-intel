"""Stage38 parser and no-NRO source-bound report regression tests."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_npad_lifo_trace as stage


def sample(buttons):
    return "[hid-publish] sample=9 entry=0 requested=0x2 injected=None npad=[" + buttons + "] mouse=0x0 mapped=0xDEADBEEF"


def make_root(root, full=None, no_virtual="", ctor=None, digest="a" * 64):
    modes = {
        "full-virtual": full if full is not None else "\n".join([
            "STAGE36_VIRTUAL_ATTACHED_AND_OPENED",
            sample("0, 2, 2, 2, 2, 2"),
            "STAGE36_VIRTUAL_SNAPSHOT_PRESS_MAPPED",
            "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
            sample("0, 0, 0, 0, 0, 0"),
            "STAGE36_VIRTUAL_SNAPSHOT_RELEASE_MAPPED",
            "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
        ]),
        "full-no-virtual": no_virtual,
        "ctor-virtual": ctor if ctor is not None else "STAGE36_VIRTUAL_ATTACHED_AND_OPENED",
    }
    for mode, console in modes.items():
        path = root / mode
        path.mkdir(parents=True)
        (path / "gui_process_probe.json").write_text(json.dumps({
            "probe": "no_nro_gui_process_only",
            "emulator_sha256": digest,
            "outcome": "alive_without_gui_verification",
            "alive_at_deadline": True,
            "window_found": True,
            "gui_verified": False,
            "nro_verified": False,
            "gameplay_verified": False,
        }))
        (path / "nexium-stdout-stderr.log").write_text(console)


class Stage38NpadLifoTests(unittest.TestCase):
    def test_parses_realistic_hexadecimal_npad_words(self):
        self.assertEqual(stage.parse_npad_samples(sample("0, 2, a, 10, 0, 2")), [[0, 2, 10, 16, 0, 2]])

    def test_press_then_release_round_trip(self):
        result = stage.analyze_console("\n".join([
            sample("0, 2, 2, 2, 2, 2"),
            sample("0, 0, 0, 0, 0, 0"),
        ]))
        self.assertEqual(result["serialized_npad_b_press_sample_count"], 1)
        self.assertTrue(result["serialized_npad_b_release_after_press"])

    def test_release_before_press_does_not_count(self):
        result = stage.analyze_console("\n".join([
            sample("0, 0, 0, 0, 0, 0"),
            sample("0, 2, 2, 2, 2, 2"),
        ]))
        self.assertFalse(result["serialized_npad_b_release_after_press"])

    def test_malformed_trace_is_ignored(self):
        self.assertEqual(stage.parse_npad_samples("[hid-publish] npad=[bad, words]"), [])

    def test_audit_classifies_full_synthetic_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root)
            result = stage.audit(root)
            self.assertTrue(result["source_bound_synthetic_b_serialized_npad_lifo_round_trip_positive"])
            self.assertFalse(result["guest_npad_shared_memory_verified"])
            self.assertFalse(result["nintendo_game_nro_supplied"])

    def test_no_guest_tick_without_nro_is_classified_not_claimed_as_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root, full="\n".join([
                "STAGE36_VIRTUAL_SNAPSHOT_PRESS_MAPPED",
                "STAGE36_VIRTUAL_SNAPSHOT_RELEASE_MAPPED",
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
            ]))
            result = stage.audit(root)
            self.assertEqual(result["result"], "NO_NPAD_TICK_OBSERVED_NO_NRO")
            self.assertFalse(result["hid_publish_samples_observed_any_mode"])
            self.assertFalse(result["source_bound_synthetic_b_serialized_npad_lifo_round_trip_positive"])
            self.assertFalse(result["nintendo_game_nro_supplied"])

    def test_guest_tick_without_round_trip_remains_unconfirmed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root, full="\n".join([
                "STAGE36_VIRTUAL_SNAPSHOT_PRESS_MAPPED",
                "STAGE36_VIRTUAL_SNAPSHOT_RELEASE_MAPPED",
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
                sample("0, 0, 0, 0, 0, 0"),
            ]))
            result = stage.audit(root)
            self.assertEqual(result["result"], "NPAD_LIFO_TRACE_OBSERVED_B_ROUND_TRIP_NOT_CONFIRMED")
            self.assertTrue(result["hid_publish_samples_observed_any_mode"])
            self.assertFalse(result["source_bound_synthetic_b_serialized_npad_lifo_round_trip_positive"])

    def test_audit_fails_closed_without_serialized_press(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root, full="\n".join([
                "STAGE36_VIRTUAL_SNAPSHOT_PRESS_MAPPED",
                "STAGE36_VIRTUAL_SNAPSHOT_RELEASE_MAPPED",
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE",
                "STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE",
                sample("0, 0, 0, 0, 0, 0"),
            ]))
            self.assertFalse(stage.audit(root)["source_bound_synthetic_b_serialized_npad_lifo_round_trip_positive"])

    def test_no_virtual_control_rejects_synthetic_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root, no_virtual="STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE")
            with self.assertRaisesRegex(ValueError, "no-virtual negative control"):
                stage.audit(root)

    def test_inert_constructor_must_not_publish_b(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root, ctor="\n".join([
                "STAGE36_VIRTUAL_ATTACHED_AND_OPENED",
                sample("0, 2, 2, 2, 2, 2"),
            ]))
            with self.assertRaisesRegex(ValueError, "inert constructor"):
                stage.audit(root)

    def test_requires_same_binary_across_modes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root)
            p = root / "full-no-virtual" / "gui_process_probe.json"
            d = json.loads(p.read_text())
            d["emulator_sha256"] = "b" * 64
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError, "same compiled"):
                stage.audit(root)

    def test_requires_no_nro_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root)
            p = root / "full-virtual" / "gui_process_probe.json"
            d = json.loads(p.read_text())
            d["nro_verified"] = True
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError, "no-NRO"):
                stage.audit(root)

    def test_report_contains_no_raw_trace_or_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_root(root)
            result = stage.audit(root)
            encoded = json.dumps(result)
            self.assertNotIn("DEADBEEF", encoded)
            self.assertNotIn("mapped=0x", encoded)
            self.assertFalse(result["raw_console_uploaded"])


if __name__ == "__main__":
    unittest.main()
