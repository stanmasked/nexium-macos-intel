#!/usr/bin/env python3
"""Audit the pinned NeXium guest HID IPC -> SVC mapping route without a game NRO.

This is a source contract audit, not runtime proof that a guest applet maps or
reads the region. It intentionally reports the handle-validation and unmap
limitations instead of treating a size-matched host buffer as proof of guest
consumption.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys


PIN = "089562567a0a8760dfdd8420e1f57c35159a9219"


def read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"missing pinned source file: {relative}")
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def between(source: str, start: str, end: str) -> str:
    begin = source.find(start)
    if begin < 0:
        raise ValueError(f"source anchor missing: {start}")
    finish = source.find(end, begin + len(start))
    if finish < 0:
        raise ValueError(f"source end anchor missing: {end}")
    return source[begin:finish]


def audit(root: Path) -> dict:
    svc = read(root, "nexium-kernel/src/kernel/svc.rs")
    hid_state = read(root, "nexium-kernel/src/hid_state.rs")

    route = between(svc, "fn subsession_service(", "\nfn applet_command_response(")
    applet_resource = between(
        svc,
        'if port_name == "IAppletResource" && cmd_id == 0 {',
        '\n    if port_name == "mm:u" {',
    )
    map_svc = between(svc, "fn svc_map_shared_memory(", "\nfn svc_unmap_shared_memory(")
    unmap_svc = between(svc, "fn svc_unmap_shared_memory(", "\nfn svc_signal_event(")
    dispatch = between(svc, "pub fn dispatch(kernel:", "\nfn ")
    tick = between(hid_state, "fn tick_with_source(", "\nfn trace_published_input(")

    has_ipc_route = bool(re.search(
        r'\(\s*"hid"\s*,\s*0\s*\)\s*=>\s*Some\("IAppletResource"\)', route
    ))
    has_handle_reply = (
        "create_handle(HandleType::SharedMemory)" in applet_resource
        and "build_ipc_response_copy(ctx, 0, &[], &[h])" in applet_resource
    )
    has_svc_dispatch = (
        re.search(r"0x13\s*=>\s*svc_map_shared_memory\(kernel\)", dispatch) is not None
        and re.search(r"0x14\s*=>\s*svc_unmap_shared_memory\(kernel\)", dispatch) is not None
    )
    has_size_gate = "if size as usize == crate::hid_state::HID_SHMEM_SIZE {" in map_svc
    has_guest_va = "hid.shmem_va = Some(addr);" in map_svc
    has_host_ptr = "kernel.hid_mapped_host_ptr = Some(region.host_ptr as usize);" in map_svc
    has_binding = "hid.bind_mapped_host(region.host_ptr);" in map_svc
    has_cpu_mapping = "cpu.map_host(region.base, region.size, region.perm, region.host_ptr)" in map_svc
    has_zero_handle_warning = 'if handle == 0 {' in map_svc and "return" not in between(
        map_svc, 'if handle == 0 {', "if size as usize == crate::hid_state::HID_SHMEM_SIZE {"
    )
    size_gate_ignores_handle = has_size_gate and "handle" not in between(
        map_svc,
        "if size as usize == crate::hid_state::HID_SHMEM_SIZE {",
        "} else if kernel.time_shmem_handle",
    )
    unmap_is_noop = (
        "fn svc_unmap_shared_memory(_kernel: &mut Kernel)" in unmap_svc
        and "SUCCESS" in unmap_svc
        and "shmem_va" not in unmap_svc
        and "unbind_mapped_host" not in unmap_svc
        and "hid_mapped_host_ptr" not in unmap_svc
    )
    copies_buffer_to_mapping = (
        "std::ptr::copy_nonoverlapping(" in tick
        and "self.buf.as_ptr()" in tick
        and "self.mapped_host_ptr as *mut u8" in tick
        and "HID_SHMEM_SIZE" in tick
    )
    serializes_npad = (
        "fn write_npad_lifo_entry(" in hid_state
        and "NPAD_BUTTON_B" in hid_state
        and "fn trace_published_input(" in hid_state
    )

    checks = {
        "guest_hid_cmd0_returns_iappletresource_session": has_ipc_route,
        "iappletresource_cmd0_returns_shared_memory_handle": has_handle_reply,
        "svc_dispatch_has_map_and_unmap_shared_memory": has_svc_dispatch,
        "map_shared_memory_has_hid_size_gate": has_size_gate,
        "map_sets_guest_virtual_address": has_guest_va,
        "map_registers_kernel_host_pointer": has_host_ptr,
        "map_binds_original_hid_buffer_to_host_region": has_binding,
        "map_attempts_cpu_host_registration": has_cpu_mapping,
        "hid_buffer_is_copied_into_mapped_region_each_tick": copies_buffer_to_mapping,
        "original_source_serializes_npad_lifo": serializes_npad,
    }
    missing = [name for name, present in checks.items() if not present]
    if missing:
        raise ValueError("pinned guest HID path changed or incomplete: " + ", ".join(missing))

    if not has_zero_handle_warning or not size_gate_ignores_handle:
        raise ValueError("expected current size-based mapping/handle-validation behavior changed")
    if not unmap_is_noop:
        raise ValueError("expected current unmap cleanup limitation changed; re-audit before classifying")

    return {
        "schema": "nexium-stage39-guest-hid-map-source-audit/v1",
        "pinned_upstream_revision": PIN,
        "result": "GUEST_HID_IPC_AND_SVC_MAP_SOURCE_PATH_PRESENT_HANDLE_AND_UNMAP_LIMITATIONS_CONFIRMED",
        "source_contract_checks": checks,
        "guest_hid_shared_memory_path": {
            "ipc_route": "hid cmd 0 -> IAppletResource",
            "handle_reply": "IAppletResource cmd 0 returns a SharedMemory-typed handle",
            "mapping_trigger": "svcMapSharedMemory with size == HID_SHMEM_SIZE",
            "mapping_effect": "maps a guest VA to a host region, records shmem_va, binds original HidState buffer, and attempts CPU map_host",
            "handle_validation": "NOT_VALIDATED_BY_HID_SIZE_BRANCH",
            "zero_handle_behavior": "LOGS_ERROR_BUT_DOES_NOT_RETURN_BEFORE_SIZE_BRANCH",
            "unmap_behavior": "NO_OP; DOES_NOT_CLEAR_SHMEM_VA_OR_UNBIND_HOST_POINTER",
            "host_npad_lifo_serialization": "SOURCE_PRESENT",
        },
        "runtime_guest_map_call_observed": False,
        "guest_read_of_npad_report_observed": False,
        "game_nro_supplied": False,
        "gameplay_verified": False,
        "real_switch_verified": False,
        "raw_logs_or_memory_pointers_included": False,
        "next_runtime_proof_needed": [
            "observe guest SVC 0x13 call with the HID-size mapping and correlate its handle to IAppletResource.GetSharedMemoryHandle",
            "read the mapped guest VA or instrument the guest load path and verify NPad B press then release",
            "verify SVC 0x14 cleanup before changing/tearing down the mapping",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root)
        encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print("STAGE39_GUEST_HID_MAP_AUDIT_BLOCKED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
