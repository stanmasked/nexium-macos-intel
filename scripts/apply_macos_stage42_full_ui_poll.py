#!/usr/bin/env python3
"""Stage42 source-guarded full original HorizonApp::ui and SDL3 poll probe.

Opt-in, macOS-only. Preserves the original update/poll behavior and never logs
input values, key codes, controller identities, paths or private game content.
A poll checkpoint is stronger than constructor-only survival, but NOT proof of
a physical controller input or correct button/axis mapping.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

START = "impl eframe::App for HorizonApp {"
UI = "    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {"
POLL = """            self.last_input = ib.poll(
                &self.controller_config,
                self.app_settings.left_deadzone,
                self.app_settings.right_deadzone,
            );"""
MARK_UI = "STAGE42_FULL_UI_ENTERED"
MARK_POLL = "STAGE42_INPUT_POLL_FIRST"
MARK_CONNECTED = "STAGE42_CONTROLLER_CONNECTED"

UI_GUARD = '''        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_SDL3_POLL_TRACE")
            .ok().as_deref() == Some("1")
        {
            static UI_SEEN: std::sync::atomic::AtomicBool =
                std::sync::atomic::AtomicBool::new(false);
            if !UI_SEEN.swap(true, std::sync::atomic::Ordering::Relaxed) {
                eprintln!("STAGE42_FULL_UI_ENTERED");
            }
        }
'''

POLL_GUARD = '''            #[cfg(target_os = "macos")]
            if std::env::var("NEXIUM_MACOS_SDL3_POLL_TRACE")
                .ok().as_deref() == Some("1")
            {
                static POLL_SEEN: std::sync::atomic::AtomicBool =
                    std::sync::atomic::AtomicBool::new(false);
                if !POLL_SEEN.swap(true, std::sync::atomic::Ordering::Relaxed) {
                    eprintln!("STAGE42_INPUT_POLL_FIRST");
                }
                static CONNECTED_SEEN: std::sync::atomic::AtomicBool =
                    std::sync::atomic::AtomicBool::new(false);
                if self.last_input.connected
                    && !CONNECTED_SEEN.swap(true, std::sync::atomic::Ordering::Relaxed)
                {
                    eprintln!("STAGE42_CONTROLLER_CONNECTED");
                }
            }
'''


def patch_source(source: str) -> str:
    if MARK_UI in source or MARK_POLL in source or MARK_CONNECTED in source:
        if source.count(UI_GUARD) == 1 and source.count(POLL_GUARD) == 1:
            return source
        raise ValueError("partial Stage42 full UI or SDL3 polling instrumentation")
    if source.count(START) != 1:
        raise ValueError("pinned HorizonApp eframe implementation missing")
    before, app = source.split(START, 1)
    if app.count(UI) != 1 or app.count(POLL) != 1:
        raise ValueError("pinned original full UI and input poll anchors missing or duplicated")
    if "STAGE40_PREWARM_CONSTRUCTOR_CONSUMED" not in source:
        raise ValueError("Stage40 same-thread prewarm must already be installed")
    # Replace only within HorizonApp's original implementation.
    app = app.replace(UI, UI + "\n" + UI_GUARD, 1)
    app = app.replace(POLL, POLL + "\n" + POLL_GUARD, 1)
    return before + START + app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args(argv)
    target = args.checkout / "nexium-gui/src/app.rs"
    try:
        original = target.read_text(encoding="utf-8")
        result = patch_source(original)
        if result != original:
            target.write_text(result, encoding="utf-8")
        print("STAGE42_FULL_UI_POLL_PATCH_APPLIED" if result != original
              else "STAGE42_FULL_UI_POLL_PATCH_IDEMPOTENT")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print("STAGE42_FULL_UI_POLL_PATCH_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
