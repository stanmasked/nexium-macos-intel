"""Guarded macOS audio ablation must be idempotent and atomic on drift."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_macos_audio_ablation.py"
MAIN = '''    audio::init_host_audio(
        settings.audio_output_device.as_deref(),
        settings.audio_volume,
    );'''
APP = '''        crate::ui_audio::init(app_settings.audio_output_device.as_deref());'''


class AudioAblationTests(unittest.TestCase):
    def root(self, parent):
        root = Path(parent)
        main = root / "nexium-gui/src/main.rs"
        app = root / "nexium-gui/src/app.rs"
        main.parent.mkdir(parents=True)
        main.write_text(MAIN, encoding="utf-8")
        app.write_text(APP, encoding="utf-8")
        return main, app

    def test_opt_in_applies_idempotently_with_both_initializers(self):
        with tempfile.TemporaryDirectory() as temp:
            main, app = self.root(temp)
            args = [sys.executable, str(SCRIPT), temp]
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertIn("NEXIUM_MACOS_NO_AUDIO", main.read_text())
            self.assertIn("NEXIUM_MACOS_NO_AUDIO", app.read_text())
            self.assertIn("cfg!(target_os = \"macos\")", main.read_text())
            self.assertIn("cfg!(target_os = \"macos\")", app.read_text())
            snapshots = (main.read_bytes(), app.read_bytes())
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertEqual(snapshots, (main.read_bytes(), app.read_bytes()))

    def test_drift_rejects_both_without_partial_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            main, app = self.root(temp)
            app.write_text("unknown upstream audio code")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), temp], capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(main.read_text(), MAIN)
            self.assertEqual(app.read_text(), "unknown upstream audio code")


if __name__ == "__main__":
    unittest.main()
