#include <switch.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

/*
 * Stage67: an ORIGINAL, public libnx framebuffer API graphics probe.
 * No Nintendo game, keys, firmware, memory patching or host frame injection.
 *
 * The probe draws two alternating small RGBA checkerboards using the guest
 * libnx NWindow/Framebuffer stack, not host-synthesized pixels. A successful
 * NRO compilation proves only API buildability, NOT that NeXium implements
 * VI, Nvidia services, buffers, presentation, or visible guest graphics.
 *
 * Guest runtime markers are source-independent OutputDebugString records.
 */
#define FB_WIDTH 320u
#define FB_HEIGHT 180u
#define FB_FRAMES 4u

static void mark(const char *s) {
    (void)svcOutputDebugString(s, strlen(s));
}

static void draw_checkerboard(void *pixels, u32 stride, u32 frame) {
    for (u32 y = 0; y < FB_HEIGHT; ++y) {
        u32 *row = (u32 *)((u8 *)pixels + (size_t)y * stride);
        for (u32 x = 0; x < FB_WIDTH; ++x) {
            const bool bright = (((x / 32u) + (y / 30u) + frame) & 1u) != 0u;
            row[x] = bright ? RGBA8_MAXALPHA(240, 64, 32)
                            : RGBA8_MAXALPHA(28, 48, 220);
        }
    }
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    mark("STAGE67_GUEST_GRAPHICS_START\n");

    NWindow *win = nwindowGetDefault();
    if (!win) {
        mark("STAGE67_GUEST_WINDOW_UNAVAILABLE\n");
        return 2;
    }
    mark("STAGE67_GUEST_DEFAULT_WINDOW_OBTAINED\n");

    Framebuffer fb = {0};
    const Result create = framebufferCreate(
        &fb, win, FB_WIDTH, FB_HEIGHT, PIXEL_FORMAT_RGBA_8888, 2
    );
    if (R_FAILED(create)) {
        mark("STAGE67_GUEST_FRAMEBUFFER_CREATE_FAILED\n");
        return 3;
    }
    mark("STAGE67_GUEST_FRAMEBUFFER_CREATED\n");

    const Result linear = framebufferMakeLinear(&fb);
    if (R_FAILED(linear)) {
        mark("STAGE67_GUEST_FRAMEBUFFER_LINEAR_FAILED\n");
        framebufferClose(&fb);
        return 4;
    }
    mark("STAGE67_GUEST_LINEAR_BUFFER_READY\n");

    for (u32 frame = 0; frame < FB_FRAMES; ++frame) {
        if (!appletMainLoop()) {
            mark("STAGE67_GUEST_APPLET_EXIT_BEFORE_FRAMES\n");
            framebufferClose(&fb);
            return 5;
        }
        u32 stride = 0;
        void *pixels = framebufferBegin(&fb, &stride);
        if (!pixels || stride < FB_WIDTH * sizeof(u32)
                || stride > 32768u) {
            mark("STAGE67_GUEST_FRAMEBUFFER_BEGIN_FAILED\n");
            framebufferClose(&fb);
            return 6;
        }
        draw_checkerboard(pixels, stride, frame);
        if (frame == 0u) {
            mark("STAGE67_GUEST_CHECKERBOARD_A_WRITTEN\n");
        } else if (frame == 1u) {
            mark("STAGE67_GUEST_CHECKERBOARD_B_WRITTEN\n");
        }
        framebufferEnd(&fb);
        if (frame == 0u) {
            mark("STAGE67_GUEST_FRAME_A_PRESENTED_CALL_RETURNED\n");
        } else if (frame == 1u) {
            mark("STAGE67_GUEST_FRAME_B_PRESENTED_CALL_RETURNED\n");
        }
        (void)svcSleepThread(16666667ULL);
    }
    framebufferClose(&fb);
    mark("STAGE67_GUEST_FOUR_FRAMEBUFFER_CALLS_COMPLETE\n");
    return 0;
}
