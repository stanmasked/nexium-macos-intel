"""Regression checks for the local-only Dynarmic/MIG staging process."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_dynarmic_macos.py"
spec = importlib.util.spec_from_file_location("intel_mig", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CMAKE_ORIGINAL = """cmake_minimum_required(VERSION 3.12)
if (WIN32)
    target_sources(dynarmic PRIVATE "${DYNARMIC_SOURCE_DIR}/backend/exception_handler_windows.cpp")
elseif (APPLE)
    target_sources(dynarmic PRIVATE "${DYNARMIC_SOURCE_DIR}/backend/exception_handler_macos.cpp")
elseif (UNIX)
    target_sources(dynarmic PRIVATE "${DYNARMIC_SOURCE_DIR}/backend/exception_handler_posix.cpp")
endif()
"""


class DynarmicMigTests(unittest.TestCase):
    def fixture(self, base: Path):
        checkout = base / "nexium"
        checkout.mkdir()
        (checkout / "Cargo.toml").write_text("[workspace]\nresolver = \"2\"\n")
        crate = base / "cargo/registry/src/registry-test/dynarmic-sys-mythrax-0.3.6"
        (crate / "vendor").mkdir(parents=True)
        (crate / "vendor/CMakeLists.txt").write_text(CMAKE_ORIGINAL)
        (crate / "Cargo.toml").write_text('[package]\nname="dynarmic-sys-mythrax"\nversion="0.3.6"\n')
        return checkout, base / "cargo", crate

    def test_stages_local_crate_without_mutating_cargo_registry(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            checkout, cargo, crate = self.fixture(base)
            staged = module.stage(checkout, cargo, base)
            self.assertTrue(staged.is_dir())
            self.assertEqual((crate / "vendor/CMakeLists.txt").read_text(), CMAKE_ORIGINAL)
            cmake = (staged / "vendor/CMakeLists.txt").read_text()
            self.assertIn("mach_exc_server.h", cmake)
            self.assertIn("mach_exc_server.c", cmake)
            self.assertIn("COMMAND xcrun --find mig", cmake)
            self.assertIn("NE_X_MIG_FIND_RESULT", cmake)
            self.assertIn('[patch.crates-io]', (checkout / "Cargo.toml").read_text())
            self.assertIn('dynarmic-sys-mythrax-macos', (checkout / "Cargo.toml").read_text())

    def test_fails_closed_without_writing_manifest_on_changed_cmake(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            checkout, cargo, crate = self.fixture(base)
            original = (checkout / "Cargo.toml").read_text()
            (crate / "vendor/CMakeLists.txt").write_text("unexpected upstream change")
            with self.assertRaises(RuntimeError):
                module.stage(checkout, cargo, base)
            self.assertEqual((checkout / "Cargo.toml").read_text(), original)
            self.assertFalse((base / "dynarmic-sys-mythrax-macos").exists())


if __name__ == "__main__":
    unittest.main()
