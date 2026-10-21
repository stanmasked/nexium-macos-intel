"""Stage55: independent strict replay of the exact Stage54 three-artifact proof."""
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
)
from verify_intel_controller_proof_manifest import verify

COMMIT = "5bdb81e41c53849dbd6afdb7edb3186113cf251f"
RUN = "39686688178"


class Stage55ProofReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.binary = root / "nexium"
        self.binary.write_bytes(
            b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x01000007) + b"\0" * 120
        )
        self.nro = root / "diagnostic.nro"
        self.nro.write_bytes(b"\0" * 16 + b"NRO0" + b"\0" * 508)
        self.receipt = root / "receipt.json"
        receipt = {
            "schema": "nexium-stage53-guest-deadzone-threshold/v1",
            "original_npad_serialized_sample_count": 5,
        }
        receipt.update({key: True for key in REQUIRED_TRUE})
        receipt.update({key: False for key in REQUIRED_FALSE})
        self.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        self.manifest = root / "manifest.json"
        self.manifest.write_text(
            json.dumps(audit(self.binary, self.nro, self.receipt,
                             PINNED_UPSTREAM, COMMIT, RUN)),
            encoding="utf-8",
        )

    def replay(self, source=PINNED_UPSTREAM, commit=COMMIT, run=RUN):
        return verify(self.manifest, self.binary, self.nro, self.receipt,
                      source, commit, run)

    def change_manifest(self, key, value):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data[key] = value
        self.manifest.write_text(json.dumps(data), encoding="utf-8")

    def test_exact_artifact_triplet_passes(self):
        result = self.replay()
        self.assertTrue(result["exact_triplet_replay_passed"])
        self.assertFalse(result["physical_controller_verified"])
        self.assertFalse(result["production_release_verified"])

    def test_changed_intel_binary_same_length_fails(self):
        data = bytearray(self.binary.read_bytes())
        data[-1] = 0x7F
        self.binary.write_bytes(data)
        with self.assertRaises(ValueError):
            self.replay()

    def test_changed_nro_same_length_fails(self):
        data = bytearray(self.nro.read_bytes())
        data[-1] = 0x7F
        self.nro.write_bytes(data)
        with self.assertRaises(ValueError):
            self.replay()

    def test_changed_sanitized_receipt_fails(self):
        data = json.loads(self.receipt.read_text())
        data["original_npad_serialized_sample_count"] = 7
        self.receipt.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.replay()

    def test_changed_digest_fails(self):
        self.change_manifest("public_guest_nro_sha256", "0" * 64)
        with self.assertRaises(ValueError):
            self.replay()

    def test_changed_byte_count_fails(self):
        self.change_manifest("intel_macho_bytes", 9999)
        with self.assertRaises(ValueError):
            self.replay()

    def test_boolean_integer_equivalence_cannot_bypass(self):
        self.change_manifest("provenance_passed", 1)
        with self.assertRaises(ValueError):
            self.replay()

    def test_false_claim_of_physical_controller_fails(self):
        self.change_manifest("physical_controller_verified", True)
        with self.assertRaises(ValueError):
            self.replay()

    def test_unknown_manifest_key_fails(self):
        self.change_manifest("private_trace", "no")
        with self.assertRaises(ValueError):
            self.replay()

    def test_removed_manifest_key_fails(self):
        data = json.loads(self.manifest.read_text())
        del data["sanitized_guest_receipt_sha256"]
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.replay()

    def test_duplicate_json_key_fails(self):
        data = self.manifest.read_text()
        self.manifest.write_text(data[:-1] + ',"provenance_passed":true}')
        with self.assertRaises(ValueError):
            self.replay()

    def test_wrong_ci_run_fails(self):
        with self.assertRaises(ValueError):
            self.replay(run="39684613237")

    def test_wrong_workflow_commit_fails(self):
        with self.assertRaises(ValueError):
            self.replay(commit="f" * 40)

    def test_wrong_upstream_sha_fails(self):
        with self.assertRaises(ValueError):
            self.replay(source="f" * 40)

    def test_non_object_manifest_fails(self):
        self.manifest.write_text("[]")
        with self.assertRaises(ValueError):
            self.replay()

    def test_invalid_utf8_fails(self):
        self.manifest.write_bytes(b"\xff\xfe")
        with self.assertRaises(UnicodeError):
            self.replay()

    def test_nonfinite_json_number_fails(self):
        self.change_manifest("intel_macho_bytes", 1)
        data = self.manifest.read_text()
        self.manifest.write_text(data.replace('"intel_macho_bytes": 1', '"intel_macho_bytes": NaN'))
        with self.assertRaises(ValueError):
            self.replay()

    def test_oversized_manifest_fails(self):
        self.manifest.write_text(" " * 16400 + self.manifest.read_text())
        with self.assertRaises(ValueError):
            self.replay()


if __name__ == "__main__":
    unittest.main()
