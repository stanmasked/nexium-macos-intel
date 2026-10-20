//! Minimal external eframe 0.37 control: no NeXium code, NRO or emulation.
struct ControlApp;

impl eframe::App for ControlApp {
    // eframe 0.37 (NeXium's pinned GUI minor) uses App::ui rather than update.
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        ui.heading("Intel macOS - independent eframe control");
        ui.label("No Nintendo files, emulator, rendering claims or audio.");
        ui.label("Minimal Wgpu/Metal versus Glow/OpenGL diagnostic.");
    }
}

fn main() -> Result<(), eframe::Error> {
    let selected = std::env::var("STAGE24_RENDERER")
        .unwrap_or_else(|_| String::from("wgpu"));
    let renderer = match selected.as_str() {
        "wgpu" => eframe::Renderer::Wgpu,
        "glow" => eframe::Renderer::Glow,
        _ => {
            eprintln!("STAGE24_INVALID_RENDERER");
            std::process::exit(2);
        }
    };
    eprintln!("STAGE24_CONTROL_RENDERER={}", selected);
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Stage24: independent Intel eframe control")
            .with_inner_size([720.0, 480.0]),
        renderer,
        ..Default::default()
    };
    eframe::run_native(
        "Stage24 independent eframe",
        options,
        Box::new(|_| Ok(Box::new(ControlApp))),
    )
}
