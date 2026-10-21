"""Stage36: immutable original NRO provenance, no false guest claims."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stage36_original_nro_mac_probe as stage


class Stage36OriginalHomebrew(unittest.TestCase):
    def test_exact_original_source_nro_name_and_digest_constants(self):
        self.assertEqual(stage.SOURCE_GAME_RUN,39501847103)
        self.assertEqual(stage.NRO_NAME,"vandal-hearts-prototype.nro")
        self.assertEqual(len(stage.NRO_SHA),64)
        self.assertEqual(stage.NRO_SIZE,299064)

    def test_refuses_unrelated_rom_or_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/"nexium"
            exe.write_bytes(b"not emulator")
            exe.chmod(0o755)  # Prove wrong digest, not a missing executable bit.
            game=Path(tmp)/"private-commercial-game.nro"
            game.write_bytes(b"test")
            with self.assertRaisesRegex(ValueError,"not original Stage32"):
                stage.validate_source(exe,game)

    def test_raw_guest_bytes_never_published(self):
        d=stage.sanitize(stage.MODES[0],{
            "alive_at_deadline":True,"window_found":True,
            "auto_loaded_nro":True,"guest_files":2})
        self.assertEqual(d["source_guest_sd_diagnostic_file_count"],2)
        self.assertFalse(d["complete_guest_boot_verified"])
        self.assertFalse(d["actual_gameplay_verified"])
        self.assertFalse(d["guest_sd_file_bytes_uploaded"])
        self.assertFalse(d["private_console_uploaded"])

    def test_live_process_without_guest_marker_not_boot_proof(self):
        d=stage.sanitize(stage.MODES[0],{"alive_at_deadline":True})
        self.assertTrue(d["process_alive_at_12s"])
        self.assertFalse(d["source_nro_auto_load_log_marker_observed"])
        self.assertFalse(d["complete_guest_boot_verified"])

    def test_control_does_not_pretend_guest_arg(self):
        d=stage.sanitize(stage.MODES[3],{"alive_at_deadline":True})
        self.assertIsNone(d["source_original_guest_nro_sha256"])
        self.assertFalse(d["exact_command_line_nro_argument_supplied"])

    def test_refuses_unknown_mode(self):
        with self.assertRaisesRegex(ValueError,"invalid"):
            stage.sanitize("commercial-rom-test",{})

    def test_failed_guest_load_not_reclassified_as_success(self):
        d=stage.sanitize(stage.MODES[0],{"failed_load_nro":True,
                                          "exited_nonzero":True})
        self.assertTrue(d["source_nro_failure_log_marker_observed"])
        self.assertTrue(d["process_exited_nonzero"])
        self.assertFalse(d["complete_guest_boot_verified"])

    def test_report_never_contains_private_home_paths(self):
        d=stage.sanitize(stage.MODES[0],{"guest_files":0})
        self.assertNotIn("/Users/",str(d))
        self.assertNotIn("file_contents",str(d))
        self.assertFalse(d["private_game_paths_uploaded"])

    def test_hash_file_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"sample"
            path.write_bytes(b"source provenance contract")
            self.assertEqual(stage.digest(path),stage.digest(path))
            self.assertEqual(len(stage.digest(path)),64)

    def test_genuine_nexium_file_logger_is_read_not_just_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            console=root/"console.txt"
            console.write_text("private stdout without loader marker")
            log=root/"nexium-data"/"logs"/"nexium-20261021-000000.log"
            log.parent.mkdir(parents=True)
            log.write_text("2026 INFO Auto-loaded NRO: original-homebrew")
            evidence=stage.collect_private_source_evidence(root,console)
            self.assertTrue(evidence["auto_loaded_nro"])
            self.assertFalse(evidence["failed_load_nro"])
            self.assertEqual(evidence["guest_files"],0)

    def test_exact_nexium_sdmc_path_and_no_private_data_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            console=root/"private.log"
            console.write_text("")
            guest=root/"nexium-data"/"sdmc"/"switch"/"vandal-hearts-remake"
            guest.mkdir(parents=True)
            (guest/"probe-receipt.csv").write_text("original diagnostic data")
            (guest/"empty.csv").write_text("")
            d=stage.collect_private_source_evidence(root,console)
            self.assertEqual(d["guest_files"],1)
            self.assertNotIn("diagnostic data",str(d))
            self.assertNotIn(str(root),str(d))

    def test_three_real_runner_boot_stages_independently_identified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            console=root/"console.log"
            console.write_text("")
            log=root/"nexium-data"/"logs"/"nexium-original.log"
            log.parent.mkdir(parents=True)
            log.write_text("Booting NRO: /isolated/homebrew.nro\\n"
                           "cpu memory null policy: strict fault\\n")
            original=stage.collect_private_source_evidence(root,console)
            self.assertTrue(original["booting_nro"])
            self.assertFalse(original["boot_failed"])
            self.assertTrue(original["cpu_memory_policy"])
            result=stage.sanitize(stage.MODES[0],original)
            self.assertTrue(result["runner_guest_cpu_context_initialization_observed"])
            self.assertFalse(result["guest_cpu_instructions_verified"])

    def test_runner_boot_failure_distinct_from_successful_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            c=root/"console.log"
            c.write_text("")
            log=root/"nexium-data"/"logs"/"nexium-boot-failure.log"
            log.parent.mkdir(parents=True)
            log.write_text("Auto-loaded NRO: fixture\\nBooting NRO: fixture\\n"
                           "Boot failed: invalid firmware\\n")
            original=stage.collect_private_source_evidence(root,c)
            result=stage.sanitize(stage.MODES[0],original)
            self.assertTrue(result["runner_guest_boot_attempt_observed"])
            self.assertTrue(result["runner_guest_boot_failure_observed"])
            self.assertFalse(result["runner_guest_cpu_context_initialization_observed"])
            self.assertFalse(result["complete_guest_boot_verified"])

    def test_false_guest_loader_marker_outside_exact_log_scope_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            console=root/"console.txt"
            console.write_text("")
            decoy=root/"nexium-data"/"other"
            decoy.mkdir(parents=True)
            (decoy/"nexium-20261021.log").write_text("Auto-loaded NRO: forged")
            evidence=stage.collect_private_source_evidence(root,console)
            self.assertFalse(evidence["auto_loaded_nro"])

    def test_kernel_phase_prefix_and_boot_error_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            c=root/"console"
            c.write_text("")
            p=root/"nexium-data"/"logs"/"nexium-20261021.log"
            p.parent.mkdir(parents=True)
            p.write_text("Loading NRO from: private-file\\n"
                         "Creating address space\\n"
                         "Mapping memory regions\\n"
                         "  Mapping heap @ 0x1234\\n"
                         "Boot failed: Failed to map heap: OutOfMemory\\n")
            evidence=stage.collect_private_source_evidence(root,c)
            self.assertEqual(evidence["boot_failure_category"],"GUEST_ADDRESS_MAPPING")
            self.assertEqual(evidence["kernel_boot_phases"],
                             ["00_LOADING_NRO","01_ADDRESS_SPACE_CREATED",
                              "02_MAPPING_MEMORY","03_MAPPING_HEAP"])
            receipt=stage.sanitize(stage.MODES[0],evidence)
            self.assertEqual(receipt["last_original_kernel_boot_phase_observed"],
                             "03_MAPPING_HEAP")
            self.assertNotIn("private-file",str(receipt))
            self.assertNotIn("OutOfMemory",str(receipt))

    def test_cpu_backend_failure_separate_from_real_execution(self):
        state={"boot_failure_category":stage.boot_failure_category(
            "Boot failed: Failed to init CPU: unavailable backend"),
            "kernel_boot_phases":["08_INITIALIZING_CPU"]}
        result=stage.sanitize(stage.MODES[0],state)
        self.assertEqual(result["boot_failure_safe_category"],"GUEST_CPU_INITIALIZATION")
        self.assertFalse(result["guest_cpu_instructions_verified"])

    def test_unknown_error_fails_safe_without_path_leak(self):
        error=stage.boot_failure_category("Boot failed: secret user home path /Users/user/private")
        self.assertEqual(error,"OTHER_UNCLASSIFIED_BOOT_ERROR")
        self.assertNotIn("user",error.lower())
        self.assertEqual(stage.boot_failure_category("normal startup"),"NO_BOOT_ERROR_OBSERVED")

    def test_guest_backend_a_b_preserves_exact_original_nro(self):
        standard=stage.sanitize(stage.MODES[0],{"boot_failed":True})
        rust=stage.sanitize(stage.MODES[1],{"cpu_memory_policy":True})
        self.assertEqual(standard["original_requested_cpu_backend"],"dynarmic")
        self.assertEqual(rust["original_requested_cpu_backend"],"rustarmic")
        self.assertTrue(rust["exact_command_line_nro_argument_supplied"])
        self.assertEqual(rust["source_original_guest_nro_sha256"],stage.NRO_SHA)
        self.assertFalse(rust["guest_cpu_instructions_verified"])
        self.assertFalse(rust["complete_guest_boot_verified"])

    def test_trace_target_proves_original_cpu_svc_without_raw_guest_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            console=root/"console.txt"
            console.write_text("")
            log=root/"nexium-data"/"logs"/"nexium-svc-sample.log"
            log.parent.mkdir(parents=True)
            log.write_text("[trace nexium_runner::boot] SVC 0x01 (count: 1)\\n"
                           "[trace nexium_runner::boot] SVC 0x22 (count: 2)\\n")
            evidence=stage.collect_private_source_evidence(root,console)
            self.assertEqual(evidence["runner_svc_count"],2)
            receipt=stage.sanitize(stage.MODES[2],evidence)
            self.assertTrue(receipt["source_guest_svc_event_observed"])
            self.assertEqual(receipt["original_runner_svc_trace_count"],2)
            self.assertNotIn("0x22",str(receipt))
            self.assertFalse(receipt["complete_guest_boot_verified"])

    def test_non_runner_text_not_misreported_as_svc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            console=root/"console.txt"
            console.write_text("SVC text without a real source count and hexadecimal")
            evidence=stage.collect_private_source_evidence(root,console)
            self.assertEqual(evidence["runner_svc_count"],0)

    def test_source_modes_are_distinct_and_not_commercial_game(self):
        self.assertEqual(len(set(stage.MODES)),4)
        self.assertEqual(stage.MODES[0],"original-homebrew-nro")
        self.assertEqual(stage.MODES[1],"rustarmic-homebrew-nro")
        self.assertEqual(stage.MODES[2],"rustarmic-svc-trace-nro")
        self.assertEqual(stage.MODES[3],"no-guest-control")

if __name__=="__main__":
    unittest.main()
