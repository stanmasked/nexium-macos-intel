#!/usr/bin/env python3
"""Pin-safe opt-in minimal eframe renderer comparison, Stage23 Intel macOS.

Run only after Stage22's minimal eframe patch. A single Rust Intel Mach-O
supports both Wgpu and Glow, selected by a runtime environment variable;
normal NeXium startup is unaffected.
"""
import argparse
from pathlib import Path
import sys

ORIGINAL = '''            renderer: eframe::Renderer::Wgpu,
            wgpu_options: eframe::WgpuConfiguration {
                wgpu_setup: eframe::egui_wgpu::WgpuSetup::CreateNew(
                    host_wgpu_setup(None),
                ),'''
UPDATED = '''            renderer: stage23_renderer,
            wgpu_options: eframe::WgpuConfiguration {
                wgpu_setup: eframe::egui_wgpu::WgpuSetup::CreateNew(
                    host_wgpu_setup(None),
                ),'''
INSERT_BEFORE = '''        let options = eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_title("NeXium Intel eframe startup isolation")'''
EXPERIMENT = '''        // Stage23: controlled renderer A/B within the same freshly built
        // Intel Mac executable; only active in Stage22's minimal GUI branch.
        let stage23_renderer_name = std::env::var("NEXIUM_MACOS_MINIMAL_RENDERER")
            .unwrap_or_else(|_| "wgpu".to_owned());
        let stage23_renderer = match stage23_renderer_name.as_str() {
            "wgpu" => eframe::Renderer::Wgpu,
            "glow" => eframe::Renderer::Glow,
            _ => {
                eprintln!("STAGE23_RENDERER_INVALID");
                std::process::exit(2);
            }
        };
        eprintln!("STAGE23_EFRAME_RENDERER_SELECTED={}", stage23_renderer_name);
'''
MARKER = 'STAGE23_EFRAME_RENDERER_SELECTED='

# E0599 prevention: the pinned eframe 0.37 Renderer::Glow enum member is
# cfg-gated behind the explicit "glow" feature. Upstream selects only wgpu.
CARGO_ORIGINAL = 'eframe = { version = "0.37", features = ["wgpu"] }'
CARGO_UPDATED = 'eframe = { version = "0.37", features = ["wgpu", "glow"] }'

def patch_cargo(data: str) -> str:
    if CARGO_UPDATED in data:
        if data.count(CARGO_UPDATED) != 1 or CARGO_ORIGINAL in data:
            raise RuntimeError("Cargo manifest partly patched or ambiguous")
        return data
    if data.count(CARGO_ORIGINAL) != 1:
        raise RuntimeError("pinned eframe Cargo feature anchor missing or ambiguous")
    return data.replace(CARGO_ORIGINAL, CARGO_UPDATED, 1)

def patch_source(data: str) -> str:
    if MARKER in data:
        if data.count(MARKER) != 1 or EXPERIMENT not in data or UPDATED not in data:
            raise RuntimeError("source partially patched or unexpected drift")
        return data
    if 'STAGE22_MINIMAL_EFRAME_ENTERED' not in data:
        raise RuntimeError("Stage22 minimal eframe source is required first")
    if data.count(ORIGINAL) != 1 or data.count(INSERT_BEFORE) != 1:
        raise RuntimeError("source anchors missing or not unique")
    data = data.replace(INSERT_BEFORE, EXPERIMENT + INSERT_BEFORE, 1)
    data = data.replace(ORIGINAL, UPDATED, 1)
    return data

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    args=parser.parse_args(argv)
    path=args.source/'nexium-gui/src/main.rs'
    cargo_path=args.source/'nexium-gui/Cargo.toml'
    try:
        old=path.read_text(encoding='utf-8')
        old_cargo=cargo_path.read_text(encoding='utf-8')
        # Validate BOTH files before editing EITHER. A source-drift failure
        # must never leave a partial local build checkout behind.
        new=patch_source(old)
        new_cargo=patch_cargo(old_cargo)
        if new!=old:
            path.write_text(new,encoding='utf-8')
        if new_cargo!=old_cargo:
            cargo_path.write_text(new_cargo,encoding='utf-8')
        print('STAGE23_RENDERER_PATCH_APPLIED' if new!=old or new_cargo!=old_cargo
              else 'STAGE23_RENDERER_PATCH_ALREADY_APPLIED')
        print('STAGE23_EFRAME_GLOW_FEATURE_VERIFIED')
    except (OSError, UnicodeError, RuntimeError) as exc:
        print('STAGE23_RENDERER_PATCH_BLOCKED: '+str(exc),file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
