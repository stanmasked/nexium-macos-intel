#!/usr/bin/env python3
"""Stage36 opt-in macOS SDL3 *synthetic* virtual-button integration test.

A genuine SDL3 virtual joystick is attached ONLY before winit in the Stage32
pre-initialized InputBackend. A source-authentic original InputBackend::poll
sees synthetic press/release. No real gamepad, game/NRO, personal button data
or performance guarantee is claimed. Fail closed on pinned-source drift.
"""
from pathlib import Path
import argparse
import sys

CTOR = "        let gamepad = sdl.gamepad().ok()?;"
IMPL = "impl InputBackend {\n"
POLL = "    pub fn poll(&mut self, cfg: &ControllerConfig, left_dz: f32, right_dz: f32) -> InputSnapshot {\n"
POLL_EVENT = "        if let Ok(mut ep) = self.sdl.event_pump() {"
END = "        snap\n    }\n\n    pub fn first_pressed"
VIRTUAL = "STAGE36_VIRTUAL_"

SUPPORT = r'''// Stage36: synthetic SDL3 gamepad is NEVER enabled in a production startup.
// SDL's virtual device exists only in the same process (not a physical pad).
#[cfg(target_os = "macos")]
thread_local! {
    static STAGE36_VIRTUAL_PAD: std::cell::Cell<*mut sdl3::sys::joystick::SDL_Joystick> =
        const { std::cell::Cell::new(std::ptr::null_mut()) };
    static STAGE36_VIRTUAL_ID: std::cell::Cell<u32> =
        const { std::cell::Cell::new(0) };
    static STAGE36_VIRTUAL_TICKS: std::cell::Cell<u32> =
        const { std::cell::Cell::new(0) };
    static STAGE36_VIRTUAL_SEEN_PRESS: std::cell::Cell<bool> =
        const { std::cell::Cell::new(false) };
    static STAGE36_VIRTUAL_SEEN_CONNECTED: std::cell::Cell<bool> =
        const { std::cell::Cell::new(false) };
}

#[cfg(target_os = "macos")]
fn stage36_make_virtual_gamepad() {
    use sdl3::sys::joystick::{
        SDL_AttachVirtualJoystick, SDL_OpenJoystick,
        SDL_VirtualJoystickDesc,
    };
    let mut desc = SDL_VirtualJoystickDesc::new();
    desc.r#type = 1; // SDL_JOYSTICK_TYPE_GAMEPAD
    desc.naxes = 6;
    desc.nbuttons = 21;
    desc.button_mask = 1u32; // SOUTH/A only
    desc.axis_mask = 0x3fu32;
    desc.name = c"NeXium_Stage36_Only_Synthetic_Gamepad".as_ptr();
    let id = unsafe { SDL_AttachVirtualJoystick(&desc) };
    if id.0 == 0 {
        eprintln!("STAGE36_VIRTUAL_ATTACH_FAILED");
        return;
    }
    let ptr = unsafe { SDL_OpenJoystick(id) };
    if ptr.is_null() {
        eprintln!("STAGE36_VIRTUAL_OPEN_FAILED");
        return;
    }
    STAGE36_VIRTUAL_PAD.with(|p| p.set(ptr));
    STAGE36_VIRTUAL_ID.with(|value| value.set(id.0));
    eprintln!("STAGE36_VIRTUAL_ATTACHED_AND_OPENED");
}

#[cfg(target_os = "macos")]
fn stage36_send_synthetic_button() {
    use sdl3::sys::joystick::SDL_SetJoystickVirtualButton;
    STAGE36_VIRTUAL_PAD.with(|p| {
        let ptr = p.get();
        if ptr.is_null() { return; }
        STAGE36_VIRTUAL_TICKS.with(|ticks| {
            let n = ticks.get();
            ticks.set(n.saturating_add(1));
            let down = n >= 1 && n < 12;
            if !unsafe { SDL_SetJoystickVirtualButton(ptr, 0, down) } {
                if n == 1 { eprintln!("STAGE36_VIRTUAL_BUTTON_SET_FAILED"); }
            } else if n == 1 {
                eprintln!("STAGE36_VIRTUAL_SYNTHETIC_PRESS_SENT");
            } else if n == 12 {
                eprintln!("STAGE36_VIRTUAL_SYNTHETIC_RELEASE_SENT");
            }
        });
    });
}

#[cfg(target_os = "macos")]
fn stage36_observe_synthetic_snapshot(connected: bool, mapped_buttons: u64) {
    if connected {
        STAGE36_VIRTUAL_SEEN_CONNECTED.with(|seen| {
            if !seen.replace(true) {
                eprintln!("STAGE36_VIRTUAL_SNAPSHOT_CONNECTED");
            }
        });
    }
    if connected && mapped_buttons != 0 {
        STAGE36_VIRTUAL_SEEN_PRESS.with(|seen| {
            if !seen.replace(true) {
                eprintln!("STAGE36_VIRTUAL_SNAPSHOT_PRESS_MAPPED");
            }
        });
    } else if connected && mapped_buttons == 0 {
        STAGE36_VIRTUAL_SEEN_PRESS.with(|pressed| {
            if pressed.replace(false) {
                eprintln!("STAGE36_VIRTUAL_SNAPSHOT_RELEASE_MAPPED");
            }
        });
    }
}

'''

