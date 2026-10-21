#!/usr/bin/env bash
# Reproducible EXPERIMENTAL NeXium build attempt for native Intel Mac only.
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "x86_64" ]] ||
   [[ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" == "1" ]]; then
    echo "BLOCKED: a physical Intel Mac running macOS is required (not Rosetta)." >&2
    exit 2
fi

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVISION="089562567a0a8760dfdd8420e1f57c35159a9219"
BACKEND="${NEXIUM_CPU_BACKEND:-dynarmic}"
case "$BACKEND" in
    dynarmic|rustarmic) ;;
    *) echo "BLOCKED: NEXIUM_CPU_BACKEND must be dynarmic or rustarmic" >&2; exit 2 ;;
esac
WORK="${NEXIUM_MAC_WORKDIR:-$PWD/nexium-macos-intel-work}"
SRC="$WORK/nexium"
mkdir -p "$WORK"
LOG="$WORK/build.log"
exec > >(tee -a "$LOG") 2>&1

echo "NeXium Intel/macOS experimental probe at $(date -u +%FT%TZ)"
echo "Host: $(sw_vers -productVersion) / $(uname -m)"
for tool in git python3 clang cmake ninja rustc cargo rustup xcrun; do
    command -v "$tool" >/dev/null || { echo "BLOCKED: missing $tool"; exit 3; }
done
xcrun --show-sdk-version
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
# Keep Rust, SDL3/Clang and CMake on one minimum macOS deployment target.
# Rust's default may be 10.12 while SDL3's C objects were built for 15.5,
# causing undefined ___isPlatformVersionAtLeast at the final linker step.
export MACOSX_DEPLOYMENT_TARGET="${NEXIUM_MIN_MACOS:-10.15}"
if [[ ! "$MACOSX_DEPLOYMENT_TARGET" =~ ^(10\.(1[5-9]|[2-9][0-9])|1[1-9](\.[0-9]+)?)$ ]]; then
    echo "BLOCKED: invalid/unsupported minimum macOS: $MACOSX_DEPLOYMENT_TARGET"
    exit 3
fi
export CMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET"
if [[ ! -f "$SDKROOT/usr/include/mach/mach_exc.defs" ]]; then
    echo "BLOCKED: macOS SDK missing Mach exception interface definitions"
    exit 3
fi
echo "macOS SDK: $SDKROOT"
echo "macOS deployment target: $MACOSX_DEPLOYMENT_TARGET"
echo "SDK Clang: $(xcrun clang --version | head -n 1)"
echo "CPU backend: $BACKEND"
rustc --version
if command -v vulkaninfo >/dev/null; then
    vulkaninfo --summary || echo "WARN: Vulkan or MoltenVK capabilities unavailable"
else
    echo "WARN: vulkaninfo missing"
fi

if [[ -e "$SRC" && ! -d "$SRC/.git" ]]; then
    echo "BLOCKED: checkout path already exists but is not a Git repository"
    exit 4
fi
if [[ ! -d "$SRC/.git" ]]; then
    git clone --recursive https://github.com/nexium-emu/nexium.git "$SRC"
fi
cd "$SRC"
if [[ -n "$(git status --porcelain)" ]]; then
    echo "BLOCKED: source checkout has changes. Use a clean NEXIUM_MAC_WORKDIR."
    exit 5
fi
git fetch origin "$REVISION"
git checkout --detach "$REVISION"
git submodule update --init --recursive
python3 "$SELF/scripts/apply_macos_bootstrap.py" "$SRC"
if [[ "${NEXIUM_EXPERIMENT_AUDIO_ABLATION:-0}" == "1" ]]; then
    echo "AUDIO_ABLATION_EXPERIMENT: patching locally checked-out host and UI audio initialization"
    python3 "$SELF/scripts/apply_macos_audio_ablation.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_MINIMAL_EFRAME:-0}" == "1" ]]; then
    echo "STAGE22_MINIMAL_EFRAME: opt-in minimal macOS eframe/Wgpu startup experiment"
    python3 "$SELF/scripts/apply_macos_minimal_eframe.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_FULL_INIT_MINIMAL_APP:-0}" == "1" ]]; then
    echo "STAGE25_FULL_INIT: isolate HorizonApp constructor after normal host startup"
    python3 "$SELF/scripts/apply_macos_full_init_minimal_app.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_HORIZON_CTOR_ONLY:-0}" == "1" ]]; then
    echo "STAGE26_CONSTRUCTOR_ONLY: retain HorizonApp but suppress its eframe UI"
    python3 "$SELF/scripts/apply_macos_horizonapp_ctor_only.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_HORIZON_CTOR_PHASE_TRACE:-0}" == "1" ]]; then
    echo "STAGE28_CONSTRUCTOR_PHASES: guarded HorizonApp::new phase markers"
    python3 "$SELF/scripts/apply_macos_horizon_ctor_phase_trace.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_SDL3_INPUT_ABLATION:-0}" == "1" ]]; then
    echo "STAGE29_SDL3_INPUT: isolate only native controller initialization"
    python3 "$SELF/scripts/apply_macos_sdl3_input_ablation.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_SDL3_PREWINIT:-0}" == "1" ]]; then
    echo "STAGE32_PREWINIT: construct and retain real SDL3 input before winit"
    python3 "$SELF/scripts/apply_macos_sdl3_pre_winit.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_INPUT_POLL_MARKERS:-0}" == "1" ]]; then
    echo "STAGE34_INPUT_POLL: one-time real SDL3 event-loop markers"
    python3 "$SELF/scripts/apply_macos_input_poll_trace.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_VIRTUAL_INPUT_SNAPSHOT:-0}" == "1" ]]; then
    echo "STAGE36: opt-in synthetic SDL3 virtual gamepad; original InputSnapshot readback"
    python3 "$SELF/scripts/apply_macos_virtual_input_snapshot.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_STAGE37_HID_BRIDGE:-0}" == "1" ]]; then
    echo "STAGE37: genuine original mapped virtual Switch B -> host HidState after update_input"
    python3 "$SELF/scripts/apply_macos_hid_host_bridge_trace.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_STAGE40_GUEST_HID:-0}" == "1" ]]; then
    echo "STAGE40: extend only the synthetic B hold for guest libnx HID readback"
    python3 "$SELF/scripts/apply_macos_guest_hid_probe.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_STAGE42_GUEST_AB:-0}" == "1" ]]; then
    echo "STAGE42: enable opt-in EAST/A pulse nested inside SOUTH/B"
    python3 "$SELF/scripts/apply_macos_guest_ab_probe.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_STAGE43_GUEST_DPAD:-0}" == "1" ]]; then
    echo "STAGE43: add DPad Up and Right source-authentic guest readback pulses"
    python3 "$SELF/scripts/apply_macos_guest_dpad_probe.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_STAGE44_GUEST_STICK_X:-0}" == "1" ]]; then
    echo "STAGE44: opt-in left X axis and authentic original InputSnapshot observation"
    python3 "$SELF/scripts/apply_macos_guest_left_stick_x.py" "$SRC"
