#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage50: real libnx simultaneous digital DPad and 4-axis two-stick input.
 * Virtual SDL3 SOUTH/B is held throughout two opposite diagonals:
 *   B, B+Up+diagonal A, B neutral, B+Right+diagonal B, B neutral, released.
 * Digital DPad and both sticks MUST be coherent within each padUpdate().
 * No synthetic guest memory or HID injection.
 */
static void marker(const char *value) {
    (void)svcOutputDebugString(value, strlen(value));
}

static bool centered(HidAnalogStickState l, HidAnalogStickState r) {
    return l.x > -4000 && l.x < 4000 && l.y > -4000 && l.y < 4000
        && r.x > -4000 && r.x < 4000 && r.y > -4000 && r.y < 4000;
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    marker("STAGE50_GUEST_MIXED_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    marker("STAGE50_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const HidAnalogStickState left = padGetStickPos(&pad, 0);
        const HidAnalogStickState right = padGetStickPos(&pad, 1);
        const u64 permitted = HidNpadButton_B | HidNpadButton_Up | HidNpadButton_Right;

        if ((buttons & ~permitted) || ((buttons & HidNpadButton_Up)
                                      && (buttons & HidNpadButton_Right))) {
            marker("STAGE50_GUEST_SPURIOUS_OR_OVERLAPPED_DIGITAL\n");
            return 2;
        }

        const bool b_only = buttons == HidNpadButton_B;
        const bool b_up = buttons == (HidNpadButton_B | HidNpadButton_Up);
        const bool b_right = buttons == (HidNpadButton_B | HidNpadButton_Right);
        const bool diagonal_a =
            left.x < -12000 && left.y > 12000
            && right.x > 12000 && right.y < -12000;
        const bool diagonal_b =
            left.x > 12000 && left.y < -12000
            && right.x < -12000 && right.y > 12000;
        const bool neutral = centered(left, right);

        if (phase == 0 && b_only && neutral) {
            marker("STAGE50_GUEST_B_ONLY_ALL_NEUTRAL\n");
            phase = 1;
        } else if (phase == 1 && b_up && diagonal_a) {
            marker("STAGE50_GUEST_B_UP_AND_DUAL_DIAGONAL_A\n");
            phase = 2;
        } else if (phase == 2 && b_only && neutral) {
            marker("STAGE50_GUEST_B_ONLY_CENTER_AFTER_A\n");
            phase = 3;
        } else if (phase == 3 && b_right && diagonal_b) {
            marker("STAGE50_GUEST_B_RIGHT_AND_DUAL_DIAGONAL_B\n");
            phase = 4;
        } else if (phase == 4 && b_only && neutral) {
            marker("STAGE50_GUEST_B_ONLY_CENTER_AFTER_B\n");
            phase = 5;
        } else if (phase == 5 && buttons == 0 && neutral) {
            marker("STAGE50_GUEST_ALL_RELEASED_NEUTRAL\n");
            marker("STAGE50_GUEST_MIXED_PASS\n");
            return 0;
        }
        (void)svcSleepThread(16666667ULL);
    }

    marker("STAGE50_GUEST_MIXED_INCOMPLETE\n");
    return 2;
}
