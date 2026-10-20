#!/usr/bin/env python3
"""Stage26: keep HorizonApp::new but substitute inert UI on Intel macOS.

Apply ONLY after Stage25 on the same pinned NeXium checkout. Normal NeXium
behavior remains unchanged unless NEXIUM_MACOS_HORIZON_CTOR_ONLY=1.
"""
import argparse
from pathlib import Path
import sys

from apply_macos_full_init_minimal_app import UPDATED as STAGE25_CREATOR

MAIN_ANCHOR = "fn main() -> Result<(), eframe::Error> {\n"
ENTER = "STAGE26_HORIZON_CTOR_ENTERED"
RETURNED = "STAGE26_HORIZON_CTOR_RETURNED"

# Hold the original constructed HorizonApp for the full lifetime of eframe::App,
# but NEVER call its potentially re-entrant logic/ui methods. No emulated game.
WRAPPER = r'''// Stage26: constructor versus GUI frame isolation (Intel macOS only).
#[cfg(target_os = "macos")]
struct Stage26HorizonCtorOnly {
    _inner: HorizonApp,
}
#[cfg(target_os = "macos")]
impl eframe::App for Stage26HorizonCtorOnly {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        ui.heading("NeXium Intel - HorizonApp constructor-only isolation");
        ui.label("No original HorizonApp UI, game/NRO, or audio assertions.");
    }
}

'''

CTOR_CASE = r'''            // Stage26: perform the *real* HorizonApp constructor, but
            // retain it under a minimal UI wrapper to suppress first-frame
            // calls to its ordinary eframe::App implementation.
            #[cfg(target_os = "macos")]
            if std::env::var("NEXIUM_MACOS_HORIZON_CTOR_ONLY")
                .ok().as_deref() == Some("1")
            {
                eprintln!("STAGE26_HORIZON_CTOR_ENTERED");
                let inner = HorizonApp::new(
                    cc,
                    log_feed_for_app.take(),
                    settings.clone(),
                    nro_arg.clone(),
                );
                eprintln!("STAGE26_HORIZON_CTOR_RETURNED");
                return Ok(Box::new(Stage26HorizonCtorOnly { _inner: inner })
                    as Box<dyn eframe::App>);
            }
'''
INSERT_ANCHOR = "            Ok(Box::new(HorizonApp::new(\n"
if STAGE25_CREATOR.count(INSERT_ANCHOR) != 1:
    raise RuntimeError("internal Stage25 constructor anchor mismatch")
STAGE26_CREATOR = STAGE25_CREATOR.replace(
    INSERT_ANCHOR, CTOR_CASE + INSERT_ANCHOR, 1
)

def patch_source(text: str) -> str:
    if RETURNED in text or ENTER in text:
        if (text.count(RETURNED) == 1 and text.count(ENTER) == 1
                and text.count(WRAPPER) == 1 and STAGE26_CREATOR in text
                and STAGE25_CREATOR not in text):
            return text
        raise RuntimeError("Stage26 partial or unexpected source edit")
    if "STAGE22_MINIMAL_EFRAME_ENTERED" not in text:
        raise RuntimeError("Stage22 early minimal eframe path missing")
    if text.count(MAIN_ANCHOR) != 1 or text.count(STAGE25_CREATOR) != 1:
        raise RuntimeError("pinned Stage25 app-creator or main anchor missing or ambiguous")
    return text.replace(MAIN_ANCHOR, WRAPPER + MAIN_ANCHOR, 1).replace(
        STAGE25_CREATOR, STAGE26_CREATOR, 1
    )

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    args=parser.parse_args(argv)
    source=args.source/"nexium-gui/src/main.rs"
    try:
        original=source.read_text(encoding="utf-8")
        patched=patch_source(original)
        if patched != original:
            source.write_text(patched,encoding="utf-8")
        print("STAGE26_HORIZON_CTOR_PATCH_APPLIED" if patched!=original
              else "STAGE26_HORIZON_CTOR_ALREADY_APPLIED")
    except (OSError,UnicodeError,RuntimeError) as exc:
        print("STAGE26_HORIZON_CTOR_PATCH_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    sys.exit(main())
