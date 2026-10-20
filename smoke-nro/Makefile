# Tiny devkitPro/libnx NRO smoke test. No copyrighted game resources.
DEVKITPRO ?= /opt/devkitpro
DEVKITA64 ?= $(DEVKITPRO)/devkitA64
LIBNX ?= $(DEVKITPRO)/libnx
CC := $(DEVKITA64)/bin/aarch64-none-elf-gcc
ELF2NRO := $(DEVKITPRO)/tools/bin/elf2nro
TARGET := nexium_clean_smoke
ARCH := -march=armv8-a -mtune=cortex-a57 -mtp=soft -fPIE
CPPFLAGS := -I$(LIBNX)/include -D__SWITCH__
CFLAGS := $(ARCH) -std=gnu11 -O2 -g -Wall -Wextra -ffunction-sections -fdata-sections
LDFLAGS := $(ARCH) -specs=$(LIBNX)/switch.specs -Wl,--gc-sections -L$(LIBNX)/lib
LDLIBS := -lnx -lm

.PHONY: all clean
all: $(TARGET).nro

$(TARGET).elf: source/main.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(LDFLAGS) $(LDLIBS) -o $@

$(TARGET).nro: $(TARGET).elf
	$(ELF2NRO) $< $@

clean:
	rm -f $(TARGET).elf $(TARGET).nro
