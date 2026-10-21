"""Stage54 fail-closed provenance checks: only exact Intel+NRO+receipt triplets."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_intel_controller_proof_manifest import (
    audit, PINNED_UPSTREAM, REQUIRED_TRUE, REQUIRED_FALSE,
    read_sanitized_receipt, require_intel_macho, require_public_nro,
)

COMMIT = "ae766265ba2e91e747f25eb3e7e68eff16794fc2"
RUN = "39684613237"


def fixture(root: Path):
    binary = root / "nexium"
    # Minimal thin MH_MAGIC_64 x86_64 header, not an executable binary.
    header = b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x01000007)
    binary.write_bytes(header + b"\0" * 120)
    nro = root / "public.nro"
    nro.write_bytes(b"\0" * 16 + b"NRO0" + b"\0" * 508)
    receipt = root / "sanitized.json"
    info = {
        "schema": "nexium-stage53-guest-deadzone-threshold/v1",
        "original_npad_serialized_sample_count": 5,
    }
    info.update({key: True for key in REQUIRED_TRUE})
    info.update({key: False for key in REQUIRED_FALSE})
    receipt.write_text(json.dumps(info), encoding="utf-8")
    return binary, nro, receipt


def run(root):
    binary, nro, receipt = fixture(root)
    return audit(binary, nro, receipt, PINNED_UPSTREAM, COMMIT, RUN)


class Stage54ProvenanceManifestTests(unittest.TestCase):
    def test_exact_proof_triplet_emits_minimal_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run(Path(temp))
            self.assertTrue(result["provenance_passed"])
            self.assertEqual(result["original_npad_samples"], 5)
            self.assertEqual(len(result["intel_macho_sha256"]), 64)
            self.assertEqual(len(result["public_guest_nro_sha256"]), 64)
            self.assertEqual(len(result["sanitized_guest_receipt_sha256"]), 64)
            self.assertEqual(result["upstream_source_sha"], PINNED_UPSTREAM)
            self.assertFalse(result["physical_controller_verified"])
            self.assertNotIn("file_path", result)
            self.assertNotIn("raw_guest_log", result)

    def test_replacing_macho_changes_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary, nro, receipt = fixture(root)
            baseline = audit(binary, nro, receipt, PINNED_UPSTREAM, COMMIT, RUN)
            with binary.open("ab") as stream:
                stream.write(b"modified")
            changed = audit(binary, nro, receipt, PINNED_UPSTREAM, COMMIT, RUN)
            self.assertNotEqual(baseline["intel_macho_sha256"], changed["intel_macho_sha256"])

    def test_replacing_public_nro_changes_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary, nro, receipt = fixture(root)
            old = audit(binary, nro, receipt, PINNED_UPSTREAM, COMMIT, RUN)
            with nro.open("ab") as stream:
                stream.write(b"new")
            new = audit(binary, nro, receipt, PINNED_UPSTREAM, COMMIT, RUN)
            self.assertNotEqual(old["public_guest_nro_sha256"], new["public_guest_nro_sha256"])

    def test_wrong_arm64_macho_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            binary, _, _ = fixture(Path(temp))
            b = bytearray(binary.read_bytes())
            b[4:8] = struct.pack("<I", 0x0100000C)
            binary.write_bytes(b)
            with self.assertRaises(ValueError):
                require_intel_macho(binary)

    def test_universal_or_elf_binary_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            binary, _, _ = fixture(Path(temp))
            binary.write_bytes(b"\xca\xfe\xba\xbe" + b"\0" * 128)
            with self.assertRaises(ValueError):
                require_intel_macho(binary)

    def test_truncated_macho_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            binary, _, _ = fixture(Path(temp))
            binary.write_bytes(b"\xcf\xfa\xed\xfe")
            with self.assertRaises(ValueError):
                require_intel_macho(binary)

    def test_missing_nro_header_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            _, nro, _ = fixture(Path(temp))
            nro.write_bytes(b"\0" * 512)
            with self.assertRaises(ValueError):
                require_public_nro(nro)

    def test_truncated_nro_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            _, nro, _ = fixture(Path(temp))
            nro.write_bytes(b"\0" * 16 + b"NRO0" + b"\0" * 2)
            with self.assertRaises(ValueError):
                require_public_nro(nro)

    def test_upstream_sha_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b, n, r = fixture(root)
            with self.assertRaises(ValueError):
                audit(b, n, r, "0" * 40, COMMIT, RUN)

    def test_repository_sha_malformed_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b, n, r = fixture(root)
            with self.assertRaises(ValueError):
                audit(b, n, r, PINNED_UPSTREAM, "not-a-sha", RUN)

    def test_run_id_malformed_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b, n, r = fixture(root)
            with self.assertRaises(ValueError):
                audit(b, n, r, PINNED_UPSTREAM, COMMIT, "bad-id")

    def test_guest_receipt_unpassed_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b, n, r = fixture(root)
            info = json.loads(r.read_text())
            info["same_process_guest_deadzone_threshold_passed"] = False
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                audit(b, n, r, PINNED_UPSTREAM, COMMIT, RUN)

    def test_missing_source_observation_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, r = fixture(root)
            info = json.loads(r.read_text())
            info.pop("original_source_below_zero_above_signed_all_four_axes")
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                read_sanitized_receipt(r)

    def test_guest_incomplete_marker_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, r = fixture(root)
            info = json.loads(r.read_text())
            info["guest_incomplete_or_unexpected_button_observed"] = True
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                read_sanitized_receipt(r)

    def test_raw_logs_uploaded_flag_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, r = fixture(root)
            info = json.loads(r.read_text())
            info["raw_logs_uploaded"] = True
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                read_sanitized_receipt(r)

    def test_unknown_raw_guest_data_key_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, r = fixture(root)
            info = json.loads(r.read_text())
            info["raw_guest_dump"] = "secret"
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                read_sanitized_receipt(r)

    def test_json_arrays_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, r = fixture(root)
            info = json.loads(r.read_text())
            info["original_npad_serialized_sample_count"] = [5]
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                read_sanitized_receipt(r)

    def test_guest_npad_zero_samples_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, r = fixture(root)
            info = json.loads(r.read_text())
            info["original_npad_serialized_sample_count"] = 0
            r.write_text(json.dumps(info))
            with self.assertRaises(ValueError):
                read_sanitized_receipt(r)


if __name__ == "__main__":
    unittest.main()
