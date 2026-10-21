import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_macos_guest_hid_probe.py"
SPEC = importlib.util.spec_from_file_location("guest_hid_patch", SCRIPT)
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


FIXTURE = '''
let down = n >= 1 && n < 12;
} else if n == 12 { eprintln!("STAGE36_VIRTUAL_SYNTHETIC_RELEASE_SENT"); }
'''


class GuestHidLongHoldPatchTests(unittest.TestCase):
    def test_extends_only_the_guest_probe_hold(self):
        result = PATCH.patch_source(FIXTURE)
        self.assertIn('var_os("NEXIUM_MACOS_GUEST_HID_PROBE")', result)
        self.assertIn("900", result)
        self.assertIn("else {\\n                12", result)
        self.assertIn("else if n == hold_ticks", result)
        self.assertNotIn("let down = n >= 1 && n < 12;", result)

    def test_patch_is_idempotent(self):
        once = PATCH.patch_source(FIXTURE)
        self.assertEqual(PATCH.patch_source(once), once)

    def test_missing_or_duplicate_anchor_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "anchors absent or doubled"):
            PATCH.patch_source(FIXTURE.replace("n < 12", "n < 11"))
        with self.assertRaisesRegex(RuntimeError, "anchors absent or doubled"):
            PATCH.patch_source(FIXTURE + FIXTURE)


if __name__ == "__main__":
    unittest.main()
