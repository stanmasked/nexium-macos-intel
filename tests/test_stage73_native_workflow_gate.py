"""Fail-closed policy tests for the Stage73 native workflow gate."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/nexium-intel-display-ipc-path-native.yml"


def job_block(source, job_name, next_job_name):
    start = source.index(f"  {job_name}:")
    end = source.index(f"  {next_job_name}:", start)
    return source[start:end]


class Stage73NativeWorkflowGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.gate = job_block(
            cls.source, "private-archive-readiness", "prepare-public-framebuffer-nro"
        )
        cls.prepare = job_block(
            cls.source, "prepare-public-framebuffer-nro", "integrated-intel-guest-graphics"
        )
        cls.graphics = cls.source[cls.source.index("  integrated-intel-guest-graphics:"):]

    def test_private_archive_gate_runs_before_nro_preparation(self):
        self.assertIn("needs: [private-archive-readiness]", self.prepare)
        self.assertIn(
            "needs.private-archive-readiness.outputs.archive_ready == 'true'",
            self.prepare,
        )
        self.assertNotIn("needs.prepare-public-framebuffer-nro", self.gate)

    def test_unverified_archive_is_explicitly_false(self):
        self.assertIn('echo "archive_ready=false" >> "$GITHUB_OUTPUT"', self.gate)
        self.assertIn("refusing to create a new raw capture", self.gate)

    def test_gate_has_no_checkout_or_private_credential(self):
        self.assertNotIn("actions/checkout@", self.gate)
        self.assertNotIn("NEXIUM_DRIVE_ACCESS_TOKEN", self.gate)
        self.assertNotIn("secrets.", self.gate)

    def test_native_graphics_requires_archive_gate(self):
        self.assertIn(
            "needs: [prepare-public-framebuffer-nro, private-archive-readiness]",
            self.graphics,
        )
        self.assertIn(
            "needs.private-archive-readiness.outputs.archive_ready == 'true'",
            self.graphics,
        )

    def test_native_gate_is_not_opened_by_workflow_success_alone(self):
        self.assertIn("archive_ready=false", self.source)
        self.assertIn("archive upload is not wired into this workflow yet", self.source)


if __name__ == "__main__":
    unittest.main()
