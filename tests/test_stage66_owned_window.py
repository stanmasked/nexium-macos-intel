"""Stage66 synthetic PID-owned window evidence, identity, and privacy gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from observe_intel_integrated_window import inspect_gui_evidence

BINARY = "a" * 64
NRO = "b" * 64


class Stage66OwnedWindowEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / "window-capture"
        self.folder.mkdir()
        self.smoke = {
            "emulator_sha256": BINARY, "nro_sha256": NRO,
            "status": "timeout_alive_unverified", "gameplay_verified": False,
            "window_capture": {
                "requested": True, "frames": 0,
                "unique_hashes": 0, "status": "no_window_frames_unverified",
            },
        }
        self.details = {
            "capture_type": "macos_pid_owned_window_only",
            "frames": [], "unique_hashes": 0,
            "status": "no_window_frames_unverified",
        }
        self.write()

    def write(self):
        (self.root / "smoke_result.json").write_text(json.dumps(self.smoke))
        (self.folder / "window_capture_result.json").write_text(
            json.dumps(self.details)
        )

    def add_png(self, index: int, token: bytes = b"\0"):
        # Minimal synthetic header matching window-capture PNG metadata.
        # Does not purport to prove a real rendered game frame.
        data = (
            b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13)
            + b"IHDR" + struct.pack(">II", 440, 240)
            + b"\x08\x06\x00\x00\x00" + b"dummycrc" + token
        )
        name = f"emulator-window-{index:03d}.png"
        path = self.folder / name
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        self.details["frames"].append({
            "file": name, "sha256": sha,
            "dimensions": [440, 240], "bytes": len(data),
        })
        self.details["unique_hashes"] = len({
            f["sha256"] for f in self.details["frames"]
        })
        self.smoke["window_capture"]["frames"] = len(self.details["frames"])
        self.smoke["window_capture"]["unique_hashes"] = (
            self.details["unique_hashes"]
        )
        self.write()

    def test_no_owned_window_is_not_graphics_success(self):
        result = inspect_gui_evidence(self.root, BINARY, NRO)
        self.assertEqual(result["observation"], "no_owned_window_frames")
        self.assertFalse(result["owned_window_visible_observed"])
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertFalse(result["main_merge_approved"])

    def test_no_capture_report_is_explicitly_unverified(self):
        (self.folder / "window_capture_result.json").unlink()
        result = inspect_gui_evidence(self.root, BINARY, NRO)
        self.assertEqual(result["observation"], "no_capture_report")
        self.assertFalse(result["owned_window_visible_observed"])

    def test_one_owned_window_frame_only_proves_observed_window(self):
        self.add_png(0)
        result = inspect_gui_evidence(self.root, BINARY, NRO)
        self.assertEqual(result["observation"], "owned_window_static_frame")
        self.assertTrue(result["owned_window_visible_observed"])
        self.assertFalse(result["window_frame_changes_observed"])
        self.assertFalse(result["guest_gpu_frames_verified"])

    def test_two_different_frame_hashes_prove_only_pixel_difference(self):
        self.add_png(0, b"one")
        self.add_png(1, b"two")
        result = inspect_gui_evidence(self.root, BINARY, NRO)
        self.assertEqual(result["observation"], "owned_window_frames_changed")
        self.assertEqual(result["owned_window_frames"], 2)
        self.assertEqual(result["unique_owned_window_hashes"], 2)
        self.assertFalse(result["guest_gpu_frames_verified"])
        self.assertFalse(result["commercial_gameplay_verified"])
        self.assertFalse(result["raw_frames_uploaded"])

    def test_repeated_identical_frames_not_misclassified_as_progress(self):
        self.add_png(0, b"same")
        self.add_png(1, b"same")
        result = inspect_gui_evidence(self.root, BINARY, NRO)
        self.assertEqual(result["unique_owned_window_hashes"], 1)
        self.assertFalse(result["window_frame_changes_observed"])

    def test_different_native_binary_rejected(self):
        with self.assertRaisesRegex(ValueError, "not bound"):
            inspect_gui_evidence(self.root, "c" * 64, NRO)

    def test_different_guest_nro_rejected(self):
        with self.assertRaisesRegex(ValueError, "not bound"):
            inspect_gui_evidence(self.root, BINARY, "c" * 64)

    def test_missing_capture_opt_in_rejected(self):
        self.smoke["window_capture"]["requested"] = False
        self.write()
        with self.assertRaisesRegex(ValueError, "not explicitly requested"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_unrelated_process_capture_type_rejected(self):
        self.add_png(0)
        self.details["capture_type"] = "whole_desktop"
        self.write()
        with self.assertRaisesRegex(ValueError, "restricted"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_changed_owned_window_png_rejected(self):
        self.add_png(0)
        (self.folder / "emulator-window-000.png").write_bytes(
            b"not the original recorded screenshot"
        )
        with self.assertRaises(ValueError):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_symlinked_window_frame_rejected(self):
        self.add_png(0)
        other = self.folder / "private-image.png"
        screenshot = self.folder / "emulator-window-000.png"
        screenshot.rename(other)
        screenshot.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "linked"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_untrusted_window_filename_rejected(self):
        self.add_png(0)
        self.details["frames"][0]["file"] = "../not-owned.png"
        self.write()
        with self.assertRaisesRegex(ValueError, "malformed"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_smoke_and_capture_frame_counts_must_agree(self):
        self.add_png(0)
        self.smoke["window_capture"]["frames"] = 9
        self.write()
        with self.assertRaisesRegex(ValueError, "disagree"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_forged_unique_hashes_rejected(self):
        self.add_png(0)
        self.details["unique_hashes"] = 99
        self.write()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_smoke_status_nonzero_exit_rejected(self):
        self.smoke["status"] = "exited_nonzero"
        self.write()
        with self.assertRaisesRegex(ValueError, "not from valid"):
            inspect_gui_evidence(self.root, BINARY, NRO)

    def test_smoke_duplicate_json_property_rejected(self):
        body = (self.root / "smoke_result.json").read_text()
        (self.root / "smoke_result.json").write_text(
            body[:-1] + ',"emulator_sha256":"'+BINARY+'"}'
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            inspect_gui_evidence(self.root, BINARY, NRO)


if __name__ == "__main__":
    unittest.main()
