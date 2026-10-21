#include <switch.h>
#include <stdbool.h>
#include <string.h>

/*
 * Stage40 diagnostic only. The probe uses libnx's real PadState API and
 * SVC OutputDebugString so the host emulator can capture structured markers.
 * It does not read host state or fake the guest-visible HID report.
 */
static void emit_marker(const char *marker) {
    (void)svcOutputDebugString(marker, strlen(marker));
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    emit_marker("STAGE40_GUEST_HID_PROBE_START\n");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    Result result = padInitializeDefault(&pad);
    if (R_FAILED(result)) {
        emit_marker("STAGE40_GUEST_HID_PAD_INIT_FAILED\n");
        return 3;
    }

    bool previous_b = false;
    bool saw_b_down = false;
    bool saw_b_up = false;

    /* 40 seconds maximum at 60 Hz; stop as soon as both edges are observed. */
    for (u32 frame = 0; frame < 2400 && appletMainLoop(); ++frame) {
        padUpdate(&pad);
        const bool b_down = (padGetButtons(&pad) & HidNpadButton_B) != 0;

        if (b_down && !previous_b) {
            emit_marker("STAGE40_GUEST_HID_B_DOWN\n");
            saw_b_down = true;
        } else if (!b_down && previous_b) {
            emit_marker("STAGE40_GUEST_HID_B_UP\n");
            saw_b_up = true;
        }

        previous_b = b_down;
        if (saw_b_down && saw_b_up) {
            emit_marker("STAGE40_GUEST_HID_PRESS_RELEASE_PASS\n");
            return 0;
        }

        (void)svcSleepThread(16666667ULL);
    }

    emit_marker("STAGE40_GUEST_HID_PROBE_END_WITHOUT_ROUNDTRIP\n");
    return 2;
}
