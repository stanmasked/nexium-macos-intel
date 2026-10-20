"""Stage28 guarded macOS input ablation: fail-closed, idempotent fixtures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_macos_input_ablation.py"
spec = importlib.util.spec_from_file_location("stage28_input", SCRIPT)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class SDLInputIsolationTests(unittest.TestCase):
    def test_opt_in_only_and_default_input_preserved(self):
        updated = stage.patch_source("before\n" + stage.ORIGINAL + "\nafter")
        self.assertIn('cfg!(target_os = "macos")', updated)
        self.assertIn('NEXIUM_MACOS_SKIP_SDL_INPUT', updated)
        self.assertIn("STAGE28_SDL_INPUT_INITIALIZING", updated)
        self.assertIn("InputBackend::new(app_settings.motion_enabled, gamepad)", updated)
        self.assertIn("None", updated)
        self.assertIn("before\n", updated)
        self.assertIn("\nafter", updated)

    def test_idempotent(self):
        once = stage.patch_source(stage.ORIGINAL)
        self.assertEqual(once, stage.patch_source(once))

    def test_missing_anchor_fails_without_editing(self):
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            stage.patch_source("pub fn new() {}")

    def test_duplicate_anchor_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            stage.patch_source(stage.ORIGINAL + "\n" + stage.ORIGINAL)

    def test_partial_patch_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "partially applied"):
            stage.patch_source(stage.ORIGINAL + "\n" + stage.MARKER)

    def test_apply_changes_only_app_rs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "nexium-gui/src/app.rs"
            path.parent.mkdir(parents=True)
            path.write_text(stage.ORIGINAL, encoding="utf-8")
            other = root / "nexium-gui/src/main.rs"
            other.write_text("unchanged", encoding="utf-8")
            self.assertTrue(stage.apply(root))
            self.assertFalse(stage.apply(root))
            self.assertEqual(path.read_text(), stage.REPLACEMENT)
            self.assertEqual(other.read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
