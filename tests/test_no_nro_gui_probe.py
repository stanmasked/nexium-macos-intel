"""No-NRO process-start diagnostics using synthetic sh executables, not NeXium."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import Mock, patch
import signal

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

    def test_panic_cause_extraction_removes_absolute_source_path(self):
        lines = [
            "thread 'main' panicked at /Users/runner/.cargo/registry/src/eframe.rs:123:21:",
            "Unable to select a compatible graphics adapter",
            "stack backtrace:",
            "0: core::panicking::panic_fmt"
        ]
        excerpt = module.panic_reason_excerpt(lines)
        self.assertIn("Unable to select a compatible graphics adapter", excerpt)
        self.assertNotIn("/Users/runner", str(excerpt))

    def test_private_internal_logs_are_counted_without_exposing_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            logdir = out / "private-neXium-data" / "logs"
            logdir.mkdir(parents=True)
            (logdir / "nexium-2026-test.log").write_text(
                "ERROR wgpu adapter /Users/private-person/secret.nro\n"
                "WARN Metal device /Users/private-person/key.txt\n"
                "normal line\n"
            )
            summary = module.collect_private_log_signals(out)
            self.assertEqual(len(summary["log_files"]), 1)
            self.assertEqual(summary["keyword_counts"]["error"], 1)
            self.assertEqual(summary["keyword_counts"]["warn"], 1)
            self.assertNotIn("private-person", str(summary))
            self.assertNotIn("secret.nro", str(summary))

    def test_hosted_macos_killpg_permission_error_does_not_relabel_gui_failure(self):
        process = Mock()
        process.pid = 12345
        process.poll.return_value = None
        with patch.object(module.os, "killpg", side_effect=PermissionError):
            self.assertEqual(
                module.stop_group(process, signal.SIGTERM),
                "direct_child_signalled",
            )
        process.send_signal.assert_called_once_with(signal.SIGTERM)

    def test_unavailable_signal_does_not_crash_diagnostic(self):
        process = Mock()
        process.pid = 12345
        process.poll.return_value = None
        process.send_signal.side_effect = PermissionError
        with patch.object(module.os, "killpg", side_effect=PermissionError):
            self.assertEqual(
                module.stop_group(process, signal.SIGTERM),
                "process_signal_denied",
            )

    def test_immediate_nonzero_exit_is_not_success(self):
        result = self.run_case("exit 12")
        self.assertEqual(result["outcome"], "exited_nonzero")
        self.assertEqual(result["exit_code"], 12)
        self.assertFalse(result["alive_at_deadline"])

    def test_clean_exit_remains_unverified(self):
        result = self.run_case("exit 0")
        self.assertEqual(result["outcome"], "exited_zero_unverified")
        self.assertEqual(result["exit_code"], 0)

    def test_mock_owned_window_is_not_treated_as_rendered_game(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "synthetic-exe"
            exe.write_text("#!/bin/sh\nsleep 3\n")
            exe.chmod(0o755)
            helper = root / "fake-window-id"
            helper.write_text("#!/bin/sh\necho 124\n")
            helper.chmod(0o755)
            result = module.probe(exe, root / "out", 1, helper)
            self.assertTrue(result["window_found"])
            self.assertEqual(result["window_id"], 124)
            self.assertEqual(result["window_probe"], "own_visible_window_observed")
            self.assertFalse(result["gui_verified"])
            self.assertFalse(result["nro_verified"])

    def test_failed_window_enumeration_is_not_rendering_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "synthetic-exe"
            exe.write_text("#!/bin/sh\nsleep 3\n")
            exe.chmod(0o755)
            helper = root / "fake-window-id"
            helper.write_text("#!/bin/sh\necho window-unavailable >&2\nexit 4\n")
            helper.chmod(0o755)
            result = module.probe(exe, root / "out", 1, helper)
            self.assertFalse(result["window_found"])
            self.assertEqual(result["window_probe"], "no_visible_window_identified")
            self.assertTrue(result["alive_at_deadline"])

    def test_alive_process_remains_unverified_and_is_terminated(self):
        result = self.run_case("sleep 3", seconds=1)
        self.assertEqual(result["outcome"], "alive_without_gui_verification")
        self.assertTrue(result["alive_at_deadline"])


if __name__ == "__main__":
    unittest.main()
