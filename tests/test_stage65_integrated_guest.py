"""Stage65 public libnx guest provenance, hygiene and fail-closed tests."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from probe_intel_integrated_guest import (
    GUEST_PROBE_ENV, probe_environment, validate_public_probe,
    run_integrated_guest,
)
from audit_intel_controller_proof_manifest import REQUIRED_FALSE, REQUIRED_TRUE


class Stage65IntegratedGuestTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.nro = self.root / "probe.nro"
        buf = bytearray(0x100)
        buf[0x10:0x14] = b"NRO0"
        struct.pack_into("<I", buf, 0x18, 0x100)
        struct.pack_into("<6I", buf, 0x20, 0, 0x80, 0x80, 0x40, 0xC0, 0x40)
        self.nro.write_bytes(buf)

    def test_valid_synthetic_public_nro_format_passes(self):
        self.assertEqual(validate_public_probe(self.nro), 0x100)

    def test_fake_nro_header_is_rejected(self):
        self.nro.write_bytes(b"not a public homebrew NRO")
        with self.assertRaises(ValueError):
            validate_public_probe(self.nro)

    def test_missing_nro_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing regular"):
            validate_public_probe(self.root / "missing.nro")

    def test_wrong_suffix_rejected(self):
        self.nro.rename(self.root / "probe.bin")
        with self.assertRaisesRegex(ValueError, "missing regular"):
            validate_public_probe(self.root / "probe.bin")

    def test_symlinked_nro_rejected(self):
        link = self.root / "alias.nro"
        link.symlink_to(self.nro)
        with self.assertRaisesRegex(ValueError, "missing regular"):
            validate_public_probe(link)

    def test_missing_guest_binary_rejected_before_spawning_smoke(self):
        src = self.root / "source"
        src.mkdir()
        with self.assertRaisesRegex(ValueError, "Mach-O unavailable"):
            run_integrated_guest(
                source=src, binary=self.root / "missing",
                guest_nro=self.nro, report_dir=self.root / "report",
                repository_sha="a"*40, run_id="1234567", base_env={},
            )

    def test_guest_probe_env_disables_other_simultaneous_stage_modes(self):
        out = probe_environment({})
        self.assertEqual(out["NEXIUM_CPU_BACKEND"], "rustarmic")
        self.assertEqual(out["NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE"], "1")
        self.assertEqual(out["NEXIUM_MACOS_GUEST_AB_PROBE"], "0")
        self.assertEqual(out["NEXIUM_MACOS_GUEST_DUAL_STICK_PROBE"], "0")
        self.assertEqual(out["NEXIUM_MACOS_NO_AUDIO"], "1")
        self.assertEqual(out["NEXIUM_MACOS_SKIP_SDL3_INPUT"], "0")

    def test_guest_probe_strips_github_token_and_build_experiments(self):
        base = {
            "GH_TOKEN": "private-token",
            "GITHUB_TOKEN": "private-token",
            "GITHUB_ACTIONS": "true",
            "PERSONAL_SECRET": "private",
            "NEXIUM_EXPERIMENT_STAGE40_GUEST_HID": "0",
            "NEXIUM_INTEL_INPUT_PROFILE": "bad",
            "NEXIUM_MAC_WORKDIR": "/sensitive",
            "PATH": "/bin:/usr/bin",
        }
        out = probe_environment(base)
        self.assertEqual(out["PATH"], "/bin:/usr/bin")
        self.assertNotIn("GH_TOKEN", out)
        self.assertNotIn("GITHUB_TOKEN", out)
        self.assertNotIn("PERSONAL_SECRET", out)
        self.assertNotIn("GITHUB_ACTIONS", out)
        self.assertNotIn("NEXIUM_MAC_WORKDIR", out)
        self.assertNotIn("NEXIUM_INTEL_INPUT_PROFILE", out)
        self.assertNotIn("NEXIUM_EXPERIMENT_STAGE40_GUEST_HID", out)

    def test_profile_contains_real_stage53_host_source_observations(self):
        self.assertEqual(GUEST_PROBE_ENV["NEXIUM_MACOS_GUEST_DEADZONE_THRESHOLD_PROBE"], "1")
        self.assertEqual(GUEST_PROBE_ENV["NEXIUM_MACOS_STAGE37_HID_BRIDGE_TRACE"], "1")
        self.assertEqual(GUEST_PROBE_ENV["NEXIUM_MACOS_SDL3_PREINIT_BEFORE_WINIT"], "1")
        self.assertEqual(GUEST_PROBE_ENV["NEXIUM_MACOS_VIRTUAL_BUTTON_TEST"], "1")

    def test_receipt_allowlist_matches_existing_stage53_contract(self):
        receipt = {"schema": "nexium-stage53-guest-deadzone-threshold/v1",
                   "original_npad_serialized_sample_count": 5}
        receipt.update({key: True for key in REQUIRED_TRUE})
        receipt.update({key: False for key in REQUIRED_FALSE})
        self.assertFalse(receipt["physical_controller_verified"])
        self.assertFalse(receipt["gameplay_verified"])
        self.assertFalse(receipt["real_switch_verified"])
        self.assertTrue(receipt["same_process_guest_deadzone_threshold_passed"])

    def test_failed_nro_check_never_invokes_guest_process(self):
        self.nro.write_bytes(b"invalid")
        with mock.patch("probe_intel_integrated_guest.subprocess.run") as run:
            with self.assertRaises(ValueError):
                run_integrated_guest(
                    source=self.root, binary=self.root / "not-used",
                    guest_nro=self.nro, report_dir=self.root / "output",
                    repository_sha="a"*40, run_id="1234567", base_env={},
                )
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
