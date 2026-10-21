"""Fail-closed Stage38 source patch tests for the actual pinned input.rs."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_sdl3_subphase_trace as stage

SOURCE = (
    "impl InputBackend {\n"
    + stage.START + "\n"
    + "\n".join(anchor for _, anchor in stage.PHASES) + "\n"
    + "        Some(Self { /* synthetic */ })\n    }\n"
    + stage.END + "\n}\n"
)

class SDL3SubphaseTests(unittest.TestCase):
    def test_five_phases_in_exact_order(self):
        patched=stage.patch_source(SOURCE)
        markers=[stage.PREFIX + name for name,_ in stage.PHASES]
        self.assertEqual([patched.index(m) for m in markers],
                         sorted(patched.index(m) for m in markers))
        self.assertEqual(patched.count(stage.PREFIX),5)

    def test_preserves_every_original_sdl3_call(self):
        patched=stage.patch_source(SOURCE)
        for name,anchor in stage.PHASES:
            self.assertIn(anchor,patched)
            self.assertIn(stage.block(name),patched)
        self.assertIn('cfg(target_os = "macos")',patched)
        self.assertIn('NEXIUM_MACOS_SDL3_SUBPHASE_TRACE',patched)

    def test_idempotent_after_success(self):
        once=stage.patch_source(SOURCE)
        self.assertEqual(stage.patch_source(once),once)

    def test_missing_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,"source anchors"):
            stage.patch_source(SOURCE.replace(stage.PHASES[1][1],"wrong sdl init"))

    def test_out_of_order_rejected(self):
        a=stage.PHASES[1][1]
        b=stage.PHASES[2][1]
        changed=SOURCE.replace(a,"TEMP").replace(b,a).replace("TEMP",b)
        with self.assertRaisesRegex(ValueError,"call order"):
            stage.patch_source(changed)

    def test_duplicate_source_anchor_rejected(self):
        a=stage.PHASES[2][1]
        changed=SOURCE.replace(a,a+"\n"+a)
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            stage.patch_source(changed)

    def test_partial_instrumentation_rejected(self):
        with self.assertRaisesRegex(ValueError,"partial"):
            stage.patch_source(SOURCE + stage.PREFIX + "00_ENTRY")

    def test_real_file_changed_only_once_and_no_partial_write(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"nexium-gui/src/input.rs"
            p.parent.mkdir(parents=True)
            p.write_text(SOURCE)
            self.assertEqual(stage.main([temp]),0)
            once=p.read_text()
            self.assertEqual(stage.main([temp]),0)
            self.assertEqual(p.read_text(),once)
            p.write_text(SOURCE.replace(stage.PHASES[0][1],"mismatch"))
            self.assertEqual(stage.main([temp]),2)
            self.assertNotIn(stage.PREFIX,p.read_text())

if __name__ == "__main__":
    unittest.main()
