//! Independent native macOS GUI-stack experiment.
//! No NeXium sources, firmware, game images, guest assets, or audio.
//! Two modes use the same eframe/winit event loop:
//!   wgpu: Metal renderer with NeXium's without_display_handle setup
//!   glow: OpenGL renderer baseline through the same GUI event loop
use eframe::{egui, egui_wgpu};

#[derive(Default)]
struct Control;

impl eframe::App for Control {
    // eframe 0.37 uses App::ui(&mut egui::Ui), not the older App::update.
    // Match the actual pinned NeXium HorizonApp implementation.
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        ui.heading("Intel macOS GUI stack control");
        ui.label("No ROM, firmware, emulator, or NRO is involved.");
        ui.label("This is only a host window/event-loop smoke experiment.");
    }
}

fn main() -> Result<(), eframe::Error> {
    let mode = std::env::var("NEXIUM_GUI_CONTROL_RENDERER")
        .ok()
        .or_else(|| std::env::args().nth(1))
        .unwrap_or_else(|| "wgpu".into());
    if mode != "wgpu" && mode != "glow" {
        eprintln!("GUI_CONTROL_BLOCKED: mode must be 'wgpu' or 'glow'");
        std::process::exit(2);
    }
    println!("GUI_CONTROL_MODE={mode}");
    let mut options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("NeXium Intel GUI stack control")
            .with_inner_size([640.0, 480.0]),
        renderer: if mode == "wgpu" {
            eframe::Renderer::Wgpu
        } else {
            eframe::Renderer::Glow
        },
        ..Default::default()
    };
    if mode == "wgpu" {
        let mut setup = egui_wgpu::WgpuSetupCreateNew::without_display_handle();
        setup.instance_descriptor.backends = eframe::wgpu::Backends::METAL;
        options.wgpu_options = eframe::WgpuConfiguration {
            wgpu_setup: egui_wgpu::WgpuSetup::CreateNew(setup),
            ..Default::default()
        };
    }
    eframe::run_native(
        "NeXium Intel GUI stack control",
        options,
        Box::new(|_cc| Ok(Box::new(Control::default()))),
    )
}