fi
if [[ "${NEXIUM_EXPERIMENT_STAGE45_GUEST_STICK_Y:-0}" == "1" ]]; then
    echo "STAGE45: exercise LeftY inversion through original SDL3 and guest libnx"
    python3 "$SELF/scripts/apply_macos_guest_left_stick_y.py" "$SRC"
fi

rustup target add x86_64-apple-darwin
if [[ "$BACKEND" == "dynarmic" ]]; then
    # Pin the published crate, then patch a LOCAL copy rather than editing
    # the shared Cargo registry. Its vendor CMake omits Mach MIG generation.
    # Upstream intentionally has no tracked Cargo.lock at this pin.
    # Generate a local resolution before modifying Cargo.toml.
    cargo fetch --target x86_64-apple-darwin
    python3 "$SELF/scripts/prepare_dynarmic_macos.py" "$SRC" \
        --cargo-home "${CARGO_HOME:-$HOME/.cargo}" --work "$WORK"
fi
# Apple Clang normally provides this compiler-rt archive during its own
# final link, but rustc's macOS link command can omit it. SDL3 references
# ___isPlatformVersionAtLeast from its Objective-C translation units.
# Link ONLY the final binary with the native Xcode archive, not each crate.
CLANG_RT_OSX="$(bash "$SELF/scripts/compiler_rt_probe_intel.sh" --path)"
echo "Explicit Intel compiler-rt for SDL3 linkage: $CLANG_RT_OSX"
set +e
cargo rustc --release --target x86_64-apple-darwin \
    -p nexium-gui --bin nexium \
    --no-default-features --features "backend-$BACKEND" -- \
    -C "link-arg=$CLANG_RT_OSX"
status=$?
set -e
if [[ $status -ne 0 ]]; then
    echo "BUILD_BLOCKED: cargo exit=$status; review $LOG"
    exit "$status"
fi

BIN="$SRC/target/x86_64-apple-darwin/release/nexium"
if [[ ! -f "$BIN" ]]; then
    echo "BUILD_BLOCKED: no native Intel Mach-O binary was emitted" >&2
    exit 6
fi
ARCHES="$(xcrun lipo -archs "$BIN")"
if [[ "$ARCHES" != "x86_64" ]]; then
    echo "BUILD_BLOCKED: expected native x86_64-only binary; got: $ARCHES" >&2
    exit 7
fi
echo "INTEL_MACHO_VERIFIED: $ARCHES"
APP="$WORK/dist/NeXium-Intel-$BACKEND-Experimental.app"
mkdir -p "$APP/Contents/MacOS"
cp "$SRC/target/x86_64-apple-darwin/release/nexium" "$APP/Contents/MacOS/nexium"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>nexium</string>
<key>CFBundleIdentifier</key><string>org.nexium-emu.macos.intel.experimental</string>
<key>CFBundleName</key><string>NeXium Intel Experimental</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2.0</string>
<key>CFBundleVersion</key><string>2</string>
<key>NSHighResolutionCapable</key><true/>
<key>LSMinimumSystemVersion</key><string>${MACOSX_DEPLOYMENT_TARGET}</string>
</dict></plist>
PLIST
cp "$SRC/LICENSE" "$WORK/dist/NeXium-LICENSE.txt"
bash "$SELF/scripts/package_intel_app.sh" "$APP" "$WORK/dist/NeXium-LICENSE.txt"
echo "EXPERIMENTAL_BUILD_OK: $APP"
xcrun otool -l "$APP/Contents/MacOS/nexium" | grep -A 5 -E "LC_BUILD_VERSION|LC_VERSION_MIN_MACOSX" || true
echo "No NRO, audio, graphics or gameplay success has been asserted."
