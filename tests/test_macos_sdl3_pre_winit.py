"""Stage32: source-bound regression checks for pre-winit SDL3 controller preservation."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_sdl3_pre_winit as stage


def fixture():
    return {
        "nexium-gui/src/main.rs":(
            "fn main() {\n    let options = eframe::NativeOptions::default();\n"
            "    let settings = AppSettings::load();\n"
            +stage.MAIN_ANCHOR+
            '    let result = eframe::run_native("NeXium", options, creator);\n}\n'),
        "nexium-gui/src/app.rs":(
            "impl HorizonApp {\n"
            "    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {\n"
            +stage.APP_ORIGINAL+"\n"
            "    }\n}\n"),
        "nexium-gui/src/input.rs":(
            "pub struct InputBackend { sdl: sdl3::Sdl }\n"
            +stage.INPUT_ANCHOR+
            "    pub fn new(motion_enabled: bool, preferred: Option<String>) -> Option<Self> {\n"
            "        let sdl = sdl3::init().ok()?;\n"
            "        Some(Self {sdl})\n"
            "    }\n}\n"),
    }


class Stage32PreWinitInputTests(unittest.TestCase):
    def test_app_has_true_prebuilt_input_and_original_fallback(self):
        result=stage.patch_triplet(fixture())
        app=result["nexium-gui/src/app.rs"]
        self.assertIn("stage32_take_preinitialized_input()",app)
        self.assertIn("InputBackend::new(app_settings.motion_enabled, gamepad)",app)
        self.assertIn("STAGE29_SDL3_INPUT_SKIPPED",app)
        self.assertIn("STAGE32_TAKE_SOME",app)
        self.assertIn("STAGE32_TAKE_NONE",app)

    def test_early_controller_initialization_occurs_before_winit(self):
        main=stage.patch_triplet(fixture())["nexium-gui/src/main.rs"]
        self.assertLess(main.index("STAGE32_PREINPUT_BEGIN_BEFORE_WINIT"),
                        main.index("eframe::run_native"))
        self.assertIn("settings.gamepad.clone()",main)
        self.assertIn("settings.motion_enabled",main)

    def test_opt_in_only_mac_and_default_is_unchanged(self):
        result=stage.patch_triplet(fixture())
        main=result["nexium-gui/src/main.rs"]
        self.assertIn('#[cfg(target_os = "macos")]',main)
        self.assertIn("NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT",main)
        self.assertIn('Some("1")',main)
        self.assertIn('NEXIUM_MACOS_SKIP_SDL3_INPUT',result["nexium-gui/src/app.rs"])

    def test_true_input_instance_is_retained_and_consumed_once(self):
        inp=stage.patch_triplet(fixture())["nexium-gui/src/input.rs"]
        self.assertIn("Option<InputBackend>",inp)
        self.assertIn("InputBackend::new(motion_enabled, preferred)",inp)
        self.assertIn("slot.borrow_mut().take()",inp)
        self.assertIn("thread_local!",inp)
        self.assertIn("STAGE32_PREINPUT_CREATED_SOME",inp)

    def test_three_sources_scoped_and_idempotent(self):
        original=fixture()
        out=stage.patch_triplet(original)
        self.assertEqual(out,stage.patch_triplet(out))
        for name in original:
            self.assertIn(original[name].splitlines()[0],out[name])

    def test_reject_missing_main_source_anchor(self):
        bad=fixture()
        bad["nexium-gui/src/main.rs"]=bad["nexium-gui/src/main.rs"].replace(
            stage.MAIN_ANCHOR,"missing_anchor;\n")
        with self.assertRaisesRegex(RuntimeError,"main"):
            stage.patch_triplet(bad)

    def test_reject_missing_stage29_original_input_path(self):
        bad=fixture()
        bad["nexium-gui/src/app.rs"]=bad["nexium-gui/src/app.rs"].replace(
            "InputBackend::new","Unexpected::new")
        with self.assertRaisesRegex(RuntimeError,"Stage29"):
            stage.patch_triplet(bad)

    def test_reject_missing_or_duplicate_input_impl(self):
        bad=fixture()
        bad["nexium-gui/src/input.rs"]=bad["nexium-gui/src/input.rs"].replace(
            stage.INPUT_ANCHOR,"different_impl {\n")
        with self.assertRaisesRegex(RuntimeError,"InputBackend"):
            stage.patch_triplet(bad)
        bad=fixture()
        bad["nexium-gui/src/input.rs"] += stage.INPUT_ANCHOR
        with self.assertRaisesRegex(RuntimeError,"doubled"):
            stage.patch_triplet(bad)

    def test_reject_partial_edits_or_missing_third_file(self):
        bad=fixture()
        bad.pop("nexium-gui/src/input.rs")
        with self.assertRaisesRegex(RuntimeError,"all three"):
            stage.patch_triplet(bad)
        bad=fixture()
        bad["nexium-gui/src/main.rs"]+=stage.MARKER
        with self.assertRaisesRegex(RuntimeError,"partial"):
            stage.patch_triplet(bad)

    def test_main_writes_only_after_all_three_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            originals=fixture()
            for name,source in originals.items():
                p=root/name
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(source)
            self.assertEqual(stage.main([tmp]),0)
            expected=stage.patch_triplet(originals)
            for name in originals:
                self.assertEqual((root/name).read_text(),expected[name])
            self.assertEqual(stage.main([tmp]),0)
            broken=fixture()
            for name,source in broken.items():
                (root/name).write_text(source)
            bad_path=root/"nexium-gui/src/input.rs"
            bad_path.write_text("bad pinned source")
            self.assertEqual(stage.main([tmp]),2)
            self.assertEqual((root/"nexium-gui/src/main.rs").read_text(),
                             originals["nexium-gui/src/main.rs"])
            self.assertEqual((root/"nexium-gui/src/app.rs").read_text(),
                             originals["nexium-gui/src/app.rs"])


if __name__=="__main__":
    unittest.main()
