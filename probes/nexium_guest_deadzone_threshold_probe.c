#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage53: real libnx guest verifies SDL3 +/-3000 below original default
 * 0.12 deadzone disappears, while +/-6000 above it reaches both sticks.
 * The guest reads both sticks in the SAME padUpdate, never HID injection.
 */
static void mark(const char *s) { (void)svcOutputDebugString(s, strlen(s)); }

static bool centered(HidAnalogStickState a, HidAnalogStickState b) {
    return a.x == 0 && a.y == 0 && b.x == 0 && b.y == 0;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    mark("STAGE53_GUEST_THRESHOLD_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    mark("STAGE53_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const HidAnalogStickState left = padGetStickPos(&pad, 0);
        const HidAnalogStickState right = padGetStickPos(&pad, 1);
        const bool b = (buttons & HidNpadButton_B) != 0;
        if (buttons & ~(u64)HidNpadButton_B) {
            mark("STAGE53_GUEST_UNEXPECTED_DIGITAL_BUTTON\n");
            return 2;
        }
        const bool a = left.x > 4500 && left.y > 4500
            && right.x < -4500 && right.y < -4500;
        const bool reverse = left.x < -4500 && left.y < -4500
            && right.x > 4500 && right.y > 4500;
        const bool zero = centered(left, right);
        if (phase == 0 && b && zero) {
            mark("STAGE53_GUEST_B_BELOW_THRESHOLD_NEUTRAL\n");
            phase = 1;
        } else if (phase == 1 && b && a) {
            mark("STAGE53_GUEST_ABOVE_A_ALL_FOUR_AXES\n");
            phase = 2;
        } else if (phase == 2 && b && zero) {
            mark("STAGE53_GUEST_CENTER_AFTER_A\n");
            phase = 3;
        } else if (phase == 3 && b && reverse) {
            mark("STAGE53_GUEST_ABOVE_B_REVERSED_ALL_AXES\n");
            phase = 4;
        } else if (phase == 4 && b && zero) {
            mark("STAGE53_GUEST_CENTER_AFTER_B\n");
            phase = 5;
        } else if (phase == 5 && !b && zero) {
            mark("STAGE53_GUEST_RELEASE_NEUTRAL\n");
            mark("STAGE53_GUEST_THRESHOLD_PASS\n");
            return 0;
        }
        (void)svcSleepThread(16666667ULL);
    }
    mark("STAGE53_GUEST_THRESHOLD_INCOMPLETE\n");
    return 2;
}
