#!/usr/bin/env python3
"""Apply a guarded, opt-in *minimal eframe* A/B experiment to pinned NeXium.

When NEXIUM_MACOS_MINIMAL_EFRAME=1 on macOS, the SAME compiled NeXium
executable starts a minimal egui/eframe/Wgpu window without initializing
the normal emulator host systems or HorizonApp. Default behavior is unchanged.

This is only a graphical startup isolation probe, never a functional port.
"""
import argparse
from pathlib import Path
import sys

ANCHOR = "fn main() -> Result<(), eframe::Error> {\n"
MARKER = "STAGE22_MINIMAL_EFRAME_ENTERED"
PREFIX = r'''// Stage22 Intel/macOS experimental diagnostic only.
#[cfg(target_os = "macos")]
struct Stage22MinimalEframe;

#[cfg(target_os = "macos")]
impl eframe::App for Stage22MinimalEframe {
    // Pinned eframe 0.37 App trait uses ui(&mut egui::Ui), NOT update(ctx).
    // Mirror HorizonApp in upstream nexium-gui/src/app.rs.
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        ui.heading("NeXium Intel - eframe startup isolation");
        ui.label("No NRO, game initialization or audio assertions.");
    }
}

'''
EARLY = r'''    // Stage22: identical binary; only the runtime startup path differs.
    #[cfg(target_os = "macos")]
    if std::env::var("NEXIUM_MACOS_MINIMAL_EFRAME").ok().as_deref() == Some("1") {
        eprintln!("STAGE22_MINIMAL_EFRAME_ENTERED");
        let options = eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_title("NeXium Intel eframe startup isolation")
                .with_inner_size([720.0, 480.0]),
            renderer: eframe::Renderer::Wgpu,
            wgpu_options: eframe::WgpuConfiguration {
                wgpu_setup: eframe::egui_wgpu::WgpuSetup::CreateNew(
                    host_wgpu_setup(None),
                ),
                ..Default::default()
            }
            .with_surface_config(host_surface_config(true)),
            ..Default::default()
        };
        return eframe::run_native(
            "NeXium minimal eframe",
            options,
            Box::new(|_| Ok(Box::new(Stage22MinimalEframe))),
        );
    }
'''

def patch_text(source: str) -> str:
    if MARKER in source:
        if source.count(MARKER) == 1 and PREFIX in source and EARLY in source:
            return source
        raise RuntimeError("stage22 partly edited or inconsistent; no write")
    if source.count(ANCHOR) != 1 or "fn host_wgpu_setup(" not in source or "fn host_surface_config(" not in source:
        raise RuntimeError("pinned source anchors missing or ambiguous")
    return source.replace(ANCHOR, PREFIX + ANCHOR + EARLY, 1)

def apply(root: Path) -> bool:
    target = root / "nexium-gui/src/main.rs"
    content = target.read_text(encoding="utf-8")
    updated = patch_text(content)
    if updated == content:
        return False
    target.write_text(updated, encoding="utf-8")
    return True

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path)
    args=p.parse_args()
    try:
        changed=apply(args.source)
        print("STAGE22_MINIMAL_EFRAME_PATCH_APPLIED" if changed else
              "STAGE22_MINIMAL_EFRAME_ALREADY_APPLIED")
    except (RuntimeError,OSError,UnicodeError) as exc:
        print("STAGE22_MINIMAL_EFRAME_PATCH_BLOCKED: " + str(exc),file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
