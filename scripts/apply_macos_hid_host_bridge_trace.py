#!/usr/bin/env python3
"""Stage37: trace host SDL SOUTH->Switch B at real HidState update_input boundary.

No ROM, no guest process, no controller data. This only establishes host-side
HidState reception of the original mapped synthetic virtual SDL3 button.
Never claim guest NPAD shared memory was read. Strict pinned app.rs anchor.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ANCHOR='''            hid.update_input(nexium_core::hid_state::ControllerInput {
                buttons,
                stick_l_x: sticks[0],
                stick_l_y: sticks[1],
                stick_r_x: sticks[2],
                stick_r_y: sticks[3],
            });
'''
MARKER="STAGE37_HID_BRIDGE_"
INSERT=r'''            // Stage37 research only. Actual guest HID state and original
            // host ControllerInput.update_input are not replaced or spoofed.
            #[cfg(target_os = "macos")]
            if std::env::var("NEXIUM_MACOS_STAGE37_HID_BRIDGE_TRACE")
                .ok().as_deref() == Some("1")
                && std::env::var("NEXIUM_MACOS_VIRTUAL_BUTTON_TEST")
                    .ok().as_deref() == Some("1")
            {
                static STAGE37_SWITCH_B_DOWN: std::sync::atomic::AtomicBool =
                    std::sync::atomic::AtomicBool::new(false);
                let switch_b = SwitchButton::B.npad_bit();
                let original_snapshot_contains_b = gp_buttons & switch_b != 0;
                let host_hid_state_contains_b = hid.input.buttons & switch_b != 0;
                if original_snapshot_contains_b && host_hid_state_contains_b {
                    if !STAGE37_SWITCH_B_DOWN.swap(true, std::sync::atomic::Ordering::Relaxed) {
                        eprintln!("STAGE37_HID_BRIDGE_SYNTHETIC_B_PRESS_HOST_STATE");
                        if hid.shmem_va.is_none() {
                            eprintln!("STAGE37_HID_BRIDGE_NO_GUEST_NPAD_SHMEM");
                        } else {
                            eprintln!("STAGE37_HID_BRIDGE_GUEST_SHMEM_MAPPING_PRESENT_UNVERIFIED");
                        }
                    }
                } else if !original_snapshot_contains_b && !host_hid_state_contains_b
                    && STAGE37_SWITCH_B_DOWN.swap(false, std::sync::atomic::Ordering::Relaxed)
                {
                    eprintln!("STAGE37_HID_BRIDGE_SYNTHETIC_B_RELEASE_HOST_STATE");
                }
            }
'''

def patch_source(original: str) -> str:
    if MARKER in original:
        if original.count(INSERT)==1 and original.count(MARKER)==4:
            return original
        raise RuntimeError("Stage37 partial/extra HID evidence markers")
    if original.count(ANCHOR)!=1:
        raise RuntimeError("original HorizonApp->HidState update_input anchor absent or doubled")
    if original.count("self.last_input.to_npad()")!=1:
        raise RuntimeError("original InputSnapshot->NPad mapping path changed")
    if original.count("let (gp_buttons, gp_sticks)")!=1:
        raise RuntimeError("original SDL3 mapped button variable not unique")
    if original.count("let mut buttons = kb_buttons | gp_buttons;")!=1:
        raise RuntimeError("host controller/keyboard merge no longer pinned")
    at=original.index(ANCHOR)
    if original.index("self.last_input.to_npad()")>=at:
        raise RuntimeError("original SDL3 mapped path moved after host HID write")
    return original.replace(ANCHOR, ANCHOR+INSERT,1)


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    args=parser.parse_args(argv)
    path=args.source/"nexium-gui/src/app.rs"
    try:
        original=path.read_text(encoding="utf-8")
        updated=patch_source(original)
        if updated!=original:
            path.write_text(updated,encoding="utf-8")
        print("STAGE37_GUEST_HID_BOUNDARY_PATCHED" if updated!=original
              else "STAGE37_GUEST_HID_BOUNDARY_ALREADY_PATCHED")
        return 0
    except (RuntimeError,UnicodeError,OSError) as error:
        print("STAGE37_GUEST_HID_BOUNDARY_PATCH_BLOCKED: "+str(error),file=sys.stderr)
        return 2


if __name__=="__main__":
    sys.exit(main())
