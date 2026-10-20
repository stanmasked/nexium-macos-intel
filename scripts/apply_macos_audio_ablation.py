#!/usr/bin/env python3
"""Guarded, opt-in Intel macOS audio-startup ablation for GUI crash diagnosis.

This experiment does not fix eframe or promise GUI functionality. A
NEXIUM_MACOS_NO_AUDIO=1 runtime variable skips *both* host and UI audio
initializers in the pinned upstream only. Default startup is unchanged.
"""
from pathlib import Path
import argparse
import sys


def prepare(path: Path, old: str, new: str):
    source = path.read_text(encoding="utf-8")
    if new in source:
        return None
    if source.count(old) != 1:
        raise RuntimeError(f"expected exactly one pinned source anchor: {path}")
    return source.replace(old, new, 1)


def main(root: Path) -> None:
    main_path = root / "nexium-gui/src/main.rs"
    app_path = root / "nexium-gui/src/app.rs"
    main_old = '''    audio::init_host_audio(
        settings.audio_output_device.as_deref(),
        settings.audio_volume,
    );'''
    main_new = '''    // Research-only macOS A/B probe: does early host audio affect
    // eframe/winit event-loop reentrancy on hosted Intel runners?
    // Normal startup remains unchanged unless explicitly opted in.
    if cfg!(target_os = "macos")
        && std::env::var("NEXIUM_MACOS_NO_AUDIO").is_ok_and(|value| value == "1")
    {
        log::warn!("Mac GUI audio-ablation experiment enabled: host audio skipped");
    } else {
        audio::init_host_audio(
            settings.audio_output_device.as_deref(),
            settings.audio_volume,
        );
    }'''
    app_old = '''        crate::ui_audio::init(app_settings.audio_output_device.as_deref());'''
    app_new = '''        // Research-only macOS A/B probe. Do not initialize menu/UI audio
        // if host audio is intentionally disabled during headless CI.
        if !(cfg!(target_os = "macos")
            && std::env::var("NEXIUM_MACOS_NO_AUDIO").is_ok_and(|value| value == "1"))
        {
            crate::ui_audio::init(app_settings.audio_output_device.as_deref());
        }'''
    # Validate both anchors before making any writes.
    edits = [(main_path, prepare(main_path, main_old, main_new)),
             (app_path, prepare(app_path, app_old, app_new))]
    for path, updated in edits:
        if updated is not None:
            path.write_text(updated, encoding="utf-8")
            print(f"AUDIO_ABLATION_APPLIED: {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    try:
        main(args.source)
    except (OSError, RuntimeError) as exc:
        print(f"AUDIO_ABLATION_BLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
