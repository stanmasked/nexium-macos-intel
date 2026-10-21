"""Fail-closed synthetic regression suite for Stage39 native receipt auditor."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_sdl3_cutpoints as stage

DIGEST = "b" * 64

def receipt(alive, window=False):
    return {
        "probe": "no_nro_gui_process_only",
        "emulator_sha256": DIGEST,
        "duration_limit_seconds": 12,
        "outcome": "alive_without_gui_verification" if alive else "exited_nonzero",
        "exit_signal": None if alive else "SIGABRT",
        "alive_at_deadline": alive,
        "window_found": window,
        "window_probe": "own_visible_window_observed" if window else "not_requested",
        "nro_verified": False,
        "gameplay_verified": False,
        "gui_verified": False,
        "diagnostic_messages": ["PRIVATE DATA MUST NOT LEAK"],
    }

def markers(name):
    if name == "no-input":
        return "STAGE29_SDL3_INPUT_SKIPPED\n"
    prefix = "STAGE29_SDL3_INPUT_ENABLED\n"
    if name == "full":
        return prefix + "".join("STAGE38_SDL3_INPUT_" + p + "\n" for p in stage.PHASES)
    pos = stage.CUTS.index(name.removeprefix("before-"))
    return (
        prefix
        + "".join("STAGE38_SDL3_INPUT_" + p + "\n" for p in stage.PHASES[:pos+1])
        + "STAGE39_SDL3_STOP_BEFORE_" + stage.CUTS[pos].upper() + "\n"
    )

class Stage39AuditTests(unittest.TestCase):
    def test_one_enabled_partial_initializer(self):
        row = stage.classify("before-gamepad", receipt(True, True), markers("before-gamepad"))
        self.assertEqual(row["observed_ordered_input_phases"], list(stage.PHASES[:3]))
        self.assertTrue(row["cutpoint_reached"])

    def test_actual_full_crash_remains_negative_evidence(self):
        row = stage.classify("full", receipt(False), markers("full") + stage.PANIC_TEXT)
        self.assertEqual(row["exit_signal"], "SIGABRT")
        self.assertTrue(row["winit_reentrant_panic_observed"])

    def test_wrong_binary_hash_fails(self):
        wrong = receipt(True, True)
        wrong["emulator_sha256"] = "bogus"
        with self.assertRaisesRegex(ValueError, "digest"):
            stage.classify("no-input", wrong, markers("no-input"))

    def test_game_claim_rejected(self):
        row = receipt(True, True)
        row["gameplay_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsupported"):
            stage.classify("no-input", row, markers("no-input"))

    def test_missing_negative_control_window_rejected(self):
        with self.assertRaisesRegex(ValueError, "negative control"):
            stage.classify("no-input", receipt(True), markers("no-input"))

    def test_duplicate_phase_marker_rejected(self):
        log = markers("full") + "STAGE38_SDL3_INPUT_04_BEFORE_INPUT_STRUCT\n"
        with self.assertRaisesRegex(ValueError, "phase"):
            stage.classify("full", receipt(False), log)

    def test_skipped_input_must_not_have_subphases(self):
        log = markers("no-input") + "STAGE38_SDL3_INPUT_00_ENTRY\n"
        with self.assertRaisesRegex(ValueError, "bypass"):
            stage.classify("no-input", receipt(True, True), log)

    def test_cutpoint_cannot_be_different_than_requested(self):
        log = markers("before-init").replace("STOP_BEFORE_INIT", "STOP_BEFORE_RUMBLE")
        with self.assertRaisesRegex(ValueError, "cutpoint"):
            stage.classify("before-init", receipt(True, True), log)

    def test_alive_without_source_emitted_cutpoint_rejected(self):
        log = markers("before-init").replace("STAGE39_SDL3_STOP_BEFORE_INIT\n", "")
        with self.assertRaisesRegex(ValueError, "never reached"):
            stage.classify("before-init", receipt(True, True), log)

    def test_trace_cannot_pass_requested_cutpoint(self):
        log = markers("before-hints").replace(
            "STAGE39_SDL3_STOP_BEFORE_HINTS\n",
            "STAGE38_SDL3_INPUT_01_BEFORE_SDL_INIT\nSTAGE39_SDL3_STOP_BEFORE_HINTS\n"
        )
        with self.assertRaisesRegex(ValueError, "passed"):
            stage.classify("before-hints", receipt(False), log)

    def test_inconsistent_process_status_rejected(self):
        bad = receipt(False)
        bad["alive_at_deadline"] = True
        with self.assertRaisesRegex(ValueError, "outcome"):
            stage.classify("full", bad, markers("full"))

    def test_panic_or_private_messages_not_leaked(self):
        row = stage.classify(
            "full", receipt(False),
            markers("full") + "\nPRIVATE SECRET\n" + stage.PANIC_TEXT
        )
        self.assertTrue(row["winit_reentrant_panic_observed"])
        self.assertNotIn("PRIVATE", repr(row))
        self.assertNotIn(stage.PANIC_TEXT, repr(row))

    def test_synthetic_complete_seven_process_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in stage.MODES:
                sub = root / name
                sub.mkdir()
                alive = name != "full"
                data = receipt(alive, alive)
                (sub / "gui_process_probe.json").write_text(__import__("json").dumps(data))
                (sub / "nexium-stdout-stderr.log").write_text(markers(name))
            result = stage.audit(root)
            self.assertEqual(result["real_process_count"], 7)
            self.assertEqual(result["single_native_x86_64_macho_sha256"], DIGEST)
            self.assertNotIn("PRIVATE DATA", repr(result))
            changed = __import__("json").loads(
                (root / "before-gamepad/gui_process_probe.json").read_text()
            )
            changed["emulator_sha256"] = "c" * 64
            (root / "before-gamepad/gui_process_probe.json").write_text(
                __import__("json").dumps(changed)
            )
            with self.assertRaisesRegex(ValueError, "mismatched"):
                stage.audit(root)

if __name__ == "__main__":
    unittest.main()
