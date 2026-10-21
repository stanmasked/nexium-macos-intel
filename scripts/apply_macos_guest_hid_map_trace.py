#!/usr/bin/env python3
"""Apply an opt-in, pointer-free trace to the pinned guest HID SVC map path.

The patch changes diagnostics only. With the environment flag absent or not
exactly "1", it emits no Stage40 markers and does not change mapping behavior.
"""
from __future__ import annotations
import sys
from pathlib import Path

RELATIVE = Path("nexium-kernel/src/kernel/svc.rs")
ENV = 'std::env::var("NEXIUM_EXPERIMENT_STAGE40_GUEST_HID_MAP_TRACE").as_deref() == Ok("1")'
PATCH_MARKER = "STAGE40_GUEST_HID_MAP_TRACE_PATCHED"
MARKERS = (
    "STAGE40_SVC_MAP_SHARED_MEMORY_ENTER",
    "STAGE40_SVC_MAP_SIZE_MATCH_HID",
    "STAGE40_SVC_MAP_SIZE_OTHER",
    "STAGE40_SVC_MAP_HANDLE_NONZERO",
    "STAGE40_SVC_MAP_HANDLE_ZERO",
    "STAGE40_HID_SHARED_MEMORY_HOST_BOUND",
    "STAGE40_HID_SHARED_MEMORY_CPU_MAP_OK",
    "STAGE40_HID_SHARED_MEMORY_CPU_MAP_FAILED",
    "STAGE40_SVC_UNMAP_SHARED_MEMORY_NOOP",
)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one pinned source anchor, found {count}")
    return source.replace(old, new, 1)


def patch_source(original: str) -> str:
    if PATCH_MARKER in original:
        if original.count(PATCH_MARKER) != 1 or any(original.count(m) != 1 for m in MARKERS):
            raise RuntimeError("Stage40 partial/duplicate trace markers")
        return original
    if any(m in original for m in MARKERS):
        raise RuntimeError("Stage40 partial/extra trace markers")

    source = replace_once(
        original,
        "fn svc_map_shared_memory(kernel: &mut Kernel) -> u32 {\n",
        "// STAGE40_GUEST_HID_MAP_TRACE_PATCHED: opt-in SVC markers only.\n"
        "fn svc_map_shared_memory(kernel: &mut Kernel) -> u32 {\n",
        "map function marker",
    )

    map_log = '''    log::debug!(
        "svcMapSharedMemory handle={:#x} addr={:#x} size={:#x} perm={:#x}",'''
    map_trace = f'''    if {ENV} {{
        eprintln!("STAGE40_SVC_MAP_SHARED_MEMORY_ENTER");
        if size as usize == crate::hid_state::HID_SHMEM_SIZE {{
            eprintln!("STAGE40_SVC_MAP_SIZE_MATCH_HID");
        }} else {{
            eprintln!("STAGE40_SVC_MAP_SIZE_OTHER");
        }}
        if handle != 0 {{
            eprintln!("STAGE40_SVC_MAP_HANDLE_NONZERO");
        }} else {{
            eprintln!("STAGE40_SVC_MAP_HANDLE_ZERO");
        }}
    }}
'''
    source = replace_once(source, map_log, map_trace + map_log, "map entry trace")

    bind = "            hid.bind_mapped_host(region.host_ptr);\n"
    bound_trace = f'''            hid.bind_mapped_host(region.host_ptr);
            if {ENV} {{
                eprintln!("STAGE40_HID_SHARED_MEMORY_HOST_BOUND");
            }}
'''
    source = replace_once(source, bind, bound_trace, "host bind trace")

    cpu_result = '''                if let Err(e) = cpu.map_host(region.base, region.size, region.perm, region.host_ptr)
                {
                    log::warn!("failed to map HID shmem in CPU: {}", e);
                }'''
    cpu_trace = f'''                if let Err(e) = cpu.map_host(region.base, region.size, region.perm, region.host_ptr)
                {{
                    if {ENV} {{
                        eprintln!("STAGE40_HID_SHARED_MEMORY_CPU_MAP_FAILED");
                    }}
                    log::warn!("failed to map HID shmem in CPU: {{}}", e);
                }} else if {ENV} {{
                    eprintln!("STAGE40_HID_SHARED_MEMORY_CPU_MAP_OK");
                }}'''
    source = replace_once(source, cpu_result, cpu_trace, "CPU map result trace")

    unmap_log = '    log::debug!("svcUnmapSharedMemory");\n'
    unmap_trace = f'''    log::debug!("svcUnmapSharedMemory");
    if {ENV} {{
        eprintln!("STAGE40_SVC_UNMAP_SHARED_MEMORY_NOOP");
    }}
'''
    source = replace_once(source, unmap_log, unmap_trace, "unmap trace")

    if source.count(PATCH_MARKER) != 1 or any(source.count(m) != 1 for m in MARKERS):
        raise RuntimeError("Stage40 trace markers failed final uniqueness check")
    return source


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: apply_macos_guest_hid_map_trace.py UPSTREAM_ROOT", file=sys.stderr)
        return 2
    path = Path(args[0]) / RELATIVE
    try:
        original = path.read_text(encoding="utf-8")
        patched = patch_source(original)
        if patched != original:
            path.write_text(patched, encoding="utf-8")
            print("STAGE40_GUEST_HID_MAP_TRACE_PATCHED")
        else:
            print("STAGE40_GUEST_HID_MAP_TRACE_ALREADY_PRESENT")
        return 0
    except (OSError, RuntimeError) as error:
        print("STAGE40_GUEST_HID_MAP_TRACE_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
