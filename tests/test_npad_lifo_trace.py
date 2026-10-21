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

    def test_stage40_guest_map_markers_are_sanitized_booleans(self):
        result = stage.analyze_console("\n".join([
            "STAGE40_SVC_MAP_SHARED_MEMORY_ENTER",
            "STAGE40_SVC_MAP_SIZE_MATCH_HID",
            "STAGE40_SVC_MAP_HANDLE_NONZERO",
            "STAGE40_HID_SHARED_MEMORY_HOST_BOUND",
            "STAGE40_HID_SHARED_MEMORY_CPU_MAP_OK",
        ]))
        self.assertTrue(result["stage40_svc_map_call_seen"])
        self.assertTrue(result["stage40_hid_size_match_seen"])
        self.assertTrue(result["stage40_map_handle_nonzero_seen"])
        self.assertTrue(result["stage40_hid_host_region_bound_seen"])
        self.assertTrue(result["stage40_cpu_map_success_seen"])
        self.assertFalse(result["stage40_unmap_noop_seen"])
        self.assertNotIn("0xDEADBEEF", str(result))

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
