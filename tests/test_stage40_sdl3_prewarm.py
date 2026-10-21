"""Stage40 guarded source patches must preserve controller initialization."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_sdl3_prewarm as stage

MAIN = '''mod input;
use app_settings::AppSettings;
fn main() -> Result<(), eframe::Error> {
    let settings = AppSettings::load();
    let result = eframe::run_native(
        "NeXium", options, Box::new(move |cc| { todo!() })
    );
    result
}
'''
APP = '''impl HorizonApp {
    pub fn new(...) -> Self {
        let stage29_skip_sdl3_input = false;
        let input = if stage29_skip_sdl3_input {
            eprintln!("STAGE29_SDL3_INPUT_SKIPPED");
            None
        } else {
            eprintln!("STAGE29_SDL3_INPUT_ENABLED");
            InputBackend::new(app_settings.motion_enabled, gamepad).or_else(|| {
                log::warn!("SDL3 gamepad init failed");
                None
            })
        };
    }
}
'''


class PrewarmPatchTests(unittest.TestCase):
    def test_main_places_preinit_before_eframe(self):
        patched = stage.patch_main(MAIN)
        self.assertLess(patched.index(stage.MAIN_SLOT), patched.index(stage.MAIN_CALL))
        self.assertIn("input::InputBackend::new(", patched)
        self.assertIn("STAGE40_PREWARM_MAIN_READY", patched)

    def test_main_same_thread_non_send_storage(self):
        patched = stage.patch_main(MAIN)
        self.assertIn("thread_local!", patched)
        self.assertIn("RefCell<Option<input::InputBackend>>", patched)
        self.assertNotIn("unsafe ", patched)
        self.assertNotIn("Arc<", patched)

    def test_main_prewarms_only_on_macos_opt_in_not_bypass(self):
        patched = stage.patch_main(MAIN)
        self.assertIn('#[cfg(target_os = "macos")]', patched)
        self.assertIn("NEXIUM_MACOS_PREWARM_SDL3_INPUT", patched)
        self.assertIn("NEXIUM_MACOS_SKIP_SDL3_INPUT", patched)

    def test_app_consumes_without_second_init(self):
        patched = stage.patch_app(APP)
        self.assertIn("crate::stage40_take_prewarmed_input()", patched)
        self.assertIn("STAGE40_PREWARM_CONSTRUCTOR_CONSUMED", patched)
        self.assertIn("STAGE40_PREWARM_CONSTRUCTOR_MISSING", patched)
        self.assertIn("stage40_input.or_else(|| {", patched)
        self.assertEqual(patched.count("InputBackend::new(app_settings.motion_enabled, gamepad)"), 2)
        # two copies are mutually exclusive: one for non-prewarm macOS,
        # one for non-macOS target.
        self.assertIn('#[cfg(not(target_os = "macos"))]', patched)
        self.assertNotIn("unsafe ", patched)

    def test_app_needs_original_stage29_gate(self):
        with self.assertRaisesRegex(ValueError, "Stage29"):
            stage.patch_app(APP.replace("STAGE29_SDL3_INPUT_ENABLED", "other"))

    def test_main_rejects_duplicate_anchor(self):
        with self.assertRaisesRegex(ValueError, "anchors"):
            stage.patch_main(MAIN + stage.MAIN_CALL)

    def test_app_rejects_duplicate_source_initializer(self):
        with self.assertRaisesRegex(ValueError, "initializer"):
            stage.patch_app(APP + stage.APP_CALL)

    def test_main_idempotent(self):
        once = stage.patch_main(MAIN)
        self.assertEqual(stage.patch_main(once), once)

    def test_app_idempotent(self):
        once = stage.patch_app(APP)
        self.assertEqual(stage.patch_app(once), once)

    def test_partial_patch_rejected(self):
        with self.assertRaisesRegex(ValueError, "partial"):
            stage.patch_main(MAIN + stage.MAIN_SLOT)
        with self.assertRaisesRegex(ValueError, "partial"):
            stage.patch_app(APP + stage.APP_SLOT)

    def test_unchanged_on_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nexium-gui/src"
            root.mkdir(parents=True)
            (root / "main.rs").write_text(MAIN)
            invalid = APP.replace("STAGE29_SDL3_INPUT_ENABLED", "other")
            (root / "app.rs").write_text(invalid)
            self.assertEqual(stage.main([tmp]), 2)
            self.assertEqual((root / "main.rs").read_text(), MAIN)
            self.assertEqual((root / "app.rs").read_text(), invalid)

    def test_dual_source_patch_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nexium-gui/src"
            root.mkdir(parents=True)
            (root / "main.rs").write_text(MAIN)
            (root / "app.rs").write_text(APP)
            self.assertEqual(stage.main([tmp]), 0)
            first = (root / "main.rs").read_text(), (root / "app.rs").read_text()
            self.assertEqual(stage.main([tmp]), 0)
            self.assertEqual(first, ((root / "main.rs").read_text(), (root / "app.rs").read_text()))

if __name__ == "__main__":
    unittest.main()
