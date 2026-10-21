#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage48: verify both original libnx PadState sticks simultaneously.
 * SDL3 sends two opposite four-axis diagonals, with centers in between.
 * Guest must see all four axes in the same padUpdate() frame. No HID
 * memory modification or guest address injection is used.
 */
static void mark(const char *s) { (void)svcOutputDebugString(s, strlen(s)); }

static bool center(HidAnalogStickState l, HidAnalogStickState r) {
    return l.x > -4000 && l.x < 4000 && l.y > -4000 && l.y < 4000
        && r.x > -4000 && r.x < 4000 && r.y > -4000 && r.y < 4000;
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    mark("STAGE48_GUEST_DUAL_STICK_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    mark("STAGE48_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const bool b = (buttons & HidNpadButton_B) != 0;
        const bool other = (buttons & (HidNpadButton_A
            | HidNpadButton_Up | HidNpadButton_Right)) != 0;
        const HidAnalogStickState l = padGetStickPos(&pad, 0);
        const HidAnalogStickState r = padGetStickPos(&pad, 1);

        if (other) {
            mark("STAGE48_GUEST_UNEXPECTED_DIGITAL_BUTTON\n");
            return 2;
        }

        const bool diag_a = l.x < -12000 && l.y > 12000
            && r.x > 12000 && r.y < -12000;
        const bool diag_b = l.x > 12000 && l.y < -12000
            && r.x < -12000 && r.y > 12000;
        if (phase == 0 && b && center(l, r)) {
            mark("STAGE48_GUEST_B_AND_ALL_NEUTRAL\n");
            phase = 1;
        } else if (phase == 1 && b && diag_a) {
            mark("STAGE48_GUEST_B_AND_DUAL_DIAGONAL_A\n");
            phase = 2;
        } else if (phase == 2 && b && center(l, r)) {
            mark("STAGE48_GUEST_DUAL_CENTER_AFTER_A\n");
            phase = 3;
        } else if (phase == 3 && b && diag_b) {
            mark("STAGE48_GUEST_B_AND_DUAL_DIAGONAL_B\n");
            phase = 4;
        } else if (phase == 4 && b && center(l, r)) {
            mark("STAGE48_GUEST_DUAL_CENTER_AFTER_B\n");
            phase = 5;
        } else if (phase == 5 && !b && center(l, r)) {
            mark("STAGE48_GUEST_ALL_RELEASED_AND_NEUTRAL\n");
            mark("STAGE48_GUEST_DUAL_STICK_PASS\n");
            return 0;
        }
        (void)svcSleepThread(16666667ULL);
    }

    mark("STAGE48_GUEST_DUAL_STICK_INCOMPLETE\n");
    return 2;
}
