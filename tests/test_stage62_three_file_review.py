"""Stage62 isolated Git tests of three pinned Stage58 source resolutions."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse_intel_pr_merge import conflicted_filenames, git
from rehearse_intel_reviewed_conflict import (
    REVIEWED_PR60_BLOBS, substitute_reviewed_pr60_blobs,
)


def ok(r):
    if r.returncode != 0:
        raise RuntimeError("synthetic Stage62 Git fixture failed")
    return r.stdout.strip()


class Stage62ThreeFileReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.sources = {}
        ok(git(self.repo, "init", "-q"))
        for path in REVIEWED_PR60_BLOBS:
            data = (Path(__file__).resolve().parents[1] / path).read_text(
                encoding="utf-8"
            )
            self.sources[path] = data
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data, encoding="utf-8")
        ok(git(self.repo, "add", "."))
        ok(git(self.repo, "commit", "-q", "-m", "reviewed Stage58 sources"))
        self.base = ok(git(self.repo, "rev-parse", "HEAD"))
        for path, sha in REVIEWED_PR60_BLOBS.items():
            self.assertEqual(ok(git(self.repo, "rev-parse",
                                    self.base + ":" + path)), sha)

    def conflict_tree(self):
        # Two independent changes to the *same start* of each source file.
        for p, data in self.sources.items():
            (self.repo / p).write_text("left\n" + data, encoding="utf-8")
        ok(git(self.repo, "add", "."))
        ok(git(self.repo, "commit", "-q", "-m", "virtual left"))
        left = ok(git(self.repo, "rev-parse", "HEAD"))
        ok(git(self.repo, "checkout", "-q", "--detach", self.base))
        for p, data in self.sources.items():
            (self.repo / p).write_text("right\n" + data, encoding="utf-8")
        ok(git(self.repo, "add", "."))
        ok(git(self.repo, "commit", "-q", "-m", "virtual right"))
        right = ok(git(self.repo, "rev-parse", "HEAD"))
        merge = git(self.repo, "merge-tree", "--write-tree",
                    "--name-only", left, right)
        self.assertEqual(merge.returncode, 1)
        paths = conflicted_filenames(merge.stdout)
        self.assertEqual(paths, sorted(REVIEWED_PR60_BLOBS))
        return merge.stdout.splitlines()[0], paths

    def test_three_exact_reviewed_blobs_can_be_inserted_locally(self):
        tree, paths = self.conflict_tree()
        current_head = ok(git(self.repo, "rev-parse", "HEAD"))
        result = substitute_reviewed_pr60_blobs(
            self.repo, tree, paths, dict(REVIEWED_PR60_BLOBS),
        )
        for path, sha in REVIEWED_PR60_BLOBS.items():
            self.assertEqual(ok(git(self.repo, "rev-parse", result + ":" + path)),
                             sha)
        self.assertEqual(ok(git(self.repo, "rev-parse", "HEAD")), current_head)

    def test_wrong_file_set_is_blocked(self):
        tree, paths = self.conflict_tree()
        with self.assertRaisesRegex(ValueError, "unexpected Stage58"):
            substitute_reviewed_pr60_blobs(
                self.repo, tree, paths[:2], dict(REVIEWED_PR60_BLOBS),
            )

    def test_modified_blob_digest_is_rejected(self):
        tree, paths = self.conflict_tree()
        corrupted = dict(REVIEWED_PR60_BLOBS)
        corrupted[paths[0]] = "a" * 40
        with self.assertRaisesRegex(ValueError, "unexpected Stage58"):
            substitute_reviewed_pr60_blobs(self.repo, tree, paths, corrupted)

    def test_unknown_extra_conflict_is_not_auto_resolved(self):
        tree, paths = self.conflict_tree()
        with self.assertRaisesRegex(ValueError, "unexpected Stage58"):
            substitute_reviewed_pr60_blobs(
                self.repo, tree, paths + ["scripts/not-reviewed.py"],
                dict(REVIEWED_PR60_BLOBS),
            )


if __name__ == "__main__":
    unittest.main()
