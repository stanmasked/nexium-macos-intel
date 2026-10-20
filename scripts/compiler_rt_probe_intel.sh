#!/usr/bin/env bash
# Locate and verify the Xcode compiler-rt archive for native Intel macOS.
# Rust's final link may omit Apple's compiler-rt availability helper used by
# SDL3 Objective-C objects: ___isPlatformVersionAtLeast.
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "x86_64" ]] ||
   [[ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" == "1" ]]; then
    echo "CLANG_RT_BLOCKED: native Intel macOS required" >&2
    exit 2
fi
for tool in xcrun rustc; do
    command -v "$tool" >/dev/null || { echo "CLANG_RT_BLOCKED: missing $tool" >&2; exit 3; }
done
resource="$(xcrun clang -print-resource-dir)"
archive="$resource/lib/darwin/libclang_rt.osx.a"
if [[ ! -s "$archive" ]]; then
    echo "CLANG_RT_BLOCKED: Xcode compiler runtime archive missing: $archive" >&2
    exit 4
fi
if ! xcrun nm -arch x86_64 "$archive" 2>/dev/null | grep -F '___isPlatformVersionAtLeast' >/dev/null; then
    echo "CLANG_RT_BLOCKED: ___isPlatformVersionAtLeast is not exported by $archive" >&2
    exit 5
fi
if [[ "${1:-}" == "--path" ]]; then
    printf '%s\n' "$archive"
    exit 0
fi
if [[ $# -gt 0 && "$1" != "--probe" ]]; then
    echo "usage: $0 [--path|--probe]" >&2
    exit 2
fi
echo "CLANG_RT_SYMBOL_FOUND: $archive"
work="$(mktemp -d "${TMPDIR:-/tmp}/nexium-compiler-rt-intel.XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
cat > "$work/symbol.rs" <<'RUST'
unsafe extern "C" {
    #[link_name = "__isPlatformVersionAtLeast"]
    fn platform_version_at_least(platform: u32, major: u32, minor: u32, patch: u32) -> i32;
}
fn main() {
    // Force a real reference to the external availability helper. Never run
    // this executable: this probe proves linkage, not helper ABI semantics.
    let func = platform_version_at_least as *const ();
    std::hint::black_box(func);
}
RUST
rustc --edition 2021 --target x86_64-apple-darwin \
    -C "link-arg=$archive" "$work/symbol.rs" -o "$work/symbol"
test -s "$work/symbol"
archs="$(xcrun lipo -archs "$work/symbol")"
if [[ "$archs" != "x86_64" ]]; then
    echo "CLANG_RT_BLOCKED: unexpected probe architecture $archs" >&2
    exit 6
fi
echo "CLANG_RT_LINK_OK: compiled x86_64 Rust executable using Xcode compiler-rt"
echo "No NeXium executable or NRO was exercised."
