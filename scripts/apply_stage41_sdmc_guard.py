#!/usr/bin/env python3
"""Stage41 experimental safe-by-default SD path guard for pinned NeXium.

Patches ONLY fs_host.rs in a separately checked-out upstream tree. Does not
activate unfinished FS/FSP IPC or grant access to real host user files.
This lexical/symlink check is not race-proof: never use a real user SD volume.
"""
from pathlib import Path
import argparse

MARKER = "// STAGE41_PRIVATE_SD_PATH_GUARD"
PREFIX = "pub fn translate_path(switch_path: &str) -> PathBuf {"
SUFFIX = "\n#[derive(Clone, Copy, Debug, PartialEq, Eq)]"
OLD_PATH_BODY = """pub fn translate_path(switch_path: &str) -> PathBuf {
    let cleaned = switch_path.trim_end_matches('\\0');
    let stripped = cleaned
        .strip_prefix("sdmc:/")
        .or_else(|| cleaned.strip_prefix("sdmc:"))
        .or_else(|| cleaned.strip_prefix("/"))
        .unwrap_or(cleaned);
    let stripped = stripped.trim_start_matches('/');
    sdmc_root().join(stripped.replace('\\\\', "/"))
}
"""


def patch_source(source: str, guard: str) -> str:
    """Fail closed when upstream format, anchors or callers drift."""
    if MARKER in source:
        if source.count(MARKER) != 1 or "stage41_guest_sd_path" not in source:
            raise ValueError("partially patched or malformed Stage41 source")
        return source
    if source.count(OLD_PATH_BODY) != 1:
        raise ValueError("pinned upstream path-translation anchor drifted")
    if source.count("pub fn sdmc_root() -> PathBuf {") != 1:
        raise ValueError("upstream sdmc root anchor drifted")
    source = source.replace(
        "pub fn sdmc_root() -> PathBuf {",
        MARKER + "\n" + guard.strip() + "\n\npub fn sdmc_root() -> PathBuf {",
        1,
    )
    replacement = """pub fn translate_path(switch_path: &str) -> Result<PathBuf, u32> {
    // Never silently expose the user's ordinary NeXium configuration root.
    // Test-only storage must explicitly opt in to an ABSOLUTE data directory.
    let data_root = std::env::var_os("NEXIUM_DATA_ROOT")
        .filter(|value| !value.is_empty()).ok_or(FS_ACCESS_DENIED)?;
    if !std::path::Path::new(&data_root).is_absolute() {
        return Err(FS_ACCESS_DENIED);
    }
    stage41_guest_sd_path(&sdmc_root(), switch_path).ok_or(FS_ACCESS_DENIED)
}
"""
    source = source.replace(OLD_PATH_BODY, replacement, 1)
    expected = {
        "let host = translate_path(switch_path);": 3,
        "std::fs::remove_file(translate_path(switch_path))": 1,
        "std::fs::create_dir_all(translate_path(switch_path))": 1,
    }
    for old, count in expected.items():
        if source.count(old) != count:
            raise ValueError(f"pinned upstream caller changed: {old!r}")
    # entry_type returns Option; other methods return Result.
    source = source.replace(
        "let host = translate_path(switch_path);",
        "let host = translate_path(switch_path).ok()?;", 1,
    )
    source = source.replace(
        "let host = translate_path(switch_path);",
        "let host = translate_path(switch_path)?;", 2,
    )
    source = source.replace(
        "std::fs::remove_file(translate_path(switch_path))",
        "std::fs::remove_file(translate_path(switch_path)?)", 1,
    )
    source = source.replace(
        "std::fs::create_dir_all(translate_path(switch_path))",
        "std::fs::create_dir_all(translate_path(switch_path)?)", 1,
    )
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream_root", type=Path)
    args = parser.parse_args()
    root = args.upstream_root.resolve(strict=True)
    target = root / "nexium-kernel/src/fs_host.rs"
    guard = (Path(__file__).resolve().parent.parent
             / "patches/stage41_sdmc_guard.rs").read_text(encoding="utf-8")
    current = target.read_text(encoding="utf-8")
    changed = patch_source(current, guard)
    if changed != current:
        target.write_text(changed, encoding="utf-8")
    print("STAGE41_PRIVATE_SD_PATH_GUARD_READY")


if __name__ == "__main__":
    main()
