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
    try:
        old=path.read_text(encoding='utf-8')
        new=patch_source(old)
        if new!=old:
            path.write_text(new,encoding='utf-8')
        print('STAGE23_RENDERER_PATCH_APPLIED' if new!=old else 'STAGE23_RENDERER_PATCH_ALREADY_APPLIED')
    except (OSError, UnicodeError, RuntimeError) as exc:
        print('STAGE23_RENDERER_PATCH_BLOCKED: '+str(exc),file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
