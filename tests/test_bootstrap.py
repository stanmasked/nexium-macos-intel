"""Guarded bootstrap must be repeatable and reject changed upstream anchors."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_macos_bootstrap.py"
GUI_ANCHOR = '''    setup.instance_descriptor.backends =
        eframe::wgpu::Backends::from_env().unwrap_or(eframe::wgpu::Backends::VULKAN);'''
ADAPTER_ANCHOR = '''    let instance = unsafe {
        entry.create_instance(
            &vk::InstanceCreateInfo::default().application_info(&app),
            None,
        )
    }
    .map_err(|error| format!("create instance: {error:?}"))?;'''


class BootstrapTests(unittest.TestCase):
    def fixture(self, root):
        gui = root / "nexium-gui/src/main.rs"
        adapter = root / "nexium-gpu/src/adapter.rs"
        for file in (gui, adapter):
            file.parent.mkdir(parents=True, exist_ok=True)
        gui.write_text(GUI_ANCHOR)
        adapter.write_text(ADAPTER_ANCHOR)
        return gui, adapter

    def test_applies_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gui, adapter = self.fixture(root)
            run = [sys.executable, str(SCRIPT), str(root)]
            self.assertEqual(subprocess.run(run, capture_output=True).returncode, 0)
            self.assertIn('Backends::METAL', gui.read_text())
            self.assertIn('ENUMERATE_PORTABILITY_KHR', adapter.read_text())
            changed = (gui.read_bytes(), adapter.read_bytes())
            self.assertEqual(subprocess.run(run, capture_output=True).returncode, 0)
            self.assertEqual(changed, (gui.read_bytes(), adapter.read_bytes()))

    def test_changed_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gui, adapter = self.fixture(root)
            adapter.write_text("upstream source changed; do not guess")
            run = [sys.executable, str(SCRIPT), str(root)]
            self.assertNotEqual(subprocess.run(run, capture_output=True).returncode, 0)
            self.assertEqual(adapter.read_text(), "upstream source changed; do not guess")


if __name__ == "__main__":
    unittest.main()
