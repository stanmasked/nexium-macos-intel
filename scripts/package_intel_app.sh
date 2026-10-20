#!/usr/bin/env bash
# Preserve macOS .app executable bits across GitHub Actions artifact downloads.
set -euo pipefail
if [[ $# -ne 2 ]]; then
    echo "usage: $0 /absolute/path/NeXium.app /absolute/path/LICENSE.txt" >&2
    exit 2
fi
APP="$1"
LICENSE="$2"
if [[ ! -d "$APP/Contents/MacOS" || ! -x "$APP/Contents/MacOS/nexium" ]]; then
    echo "PACKAGE_BLOCKED: missing executable in $APP" >&2
    exit 3
fi
if [[ ! -s "$APP/Contents/Info.plist" || ! -s "$LICENSE" ]]; then
    echo "PACKAGE_BLOCKED: missing bundle metadata or upstream license" >&2
    exit 4
fi
DIST="$(cd "$(dirname "$APP")" && pwd)"
BUNDLE="$(basename "$APP")"
LICENSE_NAME="$(basename "$LICENSE")"
if [[ "$(cd "$(dirname "$LICENSE")" && pwd)" != "$DIST" ]]; then
    echo "PACKAGE_BLOCKED: license must be in distribution directory" >&2
    exit 5
fi
OUT="$DIST/${BUNDLE%.app}.tar.gz"
if [[ -e "$OUT" ]]; then
    echo "PACKAGE_BLOCKED: archive already exists: $OUT" >&2
    exit 6
fi
(cd "$DIST" && tar -czf "$OUT" "$BUNDLE" "$LICENSE_NAME")
tar -tzf "$OUT" | grep -F "$BUNDLE/Contents/MacOS/nexium" >/dev/null
shasum -a 256 "$OUT" > "$OUT.sha256"
echo "INTEL_APP_ARCHIVE_OK: $OUT"
echo "The archive preserves executable permissions; unsigned apps may still need local approval."
