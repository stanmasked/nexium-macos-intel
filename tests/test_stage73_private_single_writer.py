"""Private single-writer locking, using only synthetic local fixtures."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from archive_private_capture_drive import DriveArchiveRejected
from stage73_private_single_writer import LOCK_NAME, private_single_writer_lock
from rehearse_stage73_private_drive import run_synthetic_rehearsal


class Stage73PrivateSingleWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / "backup-parent"
        self.b = self.root / "reference-parent"
        self.a.mkdir()
        self.b.mkdir()
        self.backup = self.a / "anchor.json"
        self.reference = self.b / "reference.json"
        self.lock = self.a / LOCK_NAME

    def test_private_lock_file_persists_between_runs(self):
        with private_single_writer_lock(self.backup):
            info = self.lock.stat()
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(info.st_nlink, 1)
            self.assertEqual(info.st_size, 0)
        self.assertTrue(self.lock.is_file())

    def test_simultaneous_second_lock_refused_without_wait(self):
        with private_single_writer_lock(self.backup):
            with self.assertRaisesRegex(DriveArchiveRejected, "single_writer_lock_unavailable"):
                with private_single_writer_lock(self.backup):
                    self.fail("second writer obtained contested lock")

    def test_contended_rehearsal_refused_before_any_drive_call(self):
        transport = Mock()
        with private_single_writer_lock(self.backup):
            with self.assertRaisesRegex(DriveArchiveRejected, "single_writer_lock_unavailable"):
                run_synthetic_rehearsal(
                    transport, "A" * 24, "B" * 24, "123", "a" * 40,
                    self.backup, self.reference)
        transport.call.assert_not_called()
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.reference.exists())

    def test_same_lock_parent_serializes_different_run_ids(self):
        with private_single_writer_lock(self.backup):
            with self.assertRaisesRegex(DriveArchiveRejected, "single_writer_lock_unavailable"):
                with private_single_writer_lock(self.a / "other-run.json"):
                    pass

    def test_different_process_cannot_acquire_contended_lock(self):
        # A distinct Python interpreter must observe the kernel flock.
        child = (
            "import sys\n"
            "from stage73_private_single_writer import private_single_writer_lock\n"
            "from archive_private_capture_drive import DriveArchiveRejected\n"
            "try:\n"
            "    with private_single_writer_lock(sys.argv[1]):\n"
            "        sys.exit(0)\n"
            "except DriveArchiveRejected:\n"
            "    sys.exit(42)\n"
        )
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        with private_single_writer_lock(self.backup):
            result = subprocess.run(
                [sys.executable, "-c", child, str(self.backup)],
                cwd=scripts, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=8, check=False,
            )
        self.assertEqual(result.returncode, 42)
        self.assertTrue(self.lock.is_file())
        self.assertFalse(self.backup.exists())

    def test_lock_recovers_after_forced_child_termination(self):
        # The child announces acquisition via an unrelated synthetic marker.
        # After SIGKILL, the kernel must release its flock automatically.
        marker = self.root / "child-acquired-lock.marker"
        child = (
            "from pathlib import Path\n"
            "import sys, time\n"
            "from stage73_private_single_writer import private_single_writer_lock\n"
            "with private_single_writer_lock(Path(sys.argv[1])):\n"
            "    Path(sys.argv[2]).write_bytes(b'locked')\n"
            "    time.sleep(30)\n"
        )
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        proc = subprocess.Popen(
            [sys.executable, "-c", child, str(self.backup), str(marker)],
            cwd=scripts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 6
            while not marker.exists() and time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
            self.assertEqual(marker.read_bytes(), b"locked")
            self.assertIsNone(proc.poll())
            with self.assertRaisesRegex(DriveArchiveRejected, "single_writer_lock_unavailable"):
                with private_single_writer_lock(self.backup):
                    self.fail("parent unexpectedly acquired child-held flock")
            proc.kill()
            proc.wait(timeout=5)
            with private_single_writer_lock(self.backup):
                self.assertTrue(self.lock.is_file())
                self.assertFalse(self.backup.exists())
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def test_lock_is_released_after_failed_run(self):
        with self.assertRaisesRegex(ValueError, "synthetic"):
            with private_single_writer_lock(self.backup):
                raise ValueError("synthetic")
        with private_single_writer_lock(self.backup):
            self.assertTrue(self.lock.is_file())

    def test_symlinked_lock_rejected_before_touching_target(self):
        target = self.root / "valuable"
        target.write_bytes(b"keep")
        self.lock.symlink_to(target)
        with self.assertRaises(DriveArchiveRejected):
            with private_single_writer_lock(self.backup):
                pass
        self.assertEqual(target.read_bytes(), b"keep")

    def test_hardlink_lock_rejected(self):
        target = self.root / "shared-inode"
        target.write_bytes(b"")
        target.chmod(0o600)
        os.link(target, self.lock)
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_single_writer_lock"):
            with private_single_writer_lock(self.backup):
                pass

    def test_group_writable_parent_rejected(self):
        self.a.chmod(0o770)
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_single_writer_parent"):
            with private_single_writer_lock(self.backup):
                pass
        self.assertFalse(self.lock.exists())

    def test_permissive_existing_lock_rejected(self):
        self.lock.touch()
        self.lock.chmod(0o644)
        with self.assertRaisesRegex(DriveArchiveRejected, "unsafe_single_writer_lock"):
            with private_single_writer_lock(self.backup):
                pass


if __name__ == "__main__":
    unittest.main()
