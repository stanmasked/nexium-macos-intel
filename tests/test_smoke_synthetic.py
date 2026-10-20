"""Synthetic tests for the local NRO smoke reporter (NOT tests of NeXium)."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/nro_smoke_test.py"


class ReporterTests(unittest.TestCase):
    def run_case(self, shell: str, seconds: int = 2):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "mock_emulator"
            exe.write_text("#!/bin/sh\n" + shell + "\n")
            exe.chmod(0o755)
            nro = root / "synthetic.nro"
            nro.write_bytes(b"Synthetic test input, not a real NRO.")
            out = root / "result"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--allow-nonmac-test",
                 "--exe", str(exe), "--nro", str(nro),
                 "--output", str(out), "--seconds", str(seconds)],
                capture_output=True, text=True, timeout=seconds + 12,
            )
            report = json.loads((out / "smoke_result.json").read_text())
            self.assertFalse(report["gameplay_verified"])
            self.assertEqual(report["unique_frame_hashes"], 0)
            self.assertIn("sha256", json.dumps(report))
            self.assertTrue((out / "nexium-console.log").is_file())
            return proc.returncode, report

    def test_zero_exit_is_not_certified(self):
        code, report = self.run_case("exit 0")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "exited_zero_unverified")

    def test_nonzero_exit_is_reported(self):
        code, report = self.run_case("exit 3")
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "exited_nonzero")
        self.assertEqual(report["exit_code"], 3)

    def test_hung_process_is_not_certified(self):
        code, report = self.run_case("sleep 10", seconds=1)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "timeout_alive_unverified")


if __name__ == "__main__":
    unittest.main()
