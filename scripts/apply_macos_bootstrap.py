#!/usr/bin/env python3
"""First guarded source edits for an EXPERIMENTAL Intel macOS NeXium build.

Not a completed port. Fails rather than guessing when upstream source changes.
"""
import argparse
import sys
from pathlib import Path


def patch(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    if after in text:
        print(f"unchanged (already patched): {path}")
        return
    if text.count(before) != 1:
        raise RuntimeError(f"Source version mismatch: {path}; expected exactly one anchor")
    path.write_text(text.replace(before, after, 1), encoding="utf-8")
    print(f"patched: {path}")


def main(root: Path) -> None:
    root = root.expanduser().resolve()
    path = root / "nexium-gui/src/main.rs"
    before = ('    setup.instance_descriptor.backends =\n'
              '        eframe::wgpu::Backends::from_env().unwrap_or(eframe::wgpu::Backends::VULKAN);')
    after = '''    // Host UI uses native Metal on macOS; guest renderer remains Vulkan.
    let host_backend = if cfg!(target_os = "macos") {
        eframe::wgpu::Backends::METAL
    } else {
        eframe::wgpu::Backends::VULKAN
    };
    setup.instance_descriptor.backends =
        eframe::wgpu::Backends::from_env().unwrap_or(host_backend);'''
    patch(path, before, after)

    path = root / "nexium-gpu/src/adapter.rs"
    before = '''    let instance = unsafe {
        entry.create_instance(
            &vk::InstanceCreateInfo::default().application_info(&app),
            None,
        )
    }
    .map_err(|error| format!("create instance: {error:?}"))?;'''
    after = '''    // MoltenVK portability devices require explicit enumeration.
    #[cfg(target_os = "macos")]
    let portability_exts = [ash::khr::portability_enumeration::NAME.as_ptr()];
    #[cfg(target_os = "macos")]
    let instance_info = vk::InstanceCreateInfo::default()
        .application_info(&app)
        .flags(vk::InstanceCreateFlags::ENUMERATE_PORTABILITY_KHR)
        .enabled_extension_names(&portability_exts);
    #[cfg(not(target_os = "macos"))]
    let instance_info = vk::InstanceCreateInfo::default().application_info(&app);
    let instance = unsafe { entry.create_instance(&instance_info, None) }
        .map_err(|error| format!("create instance: {error:?}"))?;'''
    patch(path, before, after)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("upstream_checkout", type=Path)
    args = p.parse_args()
    try:
        main(args.upstream_checkout)
    except (OSError, RuntimeError) as error:
        print(f"BOOTSTRAP BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
