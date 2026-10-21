"""Stage46: prove audio startup A/B auditor never invents audio or game proof."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_audio_original_gui as stage

SHA="b"*64
def receipt(alive=True,window=True):
    return dict(
        probe="no_nro_gui_process_only",emulator_sha256=SHA,duration_limit_seconds=12,
        nro_verified=False,gameplay_verified=False,gui_verified=False,
        alive_at_deadline=alive,window_found=window,
        outcome="alive_without_gui_verification" if alive else "exited_nonzero",
        window_probe="own_visible_window_observed" if window else "not_requested",
        exit_signal=None if alive else "SIGABRT"
    )
def marks(*names):
    return "".join(x+"\n" for x in names)

class Stage46AudioStartupTests(unittest.TestCase):
    def test_full_audio_off_original_gui(self):
        row=stage.validate("audio-off",receipt(),marks(*stage.SOURCE_LABELS))
        self.assertTrue(row["original_sdl3_poll_returned"])

    def test_full_audio_on_original_gui(self):
        row=stage.validate("audio-on",receipt(),marks(*stage.SOURCE_LABELS))
        self.assertTrue(row["own_visible_window_identified"])

    def test_audio_on_genuine_crash_is_not_success(self):
        row=stage.validate("audio-on",receipt(False,False),
                marks(*stage.SOURCE_LABELS[:2]))
        self.assertFalse(row["process_alive_at_12_seconds"])

    def test_source_markers_required_for_successful_process(self):
        with self.assertRaisesRegex(ValueError,"checkpoint"):
            stage.validate("audio-on",receipt(),marks(*stage.SOURCE_LABELS[:2]))

    def test_repeated_source_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            stage.validate("audio-on",receipt(False,False),
                marks(stage.SOURCE_LABELS[0],stage.SOURCE_LABELS[0]))

    def test_unknown_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"unknown"):
            stage.validate("audio-on",receipt(False,False),
                marks("STAGE40_PRIVATE_KEY_NAME"))

    def test_fake_gui_pixel_success_rejected(self):
        data=receipt()
        data["gui_verified"]=True
        with self.assertRaisesRegex(ValueError,"unwarranted"):
            stage.validate("audio-on",data,marks(*stage.SOURCE_LABELS))

    def test_fake_gameplay_success_rejected(self):
        data=receipt()
        data["gameplay_verified"]=True
        with self.assertRaisesRegex(ValueError,"unwarranted"):
            stage.validate("audio-on",data,marks(*stage.SOURCE_LABELS))

    def test_unowned_window_rejected(self):
        data=receipt()
        data["window_probe"]="not_requested"
        with self.assertRaisesRegex(ValueError,"window"):
            stage.validate("audio-on",data,marks(*stage.SOURCE_LABELS))

    def test_raw_audio_device_path_is_never_published(self):
        result=stage.validate("audio-on",receipt(),marks(*stage.SOURCE_LABELS)+
            "\n/Users/private/SecretGame.nro\nCoreAudio device=private input\n")
        self.assertNotIn("private",str(result))
        self.assertNotIn("SecretGame",str(result))
        self.assertNotIn("CoreAudio device",str(result))

    def test_winit_reentrancy_is_detected_without_raw_trace(self):
        result=stage.validate("audio-on",receipt(False,False),
            marks(*stage.SOURCE_LABELS[:2])+stage.PANIC)
        self.assertTrue(result["winit_reentrant_panic"])
        self.assertNotIn(stage.PANIC,repr(result))

    def test_synthetic_unknown_mode_rejected(self):
        with self.assertRaisesRegex(ValueError,"unknown"):
            stage.validate("unexpected",receipt(),marks(*stage.SOURCE_LABELS))

if __name__=="__main__":
    unittest.main()
