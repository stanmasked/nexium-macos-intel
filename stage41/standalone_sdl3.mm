// Stage41: native Intel Mac *standalone* SDL3 gamepad subsystem A/B.
//
// This probes a Homebrew-provided system SDL3, not NeXium's statically linked
// pinned SDL3. An isolated success/failure CANNOT establish NeXium's cause.
// No controllers, game files, firmware, window frames or keys are required.
#import <AppKit/AppKit.h>
#include <SDL3/SDL.h>
#include <cstdio>
#include <cstring>

static void phase(const char *name) {
    std::fprintf(stderr, "STAGE41_%s\n", name);
    std::fflush(stderr);
}

int main(int argc, char **argv) {
    if (argc != 2 || (std::strcmp(argv[1], "bare") != 0 &&
                      std::strcmp(argv[1], "appkit") != 0)) {
        return 64;
    }

    phase("PROCESS_ENTERED");
    if (std::strcmp(argv[1], "appkit") == 0) {
        phase("BEFORE_APPKIT");
        @autoreleasepool {
            [NSApplication sharedApplication];
        }
        phase("AFTER_APPKIT");
    }

    phase("BEFORE_HINTS");
    SDL_SetHint("SDL_JOYSTICK_THREAD", "1");
    SDL_SetHint("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
    SDL_SetHintWithPriority("SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS",
                            "1", SDL_HINT_OVERRIDE);
    phase("AFTER_HINTS");

    phase("BEFORE_SDL_INIT");
    if (!SDL_Init(0)) {
        phase("SDL_INIT_FAILED");
        return 3;
    }
    phase("AFTER_SDL_INIT");

    phase("BEFORE_GAMEPAD");
    if (!SDL_InitSubSystem(SDL_INIT_GAMEPAD)) {
        phase("GAMEPAD_FAILED");
        SDL_Quit();
        return 4;
    }
    phase("AFTER_GAMEPAD");

    SDL_Quit();
    phase("AFTER_QUIT");
    return 0;
}
