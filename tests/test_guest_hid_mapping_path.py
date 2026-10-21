"""Regression tests for the pinned guest HID IPC/SVC source audit."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_guest_hid_mapping_path as audit


def sources(root, *, guest_va=True, bind=True, cpu_map=True, zero_handle=True, unmap_noop=True):
    for relative in (
        "nexium-kernel/src/kernel",
        "nexium-kernel/src/services/hid",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    svc = """
pub fn dispatch(kernel: &mut Kernel, imm: u16) -> u32 {
    match imm {
        0x13 => svc_map_shared_memory(kernel),
        0x14 => svc_unmap_shared_memory(kernel),
        _ => 0,
    }
}
fn svc_map_shared_memory(kernel: &mut Kernel) -> u32 {
    let (handle, addr, size, perm) = (1u32, 0x1000u64, 0x40000u64, 3u32);
    log::debug!("svcMapSharedMemory handle={:#x}", handle);
"""
    if zero_handle:
        svc += """    if handle == 0 {
        log::error!("handle 0; placeholder");
    }
"""
    svc += """    if size as usize == crate::hid_state::HID_SHMEM_SIZE {
        if kernel.address_space.host_region_at(addr).is_none() {
            kernel.address_space.map(addr, size, Perm::RW, "hid_shmem").unwrap();
        }
        let Some(region) = kernel.address_space.host_region_at(addr) else { return 1; };
        let state = crate::hid_state::get_hid_state();
        let mut hid = state.lock();
"""
    if guest_va:
        svc += "        hid.shmem_va = Some(addr);\n"
    svc += "        kernel.hid_mapped_host_ptr = Some(region.host_ptr as usize);\n"
    if bind:
        svc += "        unsafe { hid.bind_mapped_host(region.host_ptr); }\n"
    if cpu_map:
        svc += "        unsafe { cpu.map_host(region.base, region.size, region.perm, region.host_ptr); }\n"
    svc += """    } else if kernel.time_shmem_handle == Some(handle) {
        log::debug!("time");
    }
}
"""
    if unmap_noop:
        svc += """fn svc_unmap_shared_memory(_kernel: &mut Kernel) -> u32 {
    log::debug!("svcUnmapSharedMemory");
    SUCCESS
}
"""
    else:
        svc += """fn svc_unmap_shared_memory(kernel: &mut Kernel) -> u32 {
    kernel.hid_mapped_host_ptr = None;
    SUCCESS
}
"""
    svc += """fn svc_signal_event(kernel: &mut Kernel) -> u32 { SUCCESS }
fn subsession_service(port_name: &str, cmd_id: u32) -> Option<&'static str> {
    match (port_name, cmd_id) {
        ("hid", 0) => Some("IAppletResource"),
        _ => None,
    }
}
fn applet_command_response(_kernel: &mut Kernel, port_name: &str, cmd_id: u32) {}
"""
    svc += """
if port_name == "IAppletResource" && cmd_id == 0 {
    let h = kernel.handles.create_handle(HandleType::SharedMemory);
    return build_ipc_response_copy(ctx, 0, &[], &[h]);
}
if port_name == "mm:u" { return Vec::new(); }
"""
    (root / "nexium-kernel/src/kernel/svc.rs").write_text(svc)
    hid = """
pub const HID_SHMEM_SIZE: usize = 0x40000;
pub const NPAD_BUTTON_B: u64 = 1 << 1;
fn write_npad_lifo_entry() {}
fn tick_with_source() {
    if self.mapped_host_ptr != 0 {
        unsafe {
            std::ptr::copy_nonoverlapping(
                self.buf.as_ptr(),
                self.mapped_host_ptr as *mut u8,
                HID_SHMEM_SIZE,
            );
        }
    }
}
fn trace_published_input() {}
"""
    (root / "nexium-kernel/src/hid_state.rs").write_text(hid)


class GuestHidMapAuditTests(unittest.TestCase):
    def test_complete_source_route_and_limits_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root)
            result = audit.audit(root)
            self.assertEqual(result["result"], "GUEST_HID_IPC_AND_SVC_MAP_SOURCE_PATH_PRESENT_HANDLE_AND_UNMAP_LIMITATIONS_CONFIRMED")
            self.assertTrue(result["source_contract_checks"]["guest_hid_cmd0_returns_iappletresource_session"])
            self.assertTrue(result["source_contract_checks"]["iappletresource_cmd0_returns_shared_memory_handle"])
            self.assertTrue(result["source_contract_checks"]["map_binds_original_hid_buffer_to_host_region"])
            self.assertEqual(result["guest_hid_shared_memory_path"]["handle_validation"], "NOT_VALIDATED_BY_HID_SIZE_BRANCH")
            self.assertEqual(result["guest_hid_shared_memory_path"]["unmap_behavior"], "NO_OP; DOES_NOT_CLEAR_SHMEM_VA_OR_UNBIND_HOST_POINTER")
            self.assertFalse(result["runtime_guest_map_call_observed"])
            self.assertFalse(result["guest_read_of_npad_report_observed"])

    def test_fails_closed_if_guest_va_not_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root, guest_va=False)
            with self.assertRaisesRegex(ValueError, "map_sets_guest_virtual_address"):
                audit.audit(root)

    def test_fails_closed_if_hid_buffer_not_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root, bind=False)
            with self.assertRaisesRegex(ValueError, "map_binds_original_hid_buffer"):
                audit.audit(root)

    def test_fails_closed_if_cpu_mapping_disappears(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root, cpu_map=False)
            with self.assertRaisesRegex(ValueError, "map_attempts_cpu_host_registration"):
                audit.audit(root)

    def test_requires_zero_handle_warning_and_size_only_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root, zero_handle=False)
            with self.assertRaisesRegex(ValueError, "handle-validation behavior changed"):
                audit.audit(root)

    def test_requires_audited_unmap_behavior_to_be_rechecked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root, unmap_noop=False)
            with self.assertRaisesRegex(ValueError, "unmap cleanup limitation changed"):
                audit.audit(root)

    def test_requires_original_npad_lifo_serialization_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources(root)
            p = root / "nexium-kernel/src/hid_state.rs"
            p.write_text(p.read_text().replace("fn write_npad_lifo_entry() {}", "fn unrelated() {}"))
            with self.assertRaisesRegex(ValueError, "original_source_serializes_npad_lifo"):
                audit.audit(root)

    def test_missing_pinned_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "missing pinned source file"):
                audit.audit(Path(td))


if __name__ == "__main__":
    unittest.main()
