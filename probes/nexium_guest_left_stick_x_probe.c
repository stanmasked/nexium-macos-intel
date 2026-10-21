#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage44 source-authentic libnx left analog stick X readback.
 * SDL3 virtual LeftX crosses negative/zero/positive/zero while B is held;
 * the guest sees only the original mapped HidNpadState and PadState.
 */
static void mark(const char *message) {
    (void)svcOutputDebugString(message, strlen(message));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    mark("STAGE44_GUEST_STICK_X_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);
    mark("STAGE44_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const HidAnalogStickState left = padGetStickPos(&pad, 0);
        const bool b = (buttons & HidNpadButton_B) != 0;
        const bool other = (buttons & (HidNpadButton_A
            | HidNpadButton_Up | HidNpadButton_Right)) != 0;
        if (other) {
            mark("STAGE44_GUEST_UNEXPECTED_DIGITAL_BUTTON\n");
            return 2;
        }
        if (phase == 0 && b && left.x > -4000 && left.x < 4000) {
            mark("STAGE44_GUEST_B_NEUTRAL_FIRST\n");
            phase = 1;
        } else if (phase == 1 && b && left.x < -12000) {
            mark("STAGE44_GUEST_LEFT_X_NEGATIVE\n");
            phase = 2;
        } else if (phase == 2 && b && left.x > -4000 && left.x < 4000) {
            mark("STAGE44_GUEST_LEFT_X_CENTER_AFTER_NEGATIVE\n");
            phase = 3;
        } else if (phase == 3 && b && left.x > 12000) {
            mark("STAGE44_GUEST_LEFT_X_POSITIVE\n");
            phase = 4;
        } else if (phase == 4 && b && left.x > -4000 && left.x < 4000) {
            mark("STAGE44_GUEST_LEFT_X_CENTER_AFTER_POSITIVE\n");
            phase = 5;
        } else if (phase == 5 && !b && left.x > -4000 && left.x < 4000) {
            mark("STAGE44_GUEST_B_RELEASED_NEUTRAL\n");
            mark("STAGE44_GUEST_STICK_X_PASS\n");
            return 0;
        }
        (void)svcSleepThread(16666667ULL);
    }

    mark("STAGE44_GUEST_STICK_X_INCOMPLETE\n");
    return 2;
}
