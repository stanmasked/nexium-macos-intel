"""Stage28: guard every constructor phase and reject source drift."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import apply_macos_horizon_ctor_phase_trace as stage

SOURCE=("fn other() {}\n"+stage.START+"\n"+
        "\n".join(anchor for _,anchor in stage.PHASES)+"\n"+
        stage.END+" {\n}\nimpl eframe::App for HorizonApp {}\n")

class Stage28PhaseMarkerTests(unittest.TestCase):
    def test_all_phases_in_order(self):
        patched=stage.patch_source(SOURCE)
        self.assertEqual(patched.count(stage.MARKER),len(stage.PHASES))
        positions=[patched.index(stage.MARKER+name) for name,_ in stage.PHASES]
        self.assertEqual(positions,sorted(positions))
        self.assertIn('NEXIUM_MACOS_CONSTRUCTOR_PHASE_TRACE',patched)

    def test_preserves_all_original_source_anchors(self):
        patched=stage.patch_source(SOURCE)
        for _,anchor in stage.PHASES:
            self.assertIn(anchor,patched)
        self.assertIn("impl eframe::App for HorizonApp",patched)

    def test_idempotent(self):
        patched=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(patched),patched)

    def test_missing_pinned_constructor_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"boundaries"):
            stage.patch_source(SOURCE.replace(stage.START,"fn any_other_ctor() {"))

    def test_missing_horizonapp_trait_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"trait"):
            stage.patch_source(SOURCE.replace("impl eframe::App for HorizonApp","impl eframe::App for Other"))

    def test_duplicate_or_missing_anchor_rejected(self):
        s=SOURCE.replace(stage.PHASES[2][1],stage.PHASES[2][1]+"\n"+stage.PHASES[2][1])
        with self.assertRaisesRegex(RuntimeError,"duplicated"):
            stage.patch_source(s)
        s=SOURCE.replace(stage.PHASES[5][1],"call_other_function();")
        with self.assertRaisesRegex(RuntimeError,"absent"):
            stage.patch_source(s)

    def test_out_of_order_phase_rejected(self):
        a=stage.PHASES[2][1]
        b=stage.PHASES[3][1]
        misplaced=SOURCE.replace(a,"TEMP").replace(b,a).replace("TEMP",b)
        with self.assertRaisesRegex(RuntimeError,"order"):
            stage.patch_source(misplaced)

    def test_partially_patched_source_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"partial"):
            stage.patch_source(SOURCE+stage.MARKER+"00_BEFORE_THEME")

    def test_write_once_and_refuse_bad_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p=root/"nexium-gui/src/app.rs"
            p.parent.mkdir(parents=True)
            p.write_text(SOURCE)
            self.assertEqual(stage.main([str(root)]),0)
            original=stage.patch_source(SOURCE)
            self.assertEqual(p.read_text(),original)
            self.assertEqual(stage.main([str(root)]),0)
            self.assertEqual(p.read_text(),original)
            p.write_text(SOURCE.replace(stage.START,"unexpected"))
            self.assertEqual(stage.main([str(root)]),2)
            self.assertEqual(p.read_text(),SOURCE.replace(stage.START,"unexpected"))

if __name__=="__main__":
    unittest.main()
