"""Stage73 exact scoped IPC request logging patch and source identity checks."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_macos_display_ipc_trace import (
    ANCHOR, REPLACEMENT, PINNED_UPSTREAM_COMMIT, SOURCE_RELATIVE_PATH,
    git_blob_sha, patch_scoped_ipc_request_log,
)


class Stage73ScopedIpcPatchTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.path = self.root / SOURCE_RELATIVE_PATH
        self.path.parent.mkdir(parents=True)
        self.receipt = self.root / "receipt" / "display-ipc.json"
        self.original = (
            "fn send_sync_request() {\n" + ANCHOR +
            "\n        dispatch_request();\n"
            "        log::trace!(\"SVC {:#04x}\", imm);\n"
            "}\n"
        )
        self.path.write_text(self.original)

    def patch(self, expected=None):
        if expected is None:
            expected = git_blob_sha(self.path.read_bytes())
        return patch_scoped_ipc_request_log(
            self.root, self.receipt, expected_blob_sha=expected
        )

    def test_only_one_ipc_request_log_level_changes(self):
        report = self.patch()
        changed = self.path.read_text()
        self.assertEqual(changed.count(REPLACEMENT), 1)
        self.assertNotIn(ANCHOR, changed)
        self.assertIn('log::trace!("SVC {:#04x}", imm);', changed)
        self.assertEqual(report["upstream_commit"], PINNED_UPSTREAM_COMMIT)
        self.assertTrue(report["only_ipc_request_log_level_changed"])
        self.assertFalse(report["guest_or_service_behavior_changed"])
        self.assertFalse(report["main_merge_approved"])
        self.assertEqual(json.loads(self.receipt.read_text()), report)

    def test_wrong_source_blob_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            self.patch("f" * 40)
        self.assertEqual(self.path.read_text(), self.original)
        self.assertFalse(self.receipt.exists())

    def test_missing_anchor_rejected(self):
        self.path.write_text("fn send_sync_request() {}\n")
        with self.assertRaisesRegex(ValueError, "anchor must match"):
            self.patch()

    def test_duplicate_anchor_rejected(self):
        self.path.write_text(self.original + ANCHOR + "\n")
        with self.assertRaisesRegex(ValueError, "anchor must match"):
            self.patch()

    def test_symlinked_source_rejected(self):
        other = self.root / "svc-real.rs"
        other.write_text(self.original)
        self.path.unlink()
        self.path.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "missing, linked"):
            self.patch()

    def test_linked_source_root_rejected(self):
        alias = self.root / "source-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "root is missing or linked"):
            patch_scoped_ipc_request_log(
                alias, self.receipt, expected_blob_sha=git_blob_sha(self.path.read_bytes())
            )

    def test_unexpected_upstream_blob_does_not_mutate_file(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            self.patch("0" * 40)
        self.assertEqual(self.path.read_bytes(), before)

    def test_native_build_applies_scoped_patch_and_binds_receipt_before_cargo(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = (repo_root / "macos_probe.sh").read_text(encoding="utf-8")
        builder = (repo_root / "scripts" / "build_intel_merged_tree.py").read_text(
            encoding="utf-8"
        )
        call = 'python3 "$SELF/scripts/apply_macos_display_ipc_trace.py"'
        self.assertEqual(script.count(call), 1)
        call_at = script.index(call)
        stage53_patch_at = script.index(
            'python3 "$SELF/scripts/apply_macos_guest_deadzone_threshold.py"'
        )
        rustup_at = script.index("rustup target add x86_64-apple-darwin")
        cargo_at = script.index("cargo rustc --release --target x86_64-apple-darwin")
        self.assertLess(stage53_patch_at, call_at)
        self.assertLess(call_at, rustup_at)
        self.assertLess(rustup_at, cargo_at)
        self.assertIn('if [[ "${NEXIUM_DISPLAY_IPC_TRACE:-0}" == "1" ]]; then', script)
        self.assertIn('--source-root "$SRC"', script[call_at:call_at + 300])
        self.assertIn('--receipt "$WORK/display-ipc-trace-patch.json"', script[call_at:call_at + 300])
        self.assertIn(
            'trace_receipt_path = work_dir / "display-ipc-trace-patch.json"',
            builder,
        )
        self.assertIn(
            'base_env.get("NEXIUM_DISPLAY_IPC_TRACE") == "1"',
            builder,
        )
        native_workflow = (
            repo_root / ".github" / "workflows"
            / "nexium-intel-display-ipc-path-native.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("paths-ignore:", native_workflow)
        for ignored_path in (
            ".github/workflows/nexium-intel-display-ipc-path-diagnostics.yml",
            ".github/workflows/nexium-intel-display-ipc-path-native.yml",
            "tests/test_stage73_display_ipc_path.py",
            "tests/test_stage73_scoped_ipc_patch.py",
        ):
            self.assertIn(f"- '{ignored_path}'", native_workflow)
    def test_receipt_does_not_claim_runtime_or_gpu_success(self):
        report = self.patch()
        self.assertFalse(report.get("guest_gpu_frames_verified", False))
        self.assertFalse(report.get("main_merge_approved", False))
        self.assertFalse(report.get("raw_logs_uploaded", True))


if __name__ == "__main__":
    unittest.main()
