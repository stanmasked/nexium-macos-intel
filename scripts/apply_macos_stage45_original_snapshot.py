#!/usr/bin/env python3
"""Stage45: opt-in genuine NeXium InputBackend synthetic controller snapshot.

On Intel macOS only, exercise sdl3 0.20's safe Rust virtual joystick API
inside the ORIGINAL InputBackend. Prewarm still occurs before eframe/winit,
never during HorizonApp constructor. Inject press/axis/release and read back
through ORIGINAL InputBackend::poll + ControllerConfig -> InputSnapshot.
No sys:: pointer manipulation, production defaults change, game, NRO or raw
controller values are emitted. No keyboard, physical controller or player ID
is logged. A failure emits a bounded constant marker (not a fabricated pass).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

INPUT_ANCHOR = "impl InputBackend {\n    pub fn new(motion_enabled: bool, preferred: Option<String>) -> Option<Self> {"
MAIN_ANCHOR = '''        let candidate = input::InputBackend::new(
            settings.motion_enabled, settings.gamepad.clone()
        );
'''
INPUT_MARK = "STAGE45_VIRTUAL_SNAPSHOT_BEGIN"
MAIN_MARK = "STAGE45_ORIGINAL_SNAPSHOT_REQUESTED"

INPUT_METHOD = '''impl InputBackend {
    // Stage45 diagnostic only: exercise the original SDL3 input processing
    // using a process-local virtual controller. Never reads real key data.
    #[cfg(target_os = "macos")]
    pub(crate) fn stage45_virtual_snapshot_contract(&mut self) -> bool {
        use sdl3::joystick::{JoystickType, VirtualJoystickDescription};
        eprintln!("STAGE45_VIRTUAL_SNAPSHOT_BEGIN");

        let Ok(subsystem) = self.sdl.joystick() else {
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_SUBSYSTEM_UNAVAILABLE");
            return false;
        };
        let desc = VirtualJoystickDescription::new()
            .name("NeXium Stage45 Private Synthetic Device")
            .joystick_type(JoystickType::Gamepad)
            .with_button(Button::South)
            .with_axis(Axis::LeftX);
        let Ok(connection) = subsystem.attach_virtual_joystick(desc) else {
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_ATTACH_FAILED");
            return false;
        };
        let Ok(virtual_pad) = subsystem.open(connection.id()) else {
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_OPEN_FAILED");
            return false;
        };
        eprintln!("STAGE45_VIRTUAL_SNAPSHOT_ATTACHED");

        // Restrict pad selection to the controlled synthetic device. Restore
        // settings after testing so the later GUI behaves normally.
        let saved_selected = self.selected_id;
        let saved_preferred = self.preferred.take();
        self.pad = None;
        self.selected_id = Some(connection.id());
        self.open_failure = None;
        let cfg = ControllerConfig::default();

        let passed = (|| -> bool {
            let baseline = self.poll(&cfg, 0.12, 0.12);
            if !baseline.connected {
                eprintln!("STAGE45_VIRTUAL_SNAPSHOT_NOT_CONNECTED");
                return false;
            }
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_CONNECTED");

            if virtual_pad.set_virtual_button(Button::South as u32, true).is_err()
                || virtual_pad.set_virtual_axis(Axis::LeftX as u32, 16000).is_err()
            {
                eprintln!("STAGE45_VIRTUAL_SNAPSHOT_INJECT_FAILED");
                return false;
            }
            let pressed = self.poll(&cfg, 0.12, 0.12);
            if !(pressed.connected
                && pressed.is(SwitchButton::B)
                && pressed.sticks[0] > 10000
                && pressed.raw_sticks[0] > 0.35)
            {
                eprintln!("STAGE45_VIRTUAL_SNAPSHOT_READBACK_FAILED");
                return false;
            }
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_PRESS_AXIS_OK");

            if virtual_pad.set_virtual_button(Button::South as u32, false).is_err()
                || virtual_pad.set_virtual_axis(Axis::LeftX as u32, 0).is_err()
            {
                eprintln!("STAGE45_VIRTUAL_SNAPSHOT_RELEASE_INJECT_FAILED");
                return false;
            }
            let released = self.poll(&cfg, 0.12, 0.12);
            if !(released.connected
                && !released.is(SwitchButton::B)
                && released.sticks[0].abs() < 500
                && released.raw_sticks[0].abs() < 0.02)
            {
                eprintln!("STAGE45_VIRTUAL_SNAPSHOT_RELEASE_READBACK_FAILED");
                return false;
            }
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_RELEASE_OK");
            true
        })();

        // Drop the controlled device before handing this InputBackend to
        // the original GUI; do not leave test-only selection in user settings.
        self.pad = None;
        self.selected_id = saved_selected;
        self.preferred = saved_preferred;
        self.open_failure = None;
        drop(virtual_pad);
        drop(connection);
        eprintln!("STAGE45_VIRTUAL_SNAPSHOT_DEVICE_CLEANED");
        if passed {
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_PASSED");
        } else {
            eprintln!("STAGE45_VIRTUAL_SNAPSHOT_CONTRACT_FAILED");
        }
        passed
    }
}

'''

MAIN_PATCH = '''        let mut candidate = input::InputBackend::new(
            settings.motion_enabled, settings.gamepad.clone()
        );
        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_VIRTUAL_SNAPSHOT_TEST").ok().as_deref() == Some("1") {
            eprintln!("STAGE45_ORIGINAL_SNAPSHOT_REQUESTED");
            if let Some(ref mut backend) = candidate {
                let _ = backend.stage45_virtual_snapshot_contract();
            } else {
                eprintln!("STAGE45_ORIGINAL_SNAPSHOT_BACKEND_MISSING");
            }
        }
'''


def patch_input(source: str) -> str:
    if INPUT_MARK in source:
        if source.count(INPUT_METHOD) == 1:
            return source
        raise ValueError("partial Stage45 original input edit")
    if source.count(INPUT_ANCHOR) != 1:
        raise ValueError("pinned original InputBackend constructor missing")
    if source.count("pub fn poll(&mut self, cfg: &ControllerConfig") != 1:
        raise ValueError("original InputBackend::poll missing")
    if "STAGE38_SDL3_INPUT_02_BEFORE_GAMEPAD_SUBSYSTEM" not in source:
        raise ValueError("Stage38 SDL3 source instrumentation missing")
    return source.replace(INPUT_ANCHOR, INPUT_METHOD + INPUT_ANCHOR, 1)


def patch_main(source: str) -> str:
    if MAIN_MARK in source:
        if source.count(MAIN_PATCH) == 1:
            return source
        raise ValueError("partial Stage45 main edit")
    if "STAGE40_PREWARM_MAIN_BEFORE_EFRAME" not in source:
        raise ValueError("Stage40 must be installed before Stage45")
    if source.count(MAIN_ANCHOR) != 1:
        raise ValueError("pinned Stage40 original constructor anchor missing")
    return source.replace(MAIN_ANCHOR, MAIN_PATCH, 1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkout", type=Path)
    args = p.parse_args(argv)
    base = args.checkout / "nexium-gui/src"
    i_file, m_file = base / "input.rs", base / "main.rs"
    try:
        old_i, old_m = i_file.read_text("utf-8"), m_file.read_text("utf-8")
        new_i, new_m = patch_input(old_i), patch_main(old_m)
        # Fail closed: validate both original sources before any write.
        if old_i != new_i:
            i_file.write_text(new_i, "utf-8")
        if old_m != new_m:
            m_file.write_text(new_m, "utf-8")
        print("STAGE45_ORIGINAL_SNAPSHOT_PATCH_APPLIED" if
              (new_i != old_i or new_m != old_m)
              else "STAGE45_ORIGINAL_SNAPSHOT_PATCH_IDEMPOTENT")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print("STAGE45_ORIGINAL_SNAPSHOT_PATCH_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
