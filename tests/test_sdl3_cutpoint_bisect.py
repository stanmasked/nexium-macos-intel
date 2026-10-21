"""Stage39 cutpoint patch tests, using Stage38's exact source-anchored fixture."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_sdl3_subphase_trace as previous
import apply_macos_sdl3_cutpoint_bisect as stage

PLAIN = (
    "impl InputBackend {\n" + previous.START + "\n"
    + "\n".join(anchor for _, anchor in previous.PHASES) + "\n"
    + "        Some(Self { /* fixture */ })\n    }\n"
    + previous.END + "\n}\n"
)
TRACED = previous.patch_source(PLAIN)

class CutpointTests(unittest.TestCase):
    def test_requires_stage38_trace(self):
        with self.assertRaisesRegex(ValueError, "Stage38"):
            stage.patch_source(PLAIN)

    def test_all_five_cutpoints_ordered_and_exactly_once(self):
        out = stage.patch_source(TRACED)
        indexes = [out.index(stage.PREFIX + name.upper()) for name, _ in stage.CHOICES]
        self.assertEqual(indexes, sorted(indexes))
        self.assertEqual(out.count(stage.PREFIX), 5)

    def test_every_sdl_call_preserved(self):
        out = stage.patch_source(TRACED)
        for name, anchor in stage.CHOICES:
            self.assertEqual(out.count(anchor), 1)
            self.assertIn(stage.guard(name), out)
        self.assertIn('Some(Self { /* fixture */ })', out)
        self.assertEqual(out.count('return None;'), 5)

    def test_non_macos_no_behavior_change(self):
        out = stage.patch_source(TRACED)
        self.assertEqual(out.count('#[cfg(target_os = "macos")]'), 10)
        self.assertEqual(out.count('NEXIUM_MACOS_SDL3_STOP_BEFORE'), 5)

    def test_idempotent(self):
        once = stage.patch_source(TRACED)
        self.assertEqual(stage.patch_source(once), once)

    def test_modified_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, "order"):
            stage.patch_source(TRACED.replace(stage.CHOICES[2][1], "other()"))

    def test_reordered_anchors_rejected(self):
        a, b = stage.CHOICES[1][1], stage.CHOICES[2][1]
        bad = TRACED.replace(a, "TEMP").replace(b, a).replace("TEMP", b)
        with self.assertRaisesRegex(ValueError, "order"):
            stage.patch_source(bad)

    def test_duplicate_anchor_rejected(self):
        anchor = stage.CHOICES[3][1]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            stage.patch_source(TRACED.replace(anchor, anchor + "\n" + anchor))

    def test_partial_instrumentation_rejected(self):
        with self.assertRaisesRegex(ValueError, "partial"):
            stage.patch_source(TRACED + stage.PREFIX + "HINTS")

    def test_file_write_and_failure_does_not_corrupt_source(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "nexium-gui/src/input.rs"
            target.parent.mkdir(parents=True)
            target.write_text(TRACED)
            self.assertEqual(stage.main([temp]), 0)
            first = target.read_text()
            self.assertEqual(stage.main([temp]), 0)
            self.assertEqual(target.read_text(), first)
            invalid = TRACED.replace(stage.CHOICES[0][1], "source-drift()")
            target.write_text(invalid)
            self.assertEqual(stage.main([temp]), 2)
            self.assertEqual(target.read_text(), invalid)

if __name__ == "__main__":
    unittest.main()
