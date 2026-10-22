"""Stage64 native integrated build policy fixtures; never compile in tests."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_intel_merged_tree import (
    REQUIRED_FLAGS, PROFILE_SELECTORS, native_environment,
    validate_intel_host, compile_native_intel, extract_virtual_source,
)


class Stage64NativeMergedBuildTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.work = self.root / "work"
        self.work.mkdir()

    def test_true_physical_intel_macos_target_accepted(self):
        validate_intel_host("Darwin", "x86_64", False)

    def test_apple_silicon_with_rosetta_rejected(self):
        with self.assertRaisesRegex(ValueError, "physical Intel"):
            validate_intel_host("Darwin", "x86_64", True)

    def test_arm64_macos_rejected(self):
        with self.assertRaisesRegex(ValueError, "physical Intel"):
            validate_intel_host("Darwin", "arm64", False)

    def test_linux_runner_rejected(self):
        with self.assertRaisesRegex(ValueError, "physical Intel"):
            validate_intel_host("Linux", "x86_64", False)

    def test_profile_scrubs_credentials_and_legacy_false_selectors(self):
        dirty = {
            "PATH": "/usr/bin:/bin",
            "GH_TOKEN": "private",
            "GITHUB_TOKEN": "private",
            "MY_PASSWORD": "private",
            "OTHER_SECRET": "private",
            "NEXIUM_EXPERIMENT_STAGE40_GUEST_HID": "0",
            "NEXIUM_CPU_BACKEND": "dynarmic",
            "NEXIUM_INTEL_INPUT_PROFILE": "wrong",
            "CARGO_HOME": "/tmp/cargo",
        }
        new = native_environment(dirty, self.work)
        self.assertEqual(new["NEXIUM_INTEL_INPUT_PROFILE"],
                         "controller-diagnostics-v1")
        self.assertEqual(new["NEXIUM_CPU_BACKEND"], "rustarmic")
        self.assertEqual(new["NEXIUM_MAC_WORKDIR"], str(self.work))
        self.assertEqual(new["CARGO_HOME"], "/tmp/cargo")
        self.assertTrue(all(new[k] == "1" for k in REQUIRED_FLAGS))
        self.assertTrue(all(k not in new for k in PROFILE_SELECTORS))
        self.assertFalse(any("TOKEN" in k or "PASSWORD" in k or
                             "SECRET" in k for k in new))

    def test_all_explicit_required_experiments_are_enabled(self):
        result = native_environment({}, self.work)
        self.assertEqual(result["NEXIUM_EXPERIMENT_STAGE53_DEADZONE_THRESHOLD"], "1")
        self.assertEqual(result["NEXIUM_EXPERIMENT_STAGE52_DEADZONE_JITTER"], "1")
        self.assertEqual(result["NEXIUM_EXPERIMENT_AUDIO_ABLATION"], "1")
        self.assertEqual(result["NEXIUM_EXPERIMENT_HORIZON_CTOR_ONLY"], "1")

    def test_relative_workdir_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid disposable"):
            native_environment({}, Path("relative"))

    def test_symlinked_workdir_rejected(self):
        target = self.root / "link"
        target.symlink_to(self.work, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "invalid disposable"):
            native_environment({}, target)

    def test_compilation_cannot_proceed_on_linux_with_synthetic_source(self):
        source = self.root / "src"
        source.mkdir()
        (source / "macos_probe.sh").write_text("echo fake\n")
        with self.assertRaisesRegex(ValueError, "physical Intel"):
            compile_native_intel(
                source, self.work, host_system="Linux", host_arch="x86_64",
                apple_arm_capable=False, base_env={},
            )

    def test_invalid_git_sha_blocks_virtual_source_archive(self):
        source = self.root / "src"
        source.mkdir()
        with self.assertRaisesRegex(ValueError, "invalid virtual source"):
            extract_virtual_source(self.root, "not-a-commit", source)


if __name__ == "__main__":
    unittest.main()
