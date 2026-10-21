"""Stage33: fail closed on source drift and retain exact SDL3 subcall order."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_sdl3_subcall_trace as stage

SOURCE=('impl InputBackend {\n'+stage.START+
        '\n'.join(anchor for _,anchor in stage.PHASES)+'\n'+
        '    }\n'+stage.END+' }\n}\n')

class Stage33InputTraceTests(unittest.TestCase):
    def test_seven_markers_are_ordered(self):
        d=stage.patch_source(SOURCE)
        self.assertEqual(d.count(stage.MARKER),7)
        self.assertEqual([d.index(stage.MARKER+k) for k,_ in stage.PHASES],
                         sorted(d.index(stage.MARKER+k) for k,_ in stage.PHASES))

    def test_every_original_initializer_is_preserved(self):
        d=stage.patch_source(SOURCE)
        for _,anchor in stage.PHASES:
            self.assertIn(anchor,d)
        self.assertIn('sdl3::init().ok()?;',d)
        self.assertIn('sdl.gamepad().ok()?;',d)

    def test_markers_are_opt_in_on_macos(self):
        d=stage.patch_source(SOURCE)
        self.assertEqual(d.count('NEXIUM_MACOS_SDL3_SUBCALL_TRACE'),7)
        self.assertEqual(d.count('#[cfg(target_os = "macos")]'),7)

    def test_idempotence(self):
        d=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(d),d)

    def test_missing_constructor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"boundaries"):
            stage.patch_source(SOURCE.replace(stage.START,'unexpected ctor {\n'))

    def test_missing_sdl3_call_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"02_BEFORE_SDL_INIT"):
            stage.patch_source(SOURCE.replace('sdl3::init().ok()?','other()'))

    def test_duplicate_gamepad_call_rejected(self):
        a=stage.PHASES[3][1]
        with self.assertRaisesRegex(RuntimeError,"03_AFTER_SDL_INIT"):
            stage.patch_source(SOURCE.replace(a,a+'\n'+a))

    def test_reordered_source_rejected(self):
        a,b=stage.PHASES[2][1],stage.PHASES[3][1]
        bad=SOURCE.replace(a,"TEMP").replace(b,a).replace("TEMP",b)
        with self.assertRaisesRegex(RuntimeError,"reordered"):
            stage.patch_source(bad)

    def test_partial_existing_marker_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"partial"):
            stage.patch_source(SOURCE+stage.MARKER+"02_BEFORE_SDL_INIT")

    def test_file_only_written_on_full_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p=root/"nexium-gui/src/input.rs"
            p.parent.mkdir(parents=True)
            p.write_text(SOURCE)
            self.assertEqual(stage.main([temp]),0)
            self.assertEqual(p.read_text(),stage.patch_source(SOURCE))
            self.assertEqual(stage.main([temp]),0)
            bad=SOURCE.replace(stage.PHASES[2][1],"broken")
            p.write_text(bad)
            self.assertEqual(stage.main([temp]),2)
            self.assertEqual(p.read_text(),bad)

if __name__=="__main__":
    unittest.main()
