#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage52: original processed analog deadzone must suppress +/-1000 raw SDL
 * jitter on all four axes, while SOUTH/B is held and later released.
 * Guest uses actual libnx PadState, no direct HID memory writes.
 */
static void mark(const char *text) {
    (void)svcOutputDebugString(text, strlen(text));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    mark("STAGE52_GUEST_JITTER_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    mark("STAGE52_GUEST_PAD_INIT_CALLED\n");

    unsigned b_neutral_frames = 0;
    bool held = false;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const HidAnalogStickState left = padGetStickPos(&pad, 0);
        const HidAnalogStickState right = padGetStickPos(&pad, 1);
        if (left.x != 0 || left.y != 0 || right.x != 0 || right.y != 0) {
            mark("STAGE52_GUEST_ANALOG_DEADZONE_LEAK\n");
            return 2;
        }
        if (buttons & (HidNpadButton_A | HidNpadButton_Up | HidNpadButton_Right)) {
            mark("STAGE52_GUEST_UNEXPECTED_DIGITAL_BUTTON\n");
            return 2;
        }
        const bool b = (buttons & HidNpadButton_B) != 0;
        if (!held && b) {
            held = true;
            b_neutral_frames = 1;
            mark("STAGE52_GUEST_JITTER_B_NEUTRAL_FIRST\n");
        } else if (held && b) {
            ++b_neutral_frames;
            if (b_neutral_frames == 8) {
                mark("STAGE52_GUEST_JITTER_B_NEUTRAL_PERSISTED\n");
            }
        } else if (held && !b && b_neutral_frames >= 8) {
            mark("STAGE52_GUEST_JITTER_RELEASE_NEUTRAL\n");
            mark("STAGE52_GUEST_JITTER_PASS\n");
            return 0;
        } else if (held && !b && b_neutral_frames < 8) {
            mark("STAGE52_GUEST_B_HOLD_TOO_SHORT\n");
            return 2;
        }
        (void)svcSleepThread(16666667ULL);
    }
    mark("STAGE52_GUEST_JITTER_INCOMPLETE\n");
    return 2;
}
