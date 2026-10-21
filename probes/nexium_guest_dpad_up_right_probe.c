#include <switch.h>
#include <stdbool.h>
#include <string.h>

/* Genuine guest libnx button reads. No synthetic HID/guest memory injection. */
static void mark(const char *message) {
    (void)svcOutputDebugString(message, strlen(message));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    mark("STAGE43_GUEST_DPAD_PROBE_START\n");

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    mark("STAGE43_GUEST_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const bool b = (buttons & HidNpadButton_B) != 0;
        const bool up = (buttons & HidNpadButton_Up) != 0;
        const bool right = (buttons & HidNpadButton_Right) != 0;
        const bool any_other = (buttons & HidNpadButton_A) != 0;

        if (any_other || (up && right)) {
            mark("STAGE43_GUEST_DPAD_UNEXPECTED_BUTTON\n");
            return 2;
        }

        if (phase == 0 && b && !up && !right) {
            mark("STAGE43_GUEST_B_ONLY_FIRST\n");
            phase = 1;
        } else if (phase == 1 && b && up && !right) {
            mark("STAGE43_GUEST_B_AND_UP\n");
            phase = 2;
        } else if (phase == 2 && b && !up && !right) {
            mark("STAGE43_GUEST_B_ONLY_AFTER_UP\n");
            phase = 3;
        } else if (phase == 3 && b && !up && right) {
            mark("STAGE43_GUEST_B_AND_RIGHT\n");
            phase = 4;
        } else if (phase == 4 && b && !up && !right) {
            mark("STAGE43_GUEST_B_ONLY_AFTER_RIGHT\n");
            phase = 5;
        } else if (phase == 5 && !b && !up && !right) {
            mark("STAGE43_GUEST_ALL_RELEASED\n");
            mark("STAGE43_GUEST_DPAD_PASS\n");
            return 0;
        }

        (void)svcSleepThread(16666667ULL);
    }

    mark("STAGE43_GUEST_DPAD_INCOMPLETE\n");
    return 2;
}
