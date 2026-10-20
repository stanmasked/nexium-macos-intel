"""No-NRO process-start diagnostics using synthetic sh executables, not NeXium."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/no_nro_gui_probe.py"
spec = importlib.util.spec_from_file_location("intel_gui_probe", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProcessProbeTests(unittest.TestCase):
    def run_case(self, body: str, seconds: int = 1):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / "synthetic-exe"
            fake.write_text("#!/bin/sh\n" + body + "\n")
            fake.chmod(0o755)
            evidence = root / "out"
            report = module.probe(fake, evidence, seconds)
            self.assertFalse(report["gui_verified"])
            self.assertFalse(report["nro_verified"])
            self.assertFalse(report["gameplay_verified"])
            self.assertEqual(len(report["emulator_sha256"]), 64)
            self.assertTrue((evidence / "gui_process_probe.json").is_file())
            self.assertTrue((evidence / "nexium-stdout-stderr.log").is_file())
            return report

    def test_immediate_nonzero_exit_is_not_success(self):
        result = self.run_case("exit 12")
        self.assertEqual(result["outcome"], "exited_nonzero")
        self.assertEqual(result["exit_code"], 12)
        self.assertFalse(result["alive_at_deadline"])

    def test_clean_exit_remains_unverified(self):
        result = self.run_case("exit 0")
        self.assertEqual(result["outcome"], "exited_zero_unverified")
        self.assertEqual(result["exit_code"], 0)

    def test_alive_process_remains_unverified_and_is_terminated(self):
        result = self.run_case("sleep 3", seconds=1)
        self.assertEqual(result["outcome"], "alive_without_gui_verification")
        self.assertTrue(result["alive_at_deadline"])


if __name__ == "__main__":
    unittest.main()
