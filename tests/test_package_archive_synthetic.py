"""Synthetic permission-preservation test for GitHub .app release archives."""
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/package_intel_app.sh"


@unittest.skipUnless(shutil.which("bash") and shutil.which("tar") and
                     shutil.which("shasum"), "tar/shasum/bourne shell required")
class PackageArchiveTests(unittest.TestCase):
    def test_archive_preserves_binary_executable_bit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / "NeXium-Test.app"
            binary = app / "Contents/MacOS/nexium"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"synthetic mock executable, not a Mach-O")
            binary.chmod(0o755)
            (app / "Contents/Info.plist").write_text("<plist><dict/></plist>")
            license_file = root / "NeXium-LICENSE.txt"
            license_file.write_text("synthetic license fixture")
            result = subprocess.run(
                ["bash", str(SCRIPT), str(app), str(license_file)],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = root / "NeXium-Test.tar.gz"
            self.assertTrue(archive.is_file())
            self.assertTrue((root / "NeXium-Test.tar.gz.sha256").is_file())
            with tarfile.open(archive, "r:gz") as src:
                member = src.getmember("NeXium-Test.app/Contents/MacOS/nexium")
                self.assertTrue(member.mode & 0o111)
                self.assertIsNotNone(src.getmember("NeXium-LICENSE.txt"))

    def test_refuses_bundles_without_executable_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / "NeXium-Test.app"
            (app / "Contents/MacOS").mkdir(parents=True)
            (app / "Contents/Info.plist").write_text("plist")
            license_file = root / "NeXium-LICENSE.txt"
            license_file.write_text("fixture")
            result = subprocess.run(
                ["bash", str(SCRIPT), str(app), str(license_file)],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 3)
            self.assertFalse((root / "NeXium-Test.tar.gz").exists())


if __name__ == "__main__":
    unittest.main()
