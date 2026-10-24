"""Synthetic regressions for descriptor-bound evidence reads."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stage73_safe_evidence_read import read_bounded_regular_bytes


class SafeEvidenceReadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.file = self.root / "evidence.json"
        self.file.write_bytes(b'{"valid":true}')

    def test_regular_file_read(self):
        self.assertEqual(read_bounded_regular_bytes(self.file, 128), b'{"valid":true}')

    def test_exact_size_limit(self):
        self.assertEqual(read_bounded_regular_bytes(self.file, 14), b'{"valid":true}')

    def test_oversized_file(self):
        with self.assertRaises(ValueError):
            read_bounded_regular_bytes(self.file, 13)

    def test_final_symlink(self):
        alias = self.root / "alias.json"
        alias.symlink_to(self.file)
        with self.assertRaises(ValueError):
            read_bounded_regular_bytes(alias, 128)

    def test_ancestor_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            read_bounded_regular_bytes(alias / self.file.name, 128)

    def test_parent_traversal(self):
        with self.assertRaises(ValueError):
            read_bounded_regular_bytes(self.root / "sub" / ".." / self.file.name, 128)

    def test_fifo_without_waiting_for_writer(self):
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            read_bounded_regular_bytes(fifo, 128)

    def test_path_swap_does_not_read_replacement(self):
        secret = self.root / "replacement.json"
        secret.write_bytes(b'SENSITIVE-REPLACEMENT')
        old = self.root / "original.json"
        real_read = os.read
        swapped = False

        def swap_then_read(fd, n):
            nonlocal swapped
            if not swapped:
                swapped = True
                self.file.rename(old)
                self.file.symlink_to(secret)
            return real_read(fd, n)

        with patch("stage73_safe_evidence_read.os.read", side_effect=swap_then_read):
            try:
                raw = read_bounded_regular_bytes(self.file, 128)
            except ValueError:
                return
        self.assertEqual(raw, b'{"valid":true}')

    def test_empty_file_left_for_json_parser(self):
        self.file.write_bytes(b'')
        self.assertEqual(read_bounded_regular_bytes(self.file, 128), b'')


if __name__ == "__main__":
    unittest.main()
