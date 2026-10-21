"""Stage40 opt-in SVC HID map trace patcher regression tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_macos_guest_hid_map_trace as patcher


def fixture():
    return '''fn svc_map_shared_memory(kernel: &mut Kernel) -> u32 {
    let (handle, addr, size, perm) = (1u32, 0x1000u64, 0x40000u64, 3u32);
    log::debug!(
        "svcMapSharedMemory handle={:#x} addr={:#x} size={:#x} perm={:#x}",
        handle,
        addr,
        size,
        perm
    );
    if size as usize == crate::hid_state::HID_SHMEM_SIZE {
        let region = kernel.address_space.host_region_at(addr).unwrap();
        let mut hid = get_hid_state().lock();
        unsafe {
            hid.bind_mapped_host(region.host_ptr);
        }
        if let Some(cpu) = cpu_mut() {
            unsafe {
                if let Err(e) =
                    cpu.map_host(region.base, region.size, region.perm, region.host_ptr)
                {
                    log::warn!("failed to map HID shmem in CPU: {}", e);
                }
            }
        }
    }
}
fn svc_unmap_shared_memory(_kernel: &mut Kernel) -> u32 {
    log::debug!("svcUnmapSharedMemory");
    SUCCESS
}
'''


class Stage40GuestHidMapTraceTests(unittest.TestCase):
    def test_patches_original_map_bind_cpu_and_unmap_anchors(self):
        source = patcher.patch_source(fixture())
        for marker in patcher.MARKERS:
            self.assertEqual(source.count(marker), 1, marker)
        self.assertIn("size as usize == crate::hid_state::HID_SHMEM_SIZE", source)
        self.assertIn("handle != 0", source)
        self.assertIn("hid.bind_mapped_host(region.host_ptr)", source)
        self.assertIn("STAGE40_HID_SHARED_MEMORY_CPU_MAP_OK", source)
        self.assertIn("STAGE40_HID_SHARED_MEMORY_CPU_MAP_FAILED", source)
        self.assertIn("STAGE40_SVC_UNMAP_SHARED_MEMORY_NOOP", source)

    def test_idempotent(self):
        first = patcher.patch_source(fixture())
        self.assertEqual(patcher.patch_source(first), first)

    def test_rejects_partial_marker(self):
        with self.assertRaisesRegex(RuntimeError, "partial/extra"):
            patcher.patch_source(fixture() + "\n// STAGE40_SVC_MAP_SIZE_MATCH_HID\n")

    def test_rejects_duplicate_anchor(self):
        with self.assertRaisesRegex(RuntimeError, "map entry trace"):
            patcher.patch_source(fixture().replace(
                '    log::debug!(\n        "svcMapSharedMemory',
                '    log::debug!(\n        "svcMapSharedMemory',
                1
            ) + '\n    log::debug!(\n        "svcMapSharedMemory handle={:#x} addr={:#x} size={:#x} perm={:#x}",\n'
        )

    def test_rejects_missing_cpu_map_anchor(self):
        with self.assertRaisesRegex(RuntimeError, "CPU map result trace"):
            patcher.patch_source(fixture().replace(
                'cpu.map_host(region.base, region.size, region.perm, region.host_ptr)',
                'cpu.map_host(region.base, region.size, region.perm, region.host_ptr /* drift */)',
            ))

    def test_requires_all_unmap_anchor(self):
        with self.assertRaisesRegex(RuntimeError, "unmap trace"):
            patcher.patch_source(fixture().replace(
                '    log::debug!("svcUnmapSharedMemory");\n',
                '    log::debug!("svcUnmapSharedMemory changed");\n',
            ))

    def test_trace_is_explicitly_opt_in(self):
        source = patcher.patch_source(fixture())
        self.assertGreaterEqual(source.count(
            'std::env::var("NEXIUM_EXPERIMENT_STAGE40_GUEST_HID_MAP_TRACE").as_deref() == Ok("1")'
        ), 4)

    def test_trace_contains_no_raw_address_or_handle_values(self):
        source = patcher.patch_source(fixture())
        self.assertNotIn('eprintln!("STAGE40_SVC_MAP_SHARED_MEMORY_ENTER handle={}', source)
        self.assertNotIn('eprintln!("STAGE40_SVC_MAP_SHARED_MEMORY_ENTER addr={}', source)


if __name__ == "__main__":
    unittest.main()
