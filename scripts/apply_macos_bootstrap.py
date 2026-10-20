#!/usr/bin/env python3
"""First guarded source edits for an EXPERIMENTAL Intel macOS NeXium build.

Not a completed port. Fails rather than guessing when upstream source changes.
"""
import argparse
import sys
from pathlib import Path


def checked_patch(path: Path, before: str, after: str):
    """Validate an upstream anchor without modifying any source file."""
    text = path.read_text(encoding="utf-8")
    if after in text:
        print(f"unchanged (already patched): {path}")
        return (path, None)
    if text.count(before) != 1:
        raise RuntimeError(f"Source version mismatch: {path}; expected exactly one anchor")
    return (path, text.replace(before, after, 1))


def main(root: Path) -> None:
    root = root.expanduser().resolve()
    edits = []
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
    edits.append(checked_patch(path, before, after))

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
    edits.append(checked_patch(path, before, after))

    # A second Vulkan instance is created for optional GPU clock management.
    # It must also enumerate MoltenVK portability devices on macOS.
    path = root / "nexium-gpu/src/max_clocks.rs"
    before = '''        let instance = unsafe {
            entry.create_instance(&vk::InstanceCreateInfo::default().application_info(&app), None)
        }
        .map_err(|error| format!("create instance: {error:?}"))?;'''
    after = '''        #[cfg(target_os = "macos")]
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
    edits.append(checked_patch(path, before, after))

    # Atomic from the caller's point of view: an unmatched upstream anchor
    # anywhere must not leave previously touched sources partially modified.
    for path, modified in edits:
        if modified is not None:
            path.write_text(modified, encoding="utf-8")
            print(f"patched: {path}")



if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("upstream_checkout", type=Path)
    args = p.parse_args()
    try:
        main(args.upstream_checkout)
    except (OSError, RuntimeError) as error:
        print(f"BOOTSTRAP BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
