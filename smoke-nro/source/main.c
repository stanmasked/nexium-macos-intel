/* Public-domain-style original minimal libnx smoke payload for NeXium.
 * No Nintendo game assets, private keys, firmware, or ROM data.
 * This is a technical test, not a playable game.
 */
#include <switch.h>
#include <stdio.h>
#include <stdint.h>

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    consoleInit(NULL);
    uint32_t frame = 0;
    while (appletMainLoop()) {
        printf("\x1b[1;1HNeXium Intel / clean NRO smoke test   ");
        printf("\x1b[3;1HFrame counter: %08lu   ", (unsigned long)frame);
        printf("\x1b[5;1HNo private game data or Nintendo firmware bundled.");
        printf("\x1b[7;1HAnimated counter should advance when graphics work.");
        consoleUpdate(NULL);
        ++frame;
        svcSleepThread(16666666LL);
    }
    consoleExit(NULL);
    return 0;
}
