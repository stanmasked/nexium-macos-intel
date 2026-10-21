"""Stage51 tests for explicit branch-neutral controller diagnostic selection."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "scripts" / "intel_controller_input_profile.sh"
MACOS = ROOT / "macos_probe.sh"
REQUIRED = (
    "NEXIUM_EXPERIMENT_SDL3_INPUT_ABLATION",
    "NEXIUM_EXPERIMENT_SDL3_PREWINIT",
    "NEXIUM_EXPERIMENT_INPUT_POLL_MARKERS",
    "NEXIUM_EXPERIMENT_VIRTUAL_INPUT_SNAPSHOT",
    "NEXIUM_EXPERIMENT_STAGE37_HID_BRIDGE",
    "NEXIUM_EXPERIMENT_STAGE40_GUEST_HID",
    "NEXIUM_EXPERIMENT_STAGE42_GUEST_AB",
    "NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD",
    "NEXIUM_EXPERIMENT_STAGE44_GUEST_STICK_X",
    "NEXIUM_EXPERIMENT_STAGE45_GUEST_STICK_Y",
    "NEXIUM_EXPERIMENT_STAGE46_GUEST_RIGHT_X",
    "NEXIUM_EXPERIMENT_STAGE47_GUEST_RIGHT_Y",
    "NEXIUM_EXPERIMENT_STAGE48_DUAL_STICK",
)


def run_profile(overrides=None):
    env = os.environ.copy()
    for key in (*REQUIRED, "NEXIUM_INTEL_INPUT_PROFILE"):
        env.pop(key, None)
    env["GITHUB_HEAD_REF"] = "feature/arbitrary-unlisted-branch"
    env.update(overrides or {})
    env["EXPECTED_FLAGS"] = " ".join(REQUIRED)
    script = (
        'source "$1"\n'
        'for key in ${EXPECTED_FLAGS}; do printf "%s=%s\\n" "$key" "${!key-unset}"; done\n'
    )
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script, "stage51-test", str(PROFILE)],
        env=env, text=True, capture_output=True, check=False,
    )


class Stage51ControllerProfileTests(unittest.TestCase):
    def test_explicit_optin_enables_all_13_flags_on_arbitrary_branch(self):
        result = run_profile({"NEXIUM_INTEL_INPUT_PROFILE": "controller-diagnostics-v1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NEXIUM_INTEL_CONTROLLER_DIAGNOSTICS_PROFILE_V1_ENABLED", result.stdout)
        for key in REQUIRED:
            self.assertIn(f"{key}=1\n", result.stdout)

    def test_absent_profile_does_not_change_any_flags(self):
        result = run_profile()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("DIAGNOSTICS_PROFILE", result.stdout)
        for key in REQUIRED:
            self.assertIn(f"{key}=unset\n", result.stdout)

    def test_explicit_off_preserves_default(self):
        result = run_profile({"NEXIUM_INTEL_INPUT_PROFILE": "off"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("DIAGNOSTICS_PROFILE", result.stdout)

    def test_empty_profile_is_default_off(self):
        result = run_profile({"NEXIUM_INTEL_INPUT_PROFILE": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("DIAGNOSTICS_PROFILE", result.stdout)

    def test_unknown_profile_is_blocked(self):
        result = run_profile({"NEXIUM_INTEL_INPUT_PROFILE": "production"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED: unsupported", result.stderr)

    def test_explicitly_disabled_predecessor_blocks_profile(self):
        result = run_profile({
            "NEXIUM_INTEL_INPUT_PROFILE": "controller-diagnostics-v1",
            "NEXIUM_EXPERIMENT_STAGE47_GUEST_RIGHT_Y": "0",
        })
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflicts with explicit NEXIUM_EXPERIMENT_STAGE47_GUEST_RIGHT_Y",
                      result.stderr)
        self.assertNotIn("PROFILE_V1_ENABLED", result.stdout)

    def test_invalid_flag_value_is_blocked(self):
        result = run_profile({
            "NEXIUM_INTEL_INPUT_PROFILE": "controller-diagnostics-v1",
            "NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD": "sometimes",
        })
        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED:", result.stderr)

    def test_explicit_enabled_flag_is_preserved(self):
        result = run_profile({
            "NEXIUM_INTEL_INPUT_PROFILE": "controller-diagnostics-v1",
            "NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD": "1",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        for key in REQUIRED:
            self.assertIn(f"{key}=1\n", result.stdout)

    def test_off_preserves_individually_disabled_flag(self):
        result = run_profile({
            "NEXIUM_INTEL_INPUT_PROFILE": "off",
            "NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD": "0",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD=0\n", result.stdout)
        self.assertIn("NEXIUM_EXPERIMENT_STAGE48_DUAL_STICK=unset\n", result.stdout)

    def test_profile_does_not_use_head_branch(self):
        content = PROFILE.read_text(encoding="utf-8")
        self.assertNotIn("github.head_ref", content)
        self.assertNotIn("GITHUB_HEAD_REF", content)

    def test_macos_build_sources_profile_before_checkout_and_patching(self):
        content = MACOS.read_text(encoding="utf-8")
        activation = 'source "$SELF/scripts/intel_controller_input_profile.sh"'
        self.assertEqual(content.count(activation), 1)
        self.assertLess(content.index(activation),
                        content.index('python3 "$SELF/scripts/apply_macos_bootstrap.py"'))
        self.assertLess(content.index(activation), content.index('git clone --recursive'))

    def test_both_shell_scripts_parse(self):
        for script in (PROFILE, MACOS):
            result = subprocess.run(["bash", "-n", str(script)],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
