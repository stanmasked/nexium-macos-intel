//! Native Intel Stage47: SDL3 0.20.0 safe Rust virtual gamepad semantics.
//!
//! Not the whole NeXium InputBackend or InputSnapshot. Same exact crate,
//! feature flags and macOS x86_64 target as the original application.
//! No physical devices or private user events are read or published.
use sdl3::gamepad::{Axis, Button};
use sdl3::joystick::{JoystickType, VirtualJoystickDescription};

fn mark(s: &str) {
    // Only constant literals supplied by this source may reach stdout.
    println!("STAGE47_{s}");
}

fn tested(mode: &str) -> bool {
    mark("PROCESS_ENTERED");
    sdl3::hint::set("SDL_JOYSTICK_THREAD", "1");
    sdl3::hint::set("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
    mark("BEFORE_SDL_INIT");
    let Ok(sdl) = sdl3::init() else {
        mark("SDL_INIT_FAILED");
        return false;
    };
    let Ok(joy) = sdl.joystick() else {
        mark("JOYSTICK_SUBSYSTEM_FAILED");
        return false;
    };
    let Ok(gps) = sdl.gamepad() else {
        mark("GAMEPAD_SUBSYSTEM_FAILED");
        return false;
    };
    mark("SUBSYSTEMS_READY");

    let desc = VirtualJoystickDescription::new()
        .name("Stage47 Synthetic Rust SDL3 Controller")
        .joystick_type(JoystickType::Gamepad)
        .with_button(Button::South)
        .with_axis(Axis::LeftX);
    mark("BEFORE_ATTACH");
    let Ok(connection) = joy.attach_virtual_joystick(desc) else {
        mark("ATTACH_FAILED");
        return false;
    };
    let Ok(virtual_joystick) = joy.open(connection.id()) else {
        mark("OPEN_JOYSTICK_FAILED");
        return false;
    };
    let Ok(pad) = gps.open(connection.id()) else {
        mark("OPEN_GAMEPAD_FAILED");
        return false;
    };
    mark("VIRTUAL_GAMEPAD_OPENED");

    let mut events = if mode == "event-pump" {
        match sdl.event_pump() {
            Ok(p) => Some(p),
            Err(_) => {
                mark("EVENT_PUMP_FAILED");
                return false;
            }
        }
    } else {
        None
    };
    // Same original InputBackend::poll update ordering.
    let mut refresh = || {
        if let Some(ref mut pump) = events {
            pump.pump_events();
        }
        gps.update();
    };
    refresh();
    if virtual_joystick
        .set_virtual_button(Button::South as u32, true)
        .is_err()
        || virtual_joystick
            .set_virtual_axis(Axis::LeftX as u32, 16000)
            .is_err()
    {
        mark("INJECTION_FAILED");
        return false;
    }
    refresh();
    let raw = pad.axis(Axis::LeftX);
    let scaled_stick = ((raw as f32 / 32768.0) * 30000.0) as i32;
    if !pad.connected()
        || !pad.button(Button::South)
        || raw <= 10000
        || scaled_stick <= 10000
    {
        mark("READBACK_FAILED");
        return false;
    }
    mark("BUTTON_AND_AXIS_OK");
    if virtual_joystick
        .set_virtual_button(Button::South as u32, false)
        .is_err()
        || virtual_joystick
            .set_virtual_axis(Axis::LeftX as u32, 0)
            .is_err()
    {
        mark("RELEASE_FAILED");
        return false;
    }
    refresh();
    if !pad.connected()
        || pad.button(Button::South)
        || pad.axis(Axis::LeftX).abs() > 500
    {
        mark("RELEASE_READBACK_FAILED");
        return false;
    }
    mark("RELEASE_AND_NEUTRAL_OK");
    drop(refresh);
    drop(pad);
    drop(virtual_joystick);
    drop(connection);
    mark("DEVICE_CLEANED");
    mark("CONTRACT_PASSED");
    true
}

fn main() {
    let mode = std::env::args().nth(1).unwrap_or_default();
    if mode != "direct-update" && mode != "event-pump" {
        std::process::exit(64);
    }
    if !tested(&mode) {
        std::process::exit(3);
    }
}
