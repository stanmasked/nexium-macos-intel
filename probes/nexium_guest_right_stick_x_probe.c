#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage46: authentic libnx right-stick X readback on native Intel NeXium.
 * Negative -> center -> positive -> center, with SOUTH/B held throughout.
 * The guest reads only actual NPad shared memory via PadState.
 */
static void marker(const char *value) {
    (void)svcOutputDebugString(value, strlen(value));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    marker("STAGE46_GUEST_RIGHT_X_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);
    marker("STAGE46_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const HidAnalogStickState right = padGetStickPos(&pad, 1);
        const bool b = (buttons & HidNpadButton_B) != 0;
        const bool other = (buttons & (HidNpadButton_A
            | HidNpadButton_Up | HidNpadButton_Right)) != 0;

        if (other) {
            marker("STAGE46_GUEST_UNEXPECTED_DIGITAL_BUTTON\n");
            return 2;
        }

        if (phase == 0 && b && right.x > -4000 && right.x < 4000) {
            marker("STAGE46_GUEST_B_NEUTRAL_FIRST\n");
            phase = 1;
        } else if (phase == 1 && b && right.x < -12000) {
            marker("STAGE46_GUEST_RIGHT_X_NEGATIVE\n");
            phase = 2;
        } else if (phase == 2 && b && right.x > -4000 && right.x < 4000) {
            marker("STAGE46_GUEST_RIGHT_X_CENTER_AFTER_NEGATIVE\n");
            phase = 3;
        } else if (phase == 3 && b && right.x > 12000) {
            marker("STAGE46_GUEST_RIGHT_X_POSITIVE\n");
            phase = 4;
        } else if (phase == 4 && b && right.x > -4000 && right.x < 4000) {
            marker("STAGE46_GUEST_RIGHT_X_CENTER_AFTER_POSITIVE\n");
            phase = 5;
        } else if (phase == 5 && !b && right.x > -4000 && right.x < 4000) {
            marker("STAGE46_GUEST_B_RELEASED_NEUTRAL\n");
            marker("STAGE46_GUEST_RIGHT_X_PASS\n");
            return 0;
        }
        (void)svcSleepThread(16666667ULL);
    }

    marker("STAGE46_GUEST_RIGHT_X_INCOMPLETE\n");
    return 2;
}