MAKE = r'''        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_VIRTUAL_BUTTON_TEST")
            .ok().as_deref() == Some("1")
        {
            stage36_make_virtual_gamepad();
        }
'''

SEND = r'''        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_VIRTUAL_BUTTON_TEST")
            .ok().as_deref() == Some("1")
        {
            stage36_send_synthetic_button();
        }
'''

OBSERVE = r'''        #[cfg(target_os = "macos")]
        if std::env::var("NEXIUM_MACOS_VIRTUAL_BUTTON_TEST")
            .ok().as_deref() == Some("1")
        {
            let virtual_pad_is_the_selected_source =
                STAGE36_VIRTUAL_ID.with(|id| id.get() != 0 &&
                    self.pad.as_ref().and_then(|pad| pad.id().ok())
                        .map(raw_joystick_id) == Some(id.get()));
            stage36_observe_synthetic_snapshot(
                snap.connected && virtual_pad_is_the_selected_source, snap.buttons);
        }
'''


def patch_source(source: str) -> str:
    generated=[SUPPORT,MAKE,SEND,OBSERVE]
    if VIRTUAL in source:
        if all(source.count(x)==1 for x in generated):
            return source
        raise RuntimeError("Stage36 incomplete synthetic fixture instrumentation")
    if source.count(IMPL)!=1 or source.count(CTOR)!=1 or source.count(POLL)!=1 or source.count(END)!=1:
        raise RuntimeError("pinned original InputBackend source structure drift")
    pre,post=source.split(IMPL,1)
    updated=pre+SUPPORT+IMPL+post
    updated=updated.replace(CTOR,CTOR+"\n"+MAKE,1)
    if updated.count(POLL_EVENT)!=1 or updated.count(END)!=1:
        raise RuntimeError("original SDL3 poll code unavailable")
    updated=updated.replace(POLL_EVENT,SEND+POLL_EVENT,1)
    updated=updated.replace(END,OBSERVE+END,1)
    if not (updated.index(SUPPORT)<updated.index(IMPL)<updated.index(CTOR)
            <updated.index(POLL)<updated.index(SEND+POLL_EVENT)
            <updated.index(OBSERVE)):
        raise RuntimeError("original virtual SDL3 source ordering invalid")
    return updated


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path)
    a=p.parse_args(argv)
    f=a.source/"nexium-gui/src/input.rs"
    try:
        old=f.read_text(encoding="utf-8")
        new=patch_source(old)
        if old != new: f.write_text(new,encoding="utf-8")
        print("STAGE36_SYNTHETIC_SDL3_PATCH_APPLIED" if old!=new
              else "STAGE36_SYNTHETIC_SDL3_PATCH_ALREADY_APPLIED")
        return 0
    except (OSError,UnicodeError,RuntimeError) as ex:
        print("STAGE36_SYNTHETIC_SDL3_PATCH_BLOCKED: "+str(ex),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
