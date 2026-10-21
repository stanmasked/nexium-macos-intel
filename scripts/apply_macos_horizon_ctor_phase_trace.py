#!/usr/bin/env python3
"""Stage28: marker-only, fail-closed subphase trace for real HorizonApp::new.

Runs on a pinned experimental local NeXium checkout after Stage26. This does
not suppress any constructor operation or alter normal GUI logic. Only
NEXIUM_MACOS_CONSTRUCTOR_PHASE_TRACE=1 prints static phase identifiers.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

START = "    pub fn new(\n        cc: &eframe::CreationContext<'_>,"
END = "    fn apply_theme(ctx: &egui::Context)"
MARKER = "STAGE28_HORIZON_CTOR_PHASE_"
PHASES = (
    ("00_BEFORE_THEME", "        Self::apply_theme(&cc.egui_ctx);"),
    ("01_BEFORE_UI_AUDIO", "        crate::ui_audio::init(app_settings.audio_output_device.as_deref());"),
    ("02_AFTER_UI_AUDIO", "        let gamepad = app_settings.gamepad.clone();"),
    ("03_BEFORE_INPUT", "        let input = InputBackend::new("),
    ("04_AFTER_INPUT", "        let nro_path = nro_arg.unwrap_or_default();"),
    ("05_BEFORE_NEXTENDO", "        let nextendo = crate::nextendo::Nextendo::start("),
    ("06_AFTER_NEXTENDO", "        let mut app = Self {"),
    ("07_AFTER_STRUCT", "        app.reload_profile_texture(&cc.egui_ctx);"),
    ("08_AFTER_PROFILE", "        crate::ui_audio::set_sfx_volume(app.app_settings.sfx_volume);"),
    ("09_AFTER_SFX", "        crate::ui_audio::set_carousel_track(app.app_settings.menu_music_track);"),
    ("10_BEFORE_RESCAN", "        app.library\n            .rescan("),
    ("11_AFTER_RESCAN", "        if !nro_path.is_empty() {"),
    ("12_BEFORE_RETURN", "        app\n    }\n"),
)

def emitted(label: str) -> str:
    return ('        #[cfg(target_os = "macos")]\n'
            '        if std::env::var("NEXIUM_MACOS_CONSTRUCTOR_PHASE_TRACE")'
            '.ok().as_deref() == Some("1") {\n'
            '            eprintln!("' + MARKER + label + '");\n'
            '        }\n')

def patch_source(data: str) -> str:
    expected=[MARKER+name for name,_ in PHASES]
    if MARKER in data:
        if all(data.count(marker+'";')==1 for marker in expected) and (
            data.count(MARKER)==len(PHASES)):
            return data
        raise RuntimeError("partial Stage28 markers or source mismatch")
    if data.count(START)!=1 or data.count(END)!=1:
        raise RuntimeError("pinned HorizonApp constructor boundaries missing or ambiguous")
    before,tail=data.split(START,1)
    ctor,after=tail.split(END,1)
    ctor=START+ctor
    if "impl eframe::App for HorizonApp" not in data:
        raise RuntimeError("HorizonApp eframe trait implementation missing")
    positions=[]
    for name,anchor in PHASES:
        if ctor.count(anchor)!=1:
            raise RuntimeError("constructor phase anchor absent or duplicated: "+name)
        positions.append(ctor.index(anchor))
    if positions != sorted(positions) or len(set(positions))!=len(positions):
        raise RuntimeError("constructor phases out of expected order")
    for name,anchor in PHASES:
        ctor=ctor.replace(anchor,emitted(name)+anchor,1)
    return before+ctor+END+after

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    args=parser.parse_args(argv)
    path=args.source/"nexium-gui/src/app.rs"
    try:
        old=path.read_text(encoding="utf-8")
        new=patch_source(old)
        if new!=old:
            path.write_text(new,encoding="utf-8")
        print("STAGE28_CTOR_PHASE_PATCH_APPLIED" if new!=old
              else "STAGE28_CTOR_PHASE_PATCH_ALREADY_APPLIED")
    except (OSError,UnicodeError,RuntimeError) as exc:
        print("STAGE28_CTOR_PHASE_PATCH_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
