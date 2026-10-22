"""Stage72 public pinned source, literal service stub, and blob security gates."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_intel_pinned_graphics_services import (
    PINNED_BLOBS, git_blob_sha, inspect_pinned_graphics_sources,
    read_exact_public_sources,
)


def synthetic_sources():
    return {
        "nexium-kernel/src/services/vi.rs": (
            'framebuffer_queue: Arc<Mutex<Vec<Vec<u8>>>>\n'
            'match cmd_id { _ => { log::warn!("VI.cmd_{} UNHANDLED"); SUCCESS } }\n'
        ),
        "nexium-kernel/src/services/nvnflinger.rs": (
            'REQUEST_BUFFER | DEQUEUE_BUFFER => {\n'
            ' log::trace!("IGBP buffer op {}", transaction_code); SUCCESS }\n'
            'match cmd_id { _ => { log::info!("nvnflinger stub command: {}", cmd_id); SUCCESS } }\n'
            'pixels: vec![0x10u8; pixel_count * 4]\n'
        ),
        "nexium-kernel/src/services/application_display_service/handlers.rs": (
            'pub fn open_layer(_kernel: &mut Kernel, _ctx: &mut IpcCtx, _session: u32) '
            '-> u64 { NATIVE_WINDOW_PARCEL_SIZE }\n'
        ),
        "nexium-kernel/src/services/vi_root_service/handlers.rs": (
            'pub fn get_display_service_u_from_root(_k: &mut Kernel, _c: &mut IpcCtx, '
            '_s: u32) {}\n'
        ),
        "nexium-kernel/src/services/sm.rs": (
            '"vi:m", "vi:s", "vi:u", "nvdrv"\n'
        ),
    }


class Stage72PinnedGraphicsServiceTests(unittest.TestCase):
    def setUp(self):
        ctx = tempfile.TemporaryDirectory()
        self.addCleanup(ctx.cleanup)
        self.root = Path(ctx.name)
        self.sources = synthetic_sources()
        self.sha = {}
        for path, text in self.sources.items():
            f = self.root / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
            self.sha[path] = git_blob_sha(f.read_bytes())

    def test_synthetic_exact_blob_sources_classify_all_risks(self):
        checked = read_exact_public_sources(self.root, expected=self.sha)
        report = inspect_pinned_graphics_sources(checked)
        self.assertTrue(report["source_blob_digests_verified"])
        self.assertTrue(report["vi_unhandled_command_returns_success"])
        self.assertTrue(report["binder_fallback_frame_is_constant_fill"])
        self.assertFalse(report["runtime_graphics_failure_cause_confirmed"])
        self.assertFalse(report["guest_gpu_frames_verified"])
        self.assertFalse(report["main_merge_approved"])

    def test_stage72_expected_upstream_git_pin_has_five_exact_blobs(self):
        self.assertEqual(len(PINNED_BLOBS), 5)
        self.assertTrue(all(len(value) == 40 for value in PINNED_BLOBS.values()))

    def test_any_source_change_invalidates_sha_binding(self):
        path = next(iter(self.sha))
        f = self.root / path
        f.write_text(f.read_text() + "// unexpected\n")
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            read_exact_public_sources(self.root, expected=self.sha)

    def test_vi_fallback_semantic_change_detected_even_if_blob_reauthorized(self):
        self.sources["nexium-kernel/src/services/vi.rs"] = (
            self.sources["nexium-kernel/src/services/vi.rs"]
            .replace('SUCCESS }', 'NOT_IMPLEMENTED }')
        )
        with self.assertRaisesRegex(ValueError, "contracts changed"):
            inspect_pinned_graphics_sources(self.sources)

    def test_missing_root_vi_stub_not_mistaken_for_complete_service(self):
        key = "nexium-kernel/src/services/vi_root_service/handlers.rs"
        self.sources[key] = self.sources[key].replace(" {}", " { implemented(); }")
        with self.assertRaisesRegex(ValueError, "contracts changed"):
            inspect_pinned_graphics_sources(self.sources)

    def test_missing_constant_fallback_pixel_not_claimed(self):
        key = "nexium-kernel/src/services/nvnflinger.rs"
        self.sources[key] = self.sources[key].replace("vec![0x10u8", "vec![0x77u8")
        with self.assertRaisesRegex(ValueError, "contracts changed"):
            inspect_pinned_graphics_sources(self.sources)

    def test_unregistered_vi_name_is_not_claimed(self):
        key = "nexium-kernel/src/services/sm.rs"
        self.sources[key] = self.sources[key].replace('"vi:u"', '"different"')
        with self.assertRaisesRegex(ValueError, "contracts changed"):
            inspect_pinned_graphics_sources(self.sources)

    def test_symlinked_public_source_is_rejected(self):
        key = "nexium-kernel/src/services/vi.rs"
        original = self.root / key
        other = self.root / "vi-copy.rs"
        original.rename(other)
        original.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "missing/oversized/linked"):
            read_exact_public_sources(self.root, expected=self.sha)

    def test_mismatched_pinned_expected_digest_rejected(self):
        values = dict(self.sha)
        values[next(iter(values))] = "f" * 40
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            read_exact_public_sources(self.root, expected=values)

    def test_malformed_pinned_expected_digest_rejected(self):
        values = dict(self.sha)
        values[next(iter(values))] = "wrong"
        with self.assertRaisesRegex(ValueError, "malformed"):
            read_exact_public_sources(self.root, expected=values)

    def test_missing_one_public_source_is_rejected(self):
        self.sources.pop("nexium-kernel/src/services/nvnflinger.rs")
        with self.assertRaisesRegex(ValueError, "missing pinned"):
            inspect_pinned_graphics_sources(self.sources)


if __name__ == "__main__":
    unittest.main()
