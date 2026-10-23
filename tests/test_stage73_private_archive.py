"""Synthetic tests for private Stage73 archive integrity."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from seal_private_capture import (
    ArchiveRejected, build_manifest, write_manifest, verify_manifest,
    main, MAX_FILE_BYTES, MAX_FILES,
)

SHA, MACHO, NRO = "a" * 40, "b" * 64, "c" * 64


class Stage73PrivateArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report"
        self.report.mkdir()
        self.log = self.report / "data-root/logs/nexium-synthetic.log"
        self.log.parent.mkdir(parents=True)
        self.log.write_bytes(b"synthetic log placeholder")
        (self.report / "smoke_result.json").write_text("{}")
        self.manifest = self.root / "manifest.json"

    def seal(self):
        result = build_manifest(self.report, SHA, MACHO, NRO)
        write_manifest(self.manifest, result, self.report)
        return result

    def test_success_is_local_only(self):
        result = self.seal()
        verify_manifest(self.report, self.manifest)
        self.assertFalse(result["remote_verified"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o600)

    def test_modified_log_rejected(self):
        self.seal()
        self.log.write_bytes(b"modified")
        with self.assertRaises(ArchiveRejected):
            verify_manifest(self.report, self.manifest)

    def test_deleted_log_rejected(self):
        self.seal()
        self.log.unlink()
        with self.assertRaises(ArchiveRejected):
            verify_manifest(self.report, self.manifest)

    def test_new_extra_file_rejected(self):
        self.seal()
        (self.report / "extra").write_text("synthetic")
        with self.assertRaises(ArchiveRejected):
            verify_manifest(self.report, self.manifest)

    def test_symlinked_log_rejected(self):
        self.log.unlink()
        outside = self.root / "outside"
        outside.write_bytes(b"synthetic")
        self.log.symlink_to(outside)
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_symlinked_dir_rejected(self):
        (self.report / "alias").symlink_to(self.log.parent, target_is_directory=True)
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_symlinked_root_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.report, target_is_directory=True)
        with self.assertRaises(ArchiveRejected):
            build_manifest(alias, SHA, MACHO, NRO)

    def test_hardlink_rejected(self):
        os.link(self.log, self.root / "hardlink")
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_missing_log_rejected(self):
        self.log.unlink()
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_multiple_logs_rejected(self):
        (self.log.parent / "nexium-extra.log").write_text("synthetic")
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_large_file_rejected(self):
        with self.log.open("r+b") as handle:
            handle.truncate(MAX_FILE_BYTES + 1)
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_many_files_rejected(self):
        for n in range(MAX_FILES):
            (self.report / f"extra{n}").write_text("a")
        with self.assertRaises(ArchiveRejected):
            self.seal()

    def test_manifest_inside_capture_rejected(self):
        data = build_manifest(self.report, SHA, MACHO, NRO)
        with self.assertRaises(ArchiveRejected):
            write_manifest(self.report / "manifest.json", data, self.report)

    def test_manifest_traversal_rejected(self):
        data = self.seal()
        data["files"][0]["path"] = "../outside"
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ArchiveRejected):
            verify_manifest(self.report, self.manifest)

    def test_invalid_identity_rejected(self):
        with self.assertRaises(ArchiveRejected):
            build_manifest(self.report, "wrong", MACHO, NRO)

    def test_failure_never_prints_private_content(self):
        self.seal()
        self.log.write_text("PRIVATE SECRET")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["verify", "--report", str(self.report),
                                   "--manifest", str(self.manifest)]), 1)
        self.assertEqual(stderr.getvalue(), "STAGE73_PRIVATE_MANIFEST_REJECTED\n")

    def test_success_marker_distinguishes_local(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["seal", "--report", str(self.report),
                                   "--manifest", str(self.manifest),
                                   "--source-commit", SHA,
                                   "--macho-sha256", MACHO, "--nro-sha256", NRO]), 0)
        self.assertEqual(stdout.getvalue(), "STAGE73_PRIVATE_MANIFEST_SEALED_LOCAL_ONLY\n")


if __name__ == "__main__":
    unittest.main()
