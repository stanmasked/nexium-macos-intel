"""Stage67 never mistake a compiled graphics NRO for actual guest rendering."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_guest_framebuffer_build import (
    EXPECTED_MARKERS, validate_compiled_public_probe, verify_graphics_source,
)


class Stage67PublicGraphicsNROTests(unittest.TestCase):
    def setUp(self):
        ctx = tempfile.TemporaryDirectory()
        self.addCleanup(ctx.cleanup)
        self.root = Path(ctx.name)
        real_source = (Path(__file__).resolve().parents[1] /
                       "probes/nexium_guest_framebuffer_probe.c")
        self.original = real_source.read_text(encoding="utf-8")
        self.source = self.root / "probe.c"
        self.source.write_text(self.original, encoding="utf-8")
        self.nro = self.root / "guest.nro"
        data = bytearray(4096)
        data[0x10:0x14] = b"NRO0"
        struct.pack_into("<I", data, 0x18, 4096)
        struct.pack_into("<6I", data, 0x20, 0, 0x80, 0x80, 0xf00, 0xf80, 0x80)
        marker_bytes = b"\0".join(
            marker.encode("ascii") for marker in EXPECTED_MARKERS
        ) + b"\0"
        self.assertLess(len(marker_bytes), 4096 - 0x200)
        data[0x200:0x200 + len(marker_bytes)] = marker_bytes
        self.nro.write_bytes(data)

    def test_source_follows_documented_libnx_window_framebuffer_order(self):
        verify_graphics_source(self.original)

    def test_structural_nro_with_all_markers_is_build_evidence_only(self):
        report = validate_compiled_public_probe(self.nro, self.source)
        self.assertTrue(report["libnx_public_graphics_probe_compiled"])
        self.assertFalse(report["guest_runtime_executed"])
        self.assertFalse(report["guest_frames_presented_verified"])
        self.assertFalse(report["production_graphics_verified"])
        self.assertFalse(report["main_merge_approved"])

    def test_removed_required_window_api_blocks_audit(self):
        self.source.write_text(self.original.replace(
            "NWindow *win = nwindowGetDefault();",
            "NWindow *win = NULL;",
        ))
        with self.assertRaises(ValueError):
            validate_compiled_public_probe(self.nro, self.source)

    def test_missing_framebuffer_end_blocks_source(self):
        self.source.write_text(self.original.replace(
            "framebufferEnd(&fb);",
            "/* removed submission */",
        ))
        with self.assertRaises(ValueError):
            verify_graphics_source(self.source.read_text())

    def test_missing_stage_success_marker_blocks(self):
        self.source.write_text(self.original.replace(
            "STAGE67_GUEST_FOUR_FRAMEBUFFER_CALLS_COMPLETE",
            "WRONG_GUEST_SUCCESS_MARKER",
        ))
        with self.assertRaises(ValueError):
            verify_graphics_source(self.source.read_text())

    def test_missing_compiled_framebuffer_marker_blocks(self):
        data = self.nro.read_bytes().replace(
            b"STAGE67_GUEST_LINEAR_BUFFER_READY",
            b"STAGE67_GUEST_LINEAR_BUFFER_WRONG",
        )
        self.nro.write_bytes(data)
        with self.assertRaises(ValueError):
            validate_compiled_public_probe(self.nro, self.source)

    def test_broken_nro_magic_blocks(self):
        data = bytearray(self.nro.read_bytes())
        data[0x10:0x14] = b"FAKE"
        self.nro.write_bytes(data)
        with self.assertRaises(ValueError):
            validate_compiled_public_probe(self.nro, self.source)

    def test_nro_symlink_blocks(self):
        alias = self.root / "alias.nro"
        alias.symlink_to(self.nro)
        with self.assertRaises(ValueError):
            validate_compiled_public_probe(alias, self.source)

    def test_source_symlink_blocks(self):
        alias = self.root / "alias.c"
        alias.symlink_to(self.source)
        with self.assertRaises(ValueError):
            validate_compiled_public_probe(self.nro, alias)

    def test_raw_compiled_markers_are_not_runtime_observations(self):
        x = validate_compiled_public_probe(self.nro, self.source)
        self.assertTrue(x["source_authentic_libnx_api_calls_verified"])
        self.assertFalse(x["macos_window_pixels_verified"])
        self.assertFalse(x["guest_framebuffer_initialized"])


if __name__ == "__main__":
    unittest.main()
