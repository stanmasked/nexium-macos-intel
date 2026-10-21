"""Pinned source guard rewrite contracts; no real filesystem is exposed."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_stage41_sdmc_guard import patch_source, MARKER, OLD_PATH_BODY


class Stage41GuardPatchTests(unittest.TestCase):
    def setUp(self):
        self.guard = (
            Path(__file__).resolve().parents[1]
            / "patches/stage41_sdmc_guard.rs"
        ).read_text(encoding="utf-8")
        self.original = """use std::path::PathBuf;
pub fn sdmc_root() -> PathBuf {
    nexium_common::paths::sdmc_dir()
}

""" + OLD_PATH_BODY + """
pub fn entry_type(switch_path: &str) -> Option<EntryType> {
    let host = translate_path(switch_path);
}
impl FsHost {
    pub fn open_file(&mut self, switch_path: &str) -> Result<u32, u32> {
        let host = translate_path(switch_path);
    }
    pub fn create_file(&mut self, switch_path: &str) -> Result<(), u32> {
        let host = translate_path(switch_path);
    }
    pub fn delete_file(&mut self, switch_path: &str) -> Result<(), u32> {
        std::fs::remove_file(translate_path(switch_path))
    }
    pub fn create_dir(&mut self, switch_path: &str) -> Result<(), u32> {
        std::fs::create_dir_all(translate_path(switch_path))
    }
}
"""

    def test_idempotent_fail_closed_patch_and_all_five_call_sites(self):
        transformed = patch_source(self.original, self.guard)
        self.assertEqual(transformed.count(MARKER), 1)
        self.assertIn("Result<PathBuf, u32>", transformed)
        self.assertIn('var_os("NEXIUM_DATA_ROOT")', transformed)
        self.assertIn("let host = translate_path(switch_path).ok()?;", transformed)
        self.assertEqual(transformed.count("let host = translate_path(switch_path)?;"), 2)
        self.assertIn("remove_file(translate_path(switch_path)?)", transformed)
        self.assertIn("create_dir_all(translate_path(switch_path)?)", transformed)
        self.assertEqual(patch_source(transformed, self.guard), transformed)

    def test_missing_anchor_does_not_weaken_validation(self):
        with self.assertRaisesRegex(ValueError, "anchor drifted"):
            patch_source(self.original.replace("sdmc_root().join", "other_root().join"),
                         self.guard)

    def test_changed_caller_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "caller changed"):
            patch_source(self.original.replace(
                "remove_file(translate_path(switch_path))", "remove_file(unsafe_path)"
            ), self.guard)


if __name__ == "__main__":
    unittest.main()
