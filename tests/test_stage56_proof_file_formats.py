"""Stage56 structural input gate: forged headers and ambiguous receipts fail closed."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_intel_controller_proof_manifest import REQUIRED_TRUE, REQUIRED_FALSE
from audit_intel_controller_proof_structure import (
    audit_structure, validate_macho, validate_nro, validate_receipt,
)


class Stage56FileFormatTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.binary = root / "nexium"
        self.nro = root / "probe.nro"
        self.receipt = root / "receipt.json"
        # Fixture is a minimal structurally valid Mach-O, never executable.
        header = struct.pack("<8I", 0xFEEDFACF, 0x01000007, 3, 2,
                             1, 72, 0, 0)
        segment = struct.pack("<2I", 0x19, 72) + b"\0" * 64
        self.binary.write_bytes(header + segment)
        nro = bytearray(0x100)
        nro[0x10:0x14] = b"NRO0"
        struct.pack_into("<I", nro, 0x18, 0x100)
        struct.pack_into("<6I", nro, 0x20, 0, 0x80, 0x80,
                         0x40, 0xC0, 0x40)
        self.nro.write_bytes(nro)
        r = {"schema": "nexium-stage53-guest-deadzone-threshold/v1",
             "original_npad_serialized_sample_count": 5}
        r.update({key: True for key in REQUIRED_TRUE})
        r.update({key: False for key in REQUIRED_FALSE})
        self.receipt.write_text(json.dumps(r), encoding="utf-8")

    def mutate_macho(self, offset: int, value: int):
        data = bytearray(self.binary.read_bytes())
        struct.pack_into("<I", data, offset, value)
        self.binary.write_bytes(data)

    def mutate_nro(self, offset: int, value: int):
        data = bytearray(self.nro.read_bytes())
        struct.pack_into("<I", data, offset, value)
        self.nro.write_bytes(data)

    def test_structurally_sound_triplet_passes(self):
        result = audit_structure(self.binary, self.nro, self.receipt)
        self.assertTrue(result["structure_audit_passed"])
        self.assertEqual(result["intel_macho_load_commands"], 1)
        self.assertEqual(result["nro_declared_bytes"], 0x100)
        self.assertFalse(result["physical_controller_verified"])

    def test_wrong_macho_cpu_rejected(self):
        self.mutate_macho(4, 0x0100000C)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_fake_macho_object_not_executable_rejected(self):
        self.mutate_macho(12, 1)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_no_load_commands_rejected(self):
        self.mutate_macho(16, 0)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_declared_commands_exceed_file_rejected(self):
        self.mutate_macho(20, 10000)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_zero_load_command_size_rejected(self):
        self.mutate_macho(36, 0)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_truncated_segment_command_rejected(self):
        self.mutate_macho(36, 8)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_missing_segment_command_rejected(self):
        self.mutate_macho(32, 0x1B)
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_macho_cputype_magic_only_not_enough(self):
        self.binary.write_bytes(self.binary.read_bytes()[:32])
        with self.assertRaises(ValueError):
            validate_macho(self.binary)

    def test_nro_declared_size_zero_rejected(self):
        self.mutate_nro(0x18, 0)
        with self.assertRaises(ValueError):
            validate_nro(self.nro)

    def test_nro_declared_size_exceeds_file_rejected(self):
        self.mutate_nro(0x18, 0x200)
        with self.assertRaises(ValueError):
            validate_nro(self.nro)

    def test_nro_first_segment_offset_wrong_rejected(self):
        self.mutate_nro(0x20, 0x80)
        with self.assertRaises(ValueError):
            validate_nro(self.nro)

    def test_nro_ro_overlap_rejected(self):
        self.mutate_nro(0x28, 0x70)
        with self.assertRaises(ValueError):
            validate_nro(self.nro)

    def test_nro_data_overflow_rejected(self):
        self.mutate_nro(0x34, 0x400)
        with self.assertRaises(ValueError):
            validate_nro(self.nro)

    def test_nro_missing_ro_segment_rejected(self):
        self.mutate_nro(0x2C, 0)
        with self.assertRaises(ValueError):
            validate_nro(self.nro)

    def test_duplicate_receipt_boolean_key_rejected(self):
        body = self.receipt.read_text(encoding="utf-8")
        self.receipt.write_text(
            body[:-1] + ',"same_process_guest_deadzone_threshold_passed":true}',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            validate_receipt(self.receipt)

    def test_receipt_forged_guest_success_rejected(self):
        data = json.loads(self.receipt.read_text(encoding="utf-8"))
        data["same_process_guest_deadzone_threshold_passed"] = False
        self.receipt.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_receipt(self.receipt)

    def test_receipt_unexpected_raw_field_rejected(self):
        data = json.loads(self.receipt.read_text(encoding="utf-8"))
        data["private_log"] = "unapproved"
        self.receipt.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_receipt(self.receipt)

    def test_receipt_nonfinite_number_rejected(self):
        data = self.receipt.read_text(encoding="utf-8")
        self.receipt.write_text(data.replace(
            '"original_npad_serialized_sample_count": 5',
            '"original_npad_serialized_sample_count": NaN',
        ), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_receipt(self.receipt)

    def test_symlink_input_rejected(self):
        link = self.binary.parent / "alias"
        link.symlink_to(self.binary)
        with self.assertRaises(ValueError):
            audit_structure(link, self.nro, self.receipt)


if __name__ == "__main__":
    unittest.main()
