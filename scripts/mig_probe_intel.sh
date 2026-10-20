#!/usr/bin/env bash
# Verify Apple's Mach Interface Generator on a native Intel macOS runner.
# Checks header/source generation only. Does not compile or run NeXium.
set -euo pipefail
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != x86_64 ]] ||
   [[ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" == 1 ]]; then
    echo "MIG_PROBE_BLOCKED: native Intel macOS required" >&2
    exit 2
fi
command -v xcrun >/dev/null || { echo "MIG_PROBE_BLOCKED: xcrun missing" >&2; exit 3; }
MIG="$(xcrun --find mig)"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
DEFS="$SDK/usr/include/mach/mach_exc.defs"
if [[ -z "$MIG" || ! -x "$MIG" || ! -f "$DEFS" ]]; then
    echo "MIG_PROBE_BLOCKED: missing mig or mach_exc.defs in selected SDK" >&2
    exit 4
fi
if [[ -n "${NEXIUM_MIG_WORKDIR:-}" ]]; then
    OUT="$NEXIUM_MIG_WORKDIR"
    mkdir -p "$OUT"
else
    OUT="$(mktemp -d "${TMPDIR:-/tmp}/nexium-mig-intel.XXXXXXXX")"
    trap 'rm -rf "$OUT"' EXIT
fi
echo "MIG executable: $MIG"
echo "macOS SDK: $SDK"
"$MIG" -arch x86_64 -isysroot "$SDK" \
    -user "$OUT/mach_exc_user.c" \
    -header "$OUT/mach_exc_user.h" \
    -server "$OUT/mach_exc_server.c" \
    -sheader "$OUT/mach_exc_server.h" \
    "$DEFS"
for file in mach_exc_server.c mach_exc_server.h; do
    [[ -s "$OUT/$file" ]] || {
        echo "MIG_PROBE_BLOCKED: $file missing/empty after generation" >&2
        exit 5
    }
done
echo "MIG_INTEL_GENERATION_OK: both generated server files are nonempty"
echo "This alone does NOT prove that Dynarmic compiles or that NeXium boots."
