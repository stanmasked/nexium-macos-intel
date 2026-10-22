"""Stage63 synthetic tests for private, bounded virtual-source extraction."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tarfile
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from test_intel_integrated_tree import (
    unpack_reviewed_tree, execute_integrated_tests,
)


def archive_of(items):
    stream = BytesIO()
    with tarfile.open(mode="w", fileobj=stream) as output:
        for name, value, kind in items:
            info = tarfile.TarInfo(name)
            if kind == "file":
                contents = value.encode("utf-8")
                info.size = len(contents)
                output.addfile(info, BytesIO(contents))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                output.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = value
                output.addfile(info)
            else:
                raise ValueError("unknown synthetic archive type")
    return stream.getvalue()


class Stage63IntegratedTreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_normal_source_archive_extracts_only_regular_files(self):
        data = archive_of([
            ("scripts/", "", "dir"),
            ("scripts/hello.py", "print('hello')\n", "file"),
        ])
        count = unpack_reviewed_tree(data, self.root)
        self.assertEqual(count, 1)
        self.assertEqual((self.root / "scripts/hello.py").read_text(),
                         "print('hello')\n")

    def test_parent_path_rejected(self):
        data = archive_of([("../bad.py", "unsafe\n", "file")])
        with self.assertRaisesRegex(ValueError, "unsafe Git archive"):
            unpack_reviewed_tree(data, self.root)

    def test_absolute_path_rejected(self):
        data = archive_of([("/bad.py", "unsafe\n", "file")])
        with self.assertRaisesRegex(ValueError, "unsafe Git archive"):
            unpack_reviewed_tree(data, self.root)

    def test_symlink_rejected(self):
        data = archive_of([("scripts/not-real.py", "../secret", "symlink")])
        with self.assertRaisesRegex(ValueError, "unsupported Git archive"):
            unpack_reviewed_tree(data, self.root)

    def test_duplicate_file_rejected(self):
        data = archive_of([
            ("dup.txt", "a", "file"),
            ("dup.txt", "b", "file"),
        ])
        with self.assertRaises(FileExistsError):
            unpack_reviewed_tree(data, self.root)

    def test_oversized_archive_rejected(self):
        with self.assertRaisesRegex(ValueError, "oversized"):
            unpack_reviewed_tree(b"x" * (48 * 1024 * 1024 + 1), self.root)

    def test_integrated_fixture_unittest_passes(self):
        scripts = self.root / "scripts"
        tests = self.root / "tests"
        scripts.mkdir()
        tests.mkdir()
        (scripts / "rehearse_intel_reviewed_conflict.py").write_text(
            "print('synthetic')\n"
        )
        (tests / "test_demo.py").write_text(
            "import unittest\n"
            "class TestDemo(unittest.TestCase):\n"
            "    def test_ok(self): self.assertTrue(True)\n"
        )
        result = execute_integrated_tests(self.root, min_tests=1)
        self.assertTrue(result["integrated_python_tests_passed"])
        self.assertEqual(result["integrated_python_test_count"], 1)

    def test_integrated_test_count_reduction_rejected(self):
        scripts = self.root / "scripts"
        tests = self.root / "tests"
        scripts.mkdir()
        tests.mkdir()
        (scripts / "rehearse_intel_reviewed_conflict.py").write_text(
            "pass\n"
        )
        (tests / "test_demo.py").write_text(
            "import unittest\n"
            "class TestDemo(unittest.TestCase):\n"
            "    def test_ok(self): self.assertTrue(True)\n"
        )
        with self.assertRaisesRegex(ValueError, "unexpectedly reduced"):
            execute_integrated_tests(self.root, min_tests=2)

    def test_missing_integrated_rehearsal_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "source not found"):
            execute_integrated_tests(self.root, min_tests=1)


if __name__ == "__main__":
    unittest.main()
