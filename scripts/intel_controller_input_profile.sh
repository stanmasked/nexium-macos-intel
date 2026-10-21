#!/usr/bin/env bash
# Reproducible source-authentic controller diagnostics selection for Intel.
# Source this from macos_probe.sh after SELF is established.
# This is NOT a production controller mode or a physical gamepad test.
#
# Default: no additional controller instrumentation. Named opt-in:
#   NEXIUM_INTEL_INPUT_PROFILE=controller-diagnostics-v1
# Enables all pinned source patches on any branch, not just known PR names.
# Never injects guest memory or bypasses the individual source-anchor checks.

nexium_select_intel_input_profile() {
    local profile="${NEXIUM_INTEL_INPUT_PROFILE:-off}"
    case "$profile" in
        off) return 0 ;;
        controller-diagnostics-v1) ;;
        *)
            echo "BLOCKED: unsupported NEXIUM_INTEL_INPUT_PROFILE" >&2
            return 2
            ;;
    esac

    # The order matches patch calls in macos_probe.sh.
    local required=(
        NEXIUM_EXPERIMENT_SDL3_INPUT_ABLATION
        NEXIUM_EXPERIMENT_SDL3_PREWINIT
        NEXIUM_EXPERIMENT_INPUT_POLL_MARKERS
        NEXIUM_EXPERIMENT_VIRTUAL_INPUT_SNAPSHOT
        NEXIUM_EXPERIMENT_STAGE37_HID_BRIDGE
        NEXIUM_EXPERIMENT_STAGE40_GUEST_HID
        NEXIUM_EXPERIMENT_STAGE42_GUEST_AB
        NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD
        NEXIUM_EXPERIMENT_STAGE44_GUEST_STICK_X
        NEXIUM_EXPERIMENT_STAGE45_GUEST_STICK_Y
        NEXIUM_EXPERIMENT_STAGE46_GUEST_RIGHT_X
        NEXIUM_EXPERIMENT_STAGE47_GUEST_RIGHT_Y
        NEXIUM_EXPERIMENT_STAGE48_DUAL_STICK
    )
    local key current

    # Reject contradictory explicit settings BEFORE altering the environment.
    for key in "${required[@]}"; do
        current="${!key:-}"
        if [[ -n "$current" && "$current" != "1" ]]; then
            echo "BLOCKED: controller profile conflicts with explicit $key" >&2
            return 2
        fi
    done

    for key in "${required[@]}"; do
        export "$key=1"
    done
    echo "NEXIUM_INTEL_CONTROLLER_DIAGNOSTICS_PROFILE_V1_ENABLED"
}

nexium_select_intel_input_profile
