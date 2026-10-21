#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage45: SDL3 negative LeftY denotes up. Original InputBackend inverts Y,
 * so actual guest libnx left.y must be positive for up, negative for down.
 * Use real padUpdate / padGetStickPos, never direct HID injection.
 */
static void marker(const char *value) {
    (void)svcOutputDebugString(value, strlen(value));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    marker("STAGE45_GUEST_STICK_Y_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    marker("STAGE45_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const HidAnalogStickState left = padGetStickPos(&pad, 0);
        const bool b = (buttons & HidNpadButton_B) != 0;
        const bool unexpected = (buttons & (HidNpadButton_A
            | HidNpadButton_Up | HidNpadButton_Right)) != 0;
        if (unexpected) {
            marker("STAGE45_GUEST_UNEXPECTED_DIGITAL_BUTTON\n");
            return 2;
        }

        if (phase == 0 && b && left.y > -4000 && left.y < 4000) {
            marker("STAGE45_GUEST_B_NEUTRAL_FIRST\n");
            phase = 1;
        } else if (phase == 1 && b && left.y > 12000) {
            marker("STAGE45_GUEST_LEFT_Y_UP_POSITIVE\n");
            phase = 2;
        } else if (phase == 2 && b && left.y > -4000 && left.y < 4000) {
            marker("STAGE45_GUEST_LEFT_Y_CENTER_AFTER_UP\n");
            phase = 3;
        } else if (phase == 3 && b && left.y < -12000) {
            marker("STAGE45_GUEST_LEFT_Y_DOWN_NEGATIVE\n");
            phase = 4;
        } else if (phase == 4 && b && left.y > -4000 && left.y < 4000) {
            marker("STAGE45_GUEST_LEFT_Y_CENTER_AFTER_DOWN\n");
            phase = 5;
        } else if (phase == 5 && !b && left.y > -4000 && left.y < 4000) {
            marker("STAGE45_GUEST_B_RELEASED_NEUTRAL\n");
            marker("STAGE45_GUEST_STICK_Y_PASS\n");
            return 0;
        }
        (void)svcSleepThread(16666667ULL);
    }
    marker("STAGE45_GUEST_STICK_Y_INCOMPLETE\n");
    return 2;
}
