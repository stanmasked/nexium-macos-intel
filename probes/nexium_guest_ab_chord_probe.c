#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage42: genuine guest libnx padGetButtons test of two independent buttons.
 * Stage36+40+42 drive SDL SOUTH/B for a long hold and EAST/A for a shorter,
 * fully nested hold, via original GUI/InputBackend/HidState paths.
 * No host input injection or direct guest memory modification occurs here.
 */
static void marker(const char *text) {
    (void)svcOutputDebugString(text, strlen(text));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    marker("STAGE42_GUEST_AB_PROBE_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);
    marker("STAGE42_GUEST_AB_PAD_INIT_CALLED\n");

    unsigned phase = 0;
    for (u32 frame = 0; frame < 3600 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        const bool a = (buttons & HidNpadButton_A) != 0;
        const bool b = (buttons & HidNpadButton_B) != 0;

        if (phase == 0 && b && !a) {
            marker("STAGE42_GUEST_B_ONLY_FIRST\n");
            phase = 1;
        } else if (phase == 1 && b && a) {
            marker("STAGE42_GUEST_A_AND_B\n");
            phase = 2;
        } else if (phase == 2 && b && !a) {
            marker("STAGE42_GUEST_B_ONLY_AFTER_A\n");
            phase = 3;
        } else if (phase == 3 && !b && !a) {
            marker("STAGE42_GUEST_BOTH_RELEASED\n");
            marker("STAGE42_GUEST_AB_CHORD_PASS\n");
            return 0;
        }

        (void)svcSleepThread(16666667ULL);
    }

    marker("STAGE42_GUEST_AB_CHORD_INCOMPLETE\n");
    return 2;
}
