"""Stage34 classifier is deliberately diagnostic and fail-closed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

script = Path(__file__).with_name("classify_backend_selection.py")
spec = importlib.util.spec_from_file_location("classify_backend_selection", script)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def trial():
    return {
        "nro_file": "nexium_clean_smoke.nro",
        "nro_sha256": m.EXPECTED_PUBLIC_NRO,
        "emulator_sha256": "a" * 64,
        "status": "timeout_alive_unverified",
        "gameplay_verified": False,
        "snapshots": [], "unique_frame_hashes": 0,
    }

class ClassifierTests(unittest.TestCase):
    def test_genuine_comparison_never_marks_guest_executed(self):
        d, r = trial(), trial()
        result = m.classify(d, r, {"sha256": m.EXPECTED_PUBLIC_NRO},
                            {"dynarmic_unavailable": True},
                            {"dynarmic_unavailable": False,
                             "guest_boot_thread_entered": True})
        self.assertTrue(result["cpu_selection_fault_isolated"])
        self.assertFalse(result["actual_guest_instructions_verified"])
        self.assertFalse(result["gameplay_verified"])
        self.assertEqual(result["variants"]["forced_rustarmic"]["snapshots_observed"], 0)

    def test_different_compiled_emulator_rejected(self):
        d, r = trial(), trial()
        r["emulator_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "same emulator"):
            m.classify(d, r, {"sha256": m.EXPECTED_PUBLIC_NRO}, {}, {})

    def test_wrong_public_nro_rejected(self):
        d, r = trial(), trial()
        with self.assertRaisesRegex(ValueError, "unexpected public"):
            m.classify(d, r, {"sha256": "b" * 64}, {}, {})

    def test_private_or_other_nro_rejected(self):
        d, r = trial(), trial()
        r["nro_file"] = "private.nro"
        with self.assertRaisesRegex(ValueError, "approved clean"):
            m.classify(d, r, {"sha256": m.EXPECTED_PUBLIC_NRO}, {}, {})

    def test_claimed_gameplay_rejected(self):
        d, r = trial(), trial()
        r["gameplay_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsafe gameplay"):
            m.classify(d, r, {"sha256": m.EXPECTED_PUBLIC_NRO}, {}, {})

    def test_no_logs_are_invented(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(m.scan_local_logs(Path(d)),
                             {name: False for name in m.MARKERS})

    def test_markers_scoped_to_isolated_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "nexium-console.log").write_text(
                "Booting NRO:\nDynarmic backend not compiled in\n")
            result = m.scan_local_logs(root)
            self.assertTrue(result["dynarmic_unavailable"])
            self.assertTrue(result["guest_boot_thread_entered"])
            self.assertFalse(result["rustarmic_unavailable"])

    def test_nonnumeric_flags_rejected(self):
        d, r = trial(), trial()
        with self.assertRaisesRegex(ValueError, "booleans"):
            m.classify(d, r, {"sha256": m.EXPECTED_PUBLIC_NRO},
                       {"dynarmic_unavailable": "yes"}, {})

if __name__ == "__main__":
    unittest.main()
