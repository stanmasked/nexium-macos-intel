// Stage44: reproducible synthetic SDL3 input without physical hardware.
// This is a HOME-BREW SDL3 harness, NOT NeXium's statically linked library.
// Static marker names only, never leak player input/IDs/device paths.
#import <AppKit/AppKit.h>
#include <SDL3/SDL.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void mark(const char* label) {
    std::fprintf(stderr, "STAGE44_%s\n", label);
    std::fflush(stderr);
}

int main(int argc, char** argv) {
    if (argc != 2 || (std::strcmp(argv[1], "bare") != 0 &&
                      std::strcmp(argv[1], "appkit") != 0)) {
        return 64;
    }

    mark("PROCESS_ENTERED");
    if (std::strcmp(argv[1], "appkit") == 0) {
        mark("BEFORE_APPKIT");
        @autoreleasepool {
            [NSApplication sharedApplication];
        }
        mark("AFTER_APPKIT");
    }

    SDL_SetHint("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
    mark("BEFORE_SDL_INIT");
    if (!SDL_Init(SDL_INIT_GAMEPAD)) {
        mark("SDL_INIT_FAILED");
        return 3;
    }
    mark("SDL_READY");

    SDL_VirtualJoystickDesc desc;
    SDL_INIT_INTERFACE(&desc);
    desc.type = SDL_JOYSTICK_TYPE_GAMEPAD;
    desc.naxes = SDL_GAMEPAD_AXIS_COUNT;
    desc.nbuttons = SDL_GAMEPAD_BUTTON_COUNT;
    desc.button_mask = (1u << SDL_GAMEPAD_BUTTON_SOUTH);
    desc.axis_mask = (1u << SDL_GAMEPAD_AXIS_LEFTX);
    desc.name = "Stage44 Synthetic Controller";

    mark("BEFORE_ATTACH");
    const SDL_JoystickID id = SDL_AttachVirtualJoystick(&desc);
    if (id == 0 || !SDL_IsGamepad(id)) {
        mark("ATTACH_FAILED");
        SDL_Quit();
        return 4;
    }
    mark("ATTACHED");

    SDL_Joystick* joystick = SDL_OpenJoystick(id);
    SDL_Gamepad* gamepad = SDL_OpenGamepad(id);
    if (joystick == nullptr || gamepad == nullptr) {
        mark("OPEN_FAILED");
        if (gamepad) SDL_CloseGamepad(gamepad);
        if (joystick) SDL_CloseJoystick(joystick);
        SDL_DetachVirtualJoystick(id);
        SDL_Quit();
        return 5;
    }
    mark("GAMEPAD_OPENED");

    mark("BEFORE_INJECTION");
    bool set_ok =
        SDL_SetJoystickVirtualButton(joystick, SDL_GAMEPAD_BUTTON_SOUTH, true) &&
        SDL_SetJoystickVirtualAxis(joystick, SDL_GAMEPAD_AXIS_LEFTX, 16000);
    SDL_UpdateJoysticks();
    SDL_UpdateGamepads();
    if (!set_ok || !SDL_GetGamepadButton(gamepad, SDL_GAMEPAD_BUTTON_SOUTH) ||
        std::abs((int)SDL_GetGamepadAxis(gamepad, SDL_GAMEPAD_AXIS_LEFTX) - 16000) > 500) {
        mark("INJECTION_FAILED");
        SDL_CloseGamepad(gamepad);
        SDL_CloseJoystick(joystick);
        SDL_DetachVirtualJoystick(id);
        SDL_Quit();
        return 6;
    }
    mark("BUTTON_AXIS_OBSERVED");

    set_ok =
        SDL_SetJoystickVirtualButton(joystick, SDL_GAMEPAD_BUTTON_SOUTH, false) &&
        SDL_SetJoystickVirtualAxis(joystick, SDL_GAMEPAD_AXIS_LEFTX, 0);
    SDL_UpdateJoysticks();
    SDL_UpdateGamepads();
    if (!set_ok || SDL_GetGamepadButton(gamepad, SDL_GAMEPAD_BUTTON_SOUTH) ||
        std::abs((int)SDL_GetGamepadAxis(gamepad, SDL_GAMEPAD_AXIS_LEFTX)) > 500) {
        mark("RELEASE_FAILED");
        SDL_CloseGamepad(gamepad);
        SDL_CloseJoystick(joystick);
        SDL_DetachVirtualJoystick(id);
        SDL_Quit();
        return 7;
    }
    mark("RELEASE_OBSERVED");

    SDL_CloseGamepad(gamepad);
    SDL_CloseJoystick(joystick);
    if (!SDL_DetachVirtualJoystick(id)) {
        mark("DETACH_FAILED");
        SDL_Quit();
        return 8;
    }
    mark("DETACHED");
    SDL_Quit();
    mark("CLEAN_EXIT");
    return 0;
}
