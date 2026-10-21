"""Fail closed if the Stage40 Intel NRO job silently selects the wrong CPU.

The Stage40 GUI is built with backend-rustarmic only, while normal GUI
settings default to Dynarmic. This source-level contract prevents another
successful native compilation followed by a failed guest CPU initialization.
It does not assert that any guest instructions were executed.
"""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/nexium-macos-probe.yml"
STEP_BEGIN = "      - name: Run guest NRO with sustained synthetic B and safe HID diagnostics"
STEP_END = "      - name: Require guest-visible B press/release and mapped HID report"

REQUIRED = (
    "NEXIUM_CPU_BACKEND=rustarmic",
    "NEXIUM_MACOS_GUEST_HID_PROBE=1",
    "NEXIUM_MACOS_STAGE37_HID_BRIDGE_TRACE=1",
    "NEXIUM_DIAG=lite",
    "NEXIUM_LOG_LEVEL=debug",
    "python3 scripts/nro_smoke_test.py",
    "--nro stage40-probe/nexium-guest-hid-probe.nro",
)


def validate_stage40_shell(workflow: str) -> None:
    """Validate only the real Stage40 script, not unrelated workflow jobs."""
    if workflow.count(STEP_BEGIN) != 1 or workflow.count(STEP_END) != 1:
        raise ValueError("Stage40 runtime step missing or ambiguous")
    step = workflow.split(STEP_BEGIN, 1)[1].split(STEP_END, 1)[0]
    if "backend: [rustarmic]" not in workflow:
        raise ValueError("Stage40 expects the Rustarmic-only Intel build")

    lines = step.splitlines()
    starts = [i for i, line in enumerate(lines)
              if line.strip().startswith("env NEXIUM_CPU_BACKEND=")]
    if len(starts) != 1:
        raise ValueError("Stage40 must explicitly set exactly one CPU backend")
    start = starts[0]
    stops = [i for i in range(start, len(lines))
             if lines[i].strip() == "--snapshot-ms 5000"]
    if len(stops) != 1:
        raise ValueError("Stage40 guest smoke command missing or ambiguous")
    end = stops[0]
    command = lines[start:end + 1]
    for line in command[:-1]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.endswith("\\"):
            raise ValueError("Stage40 shell env invocation was interrupted")
    if command[-1].strip().endswith("\\"):
        raise ValueError("Stage40 smoke command must terminate normally")

    collapsed = " ".join(line.strip().rstrip("\\").strip() for line in command)
    for required in REQUIRED:
        if collapsed.count(required) != 1:
            raise ValueError(f"Stage40 runtime contract missing/duplicated: {required}")
    if not collapsed.startswith("env NEXIUM_CPU_BACKEND=rustarmic "):
        raise ValueError("Stage40 CPU backend must be in the actual env invocation")
    if "NEXIUM_CPU_BACKEND=dynarmic" in collapsed:
        raise ValueError("Stage40 may not select uncompiled Dynarmic")


class Stage40RuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_live_workflow_uses_compiled_rustarmic(self):
        validate_stage40_shell(self.workflow)

    def test_missing_cpu_backend_is_rejected(self):
        broken = self.workflow.replace(
            "env NEXIUM_CPU_BACKEND=rustarmic",
            "env NEXIUM_MACOS_NO_AUDIO=1",
            1,
        )
        with self.assertRaises(ValueError):
            validate_stage40_shell(broken)

    def test_dynarmic_default_regression_is_rejected(self):
        broken = self.workflow.replace(
            "env NEXIUM_CPU_BACKEND=rustarmic",
            "env NEXIUM_CPU_BACKEND=dynarmic",
            1,
        )
        with self.assertRaises(ValueError):
            validate_stage40_shell(broken)

    def test_comment_inside_multiline_env_is_rejected(self):
        broken = self.workflow.replace(
            "            NEXIUM_HID_TRACE=1 \\\n            NEXIUM_DIAG=lite",
            "            NEXIUM_HID_TRACE=1 \\\n            # accidental shell command split\n            NEXIUM_DIAG=lite",
            1,
        )
        self.assertNotEqual(broken, self.workflow)
        with self.assertRaisesRegex(ValueError, "interrupted"):
            validate_stage40_shell(broken)

    def test_debug_svc_flag_removal_is_rejected(self):
        broken = self.workflow.replace(
            "NEXIUM_DIAG=lite",
            "NEXIUM_DIAG=0",
            1,
        )
        with self.assertRaises(ValueError):
            validate_stage40_shell(broken)


if __name__ == "__main__":
    unittest.main()
