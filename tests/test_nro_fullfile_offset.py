"""Strict Stage33 NRO file-origin patch synthetic regression fixtures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

TARGET = Path(__file__).resolve().parents[1] / "scripts/apply_nro_fullfile_offset.py"
spec = importlib.util.spec_from_file_location("stage33_nro_origin", TARGET)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

SOURCE = (
    "impl Nro {\n"
    "    pub fn parse_mmap(mmap: Arc<Mmap>) -> Result<Self, String> {\n"
    + stage.OLD_HEADER + "\n"
    + stage.OLD_SEGMENTS + "\n"
    + stage.OLD_BOUNDS + "\n"
    + "\n".join(before for before, _ in stage.RANGE_REWRITES)
    + "\n    }\n}\n"
)


class SegmentOriginPatchTests(unittest.TestCase):
    def test_official_16_byte_nro_start_uses_full_file_and_unchanged_magic_read(self):
        output = stage.patch(SOURCE)
        self.assertIn("let file_origin = if standard_nro_start { 0 } else { nro_offset };",output)
        self.assertIn("NroHeader::from_bytes(&mmap[nro_offset..])?",output)
        self.assertIn("if standard_nro_start {\n            header.text_offset",output)
        self.assertNotIn(stage.OLD_HEADER,output)

    def test_strict_bounds_also_reject_declared_image_and_asset_overflow(self):
        output = stage.patch(SOURCE)
        self.assertIn("NRO declared image size out of bounds",output)
        self.assertIn("header.size as usize",output)
        self.assertIn("checked_add",output)
        self.assertIn("Data segment out of bounds",output)
        self.assertIn("end > image_limit",output)

    def test_segment_ranges_use_file_origin_consistently(self):
        output = stage.patch(SOURCE)
        for old,new in stage.RANGE_REWRITES:
            self.assertNotIn(old,output)
            self.assertIn(new,output)

    def test_idempotent(self):
        once = stage.patch(SOURCE)
        self.assertEqual(once,stage.patch(once))

    def test_original_anchor_drift_fails_closed(self):
        for original in (stage.OLD_HEADER,stage.OLD_SEGMENTS,stage.OLD_BOUNDS):
            with self.assertRaisesRegex(RuntimeError,"anchor"):
                stage.patch(SOURCE.replace(original,"changed upstream code"))

    def test_partial_edit_refused(self):
        partial = SOURCE.replace(stage.OLD_HEADER,stage.NEW_HEADER)
        with self.assertRaisesRegex(RuntimeError,"partial Stage33"):
            stage.patch(partial)

    def test_real_tempfile_scoped_to_loader_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"nexium-loader/src/nro.rs"
            target.parent.mkdir(parents=True)
            target.write_text(SOURCE)
            other=root/"nexium-gui/src/main.rs"
            other.parent.mkdir(parents=True)
            other.write_text("untouched")
            self.assertEqual(stage.patch(target.read_text()),stage.patch(SOURCE))
            self.assertEqual(other.read_text(),"untouched")


if __name__ == "__main__":
    unittest.main()
