"""Fail-closed synthetic tests for independent Intel eframe process receipts."""
import copy
import importlib.util
from pathlib import Path
import unittest

TARGET = Path(__file__).with_name("control_probe.py")
spec = importlib.util.spec_from_file_location("stage24_control_probe", TARGET)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def row(renderer: str) -> dict:
    return {
        "schema": "nexium-stage24-independent-eframe-process/v1",
        "renderer": renderer,
        "executable_sha256": "a" * 64,
        "expected_renderer_marker_observed": True,
        "other_renderer_marker_observed": False,
        "nro_supplied": False, "nintendo_resources_used": False,
        "gui_rendering_proven": False, "window_pixels_observed": False,
        "outcome": "exited_nonzero", "exit_code": -6, "exit_signal": "SIGABRT",
        "alive_at_deadline": False,
        "winit_reentrant_event_panic_observed": True,
        "panic_cannot_unwind_observed": True,
    }


class TestIndependentControl(unittest.TestCase):
    def test_detect_exact_marker_not_prefix(self):
        e = control.parse_evidence("STAGE24_CONTROL_RENDERER=wgpu\n", "wgpu")
        self.assertTrue(e["expected_renderer_marker_observed"])
        self.assertFalse(e["other_renderer_marker_observed"])
        self.assertFalse(control.parse_evidence("STAGE24_CONTROL_RENDERER=wgpu-corrupt\n", "wgpu")["expected_renderer_marker_observed"])

    def test_wrong_renderer_marker_detected(self):
        e = control.parse_evidence("STAGE24_CONTROL_RENDERER=glow\n", "wgpu")
        self.assertFalse(e["expected_renderer_marker_observed"])
        self.assertTrue(e["other_renderer_marker_observed"])

    def test_two_abort_observations_are_valid_not_success_claim(self):
        evidence = control.classify_pair(row("wgpu"), row("glow"))
        self.assertEqual(evidence["result"], "TWO_REAL_RENDERER_STARTUPS_CLASSIFIED")
        self.assertEqual(evidence["wgpu"]["exit_signal"], "SIGABRT")
        self.assertFalse(evidence["gui_rendering_proven"])

    def test_survival_not_graphics_proof(self):
        w = row("wgpu")
        w.update(outcome="alive_without_graphical_verification", alive_at_deadline=True,
                 exit_code=None, exit_signal=None)
        evidence = control.classify_pair(w, row("glow"))
        self.assertFalse(evidence["gui_rendering_proven"])

    def test_executable_mismatch_rejected(self):
        w = row("wgpu")
        w["executable_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "same Intel"):
            control.classify_pair(w, row("glow"))

    def test_missing_actual_marker_rejected(self):
        w = row("wgpu")
        w["expected_renderer_marker_observed"] = False
        with self.assertRaisesRegex(ValueError, "expected code"):
            control.classify_pair(w, row("glow"))

    def test_unverified_window_assertion_rejected(self):
        w = row("wgpu")
        w["gui_rendering_proven"] = True
        with self.assertRaisesRegex(ValueError, "graphics assertion"):
            control.classify_pair(w, row("glow"))

    def test_unexpected_private_asset_rejected(self):
        w = row("wgpu")
        w["nro_supplied"] = True
        with self.assertRaisesRegex(ValueError, "proprietary"):
            control.classify_pair(w, row("glow"))

    def test_invalid_outcome_rejected(self):
        w = row("wgpu")
        w["outcome"] = "not_started"
        with self.assertRaisesRegex(ValueError, "genuine process"):
            control.classify_pair(w, row("glow"))


if __name__ == "__main__":
    unittest.main()
