# Intel controller diagnostics profile (Stage51)

This is an **experimental, opt-in controller diagnostic build** for the
pinned NeXium Intel source, not a production release or real-gamepad test.

## Explicit selection

The `macos_probe.sh` build now sources
`scripts/intel_controller_input_profile.sh` **before the pinned NeXium
source checkout and source transformations**.

- `NEXIUM_INTEL_INPUT_PROFILE=off` (or unset) leaves all existing feature
  selectors untouched.
- `NEXIUM_INTEL_INPUT_PROFILE=controller-diagnostics-v1` enables the complete
  SDL3 input event/preinit/snapshot/HID-bridge and Stage40–48 source
  instrumentation sequence. Selection depends on an explicit environment
  value, **not** `GITHUB_HEAD_REF` or an experimental branch name.
- Any unknown profile name or contradictory explicit per-stage selector
  (e.g. `NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD=0`) fails before applying any
  profile changes. Every source patch still validates the pinned Rust source
  anchors independently, failing closed on drift.

Example of the opt-in component of the existing experimental Intel build:

```bash
NEXIUM_CPU_BACKEND=rustarmic \
NEXIUM_INTEL_INPUT_PROFILE=controller-diagnostics-v1 \
bash ./macos_probe.sh
```

The existing experimental UI/audio/Mach prerequisites still apply. For
reproducible validation, use the `macos-15-intel` CI workflow (Stage51),
which supplies the previously tested startup settings.

## Proof requirements

The Stage51 CI test clears the **legacy branch-name-derived Stage40–48
variables** before building the Intel host binary. The profile must
explicitly enable the same authenticated patch chain. The job then builds a
public libnx Stage50 diagnostic NRO and runs the **same-process mixed DPad +
both analog sticks** guest readback, requiring original SDL3, actual
`InputSnapshot`, NPad and real libnx SVC evidence. Only a sanitized JSON
receipt is uploaded.

`tests/test_stage51_controller_input_profile.py` checks defaults, all
13 required flags, branch neutrality, contradictory values, idempotent
pre-enabled selectors, build order and bash syntax on Linux. This test alone
does **not** prove that the native Intel guest run passed.

## Scope

This profile enables *synthetic SDL3 diagnostics* rather than a production
input feature. It does **not** attest to physical controllers, real Switch
hardware, playable commercial games, audio/graphics correctness or ROM
compatibility. Raw emulator logs, guest memory, firmware, ROMs and frame
screenshots must not be uploaded.
