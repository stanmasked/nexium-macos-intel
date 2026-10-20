#!/usr/bin/env python3
"""Stage a patched *local copy* of dynarmic-sys-mythrax 0.3.6 for Intel macOS.

The published crate's vendor/CMakeLists.txt compiles its macOS exception
handler without generating the Mach Interface Generator header and server.
Never modify the shared cargo registry or ship generated SDK source.
"""
import argparse
from pathlib import Path
import shutil
import sys

CRATE = "dynarmic-sys-mythrax-0.3.6"
OLD = '''elseif (APPLE)
    target_sources(dynarmic PRIVATE "${DYNARMIC_SOURCE_DIR}/backend/exception_handler_macos.cpp")'''
NEW = '''elseif (APPLE)
    # NeXium Intel/macOS: CMake must generate the Mach exception RPC code.
    # This fix is applied to a project-local copy of dynarmic-sys-mythrax.
    if (NOT CMAKE_OSX_ARCHITECTURES STREQUAL "x86_64")
        message(FATAL_ERROR "This experimental Dynarmic patch supports Intel macOS only")
    endif()
    # Apple's mig may reside inside Xcode toolchains rather than PATH.
    execute_process(
        COMMAND xcrun --find mig
        RESULT_VARIABLE NE_X_MIG_FIND_RESULT
        OUTPUT_VARIABLE NE_X_MIG_TOOL
        ERROR_VARIABLE NE_X_MIG_FIND_ERROR
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if (NOT NE_X_MIG_FIND_RESULT EQUAL 0 OR NOT EXISTS "${NE_X_MIG_TOOL}")
        message(FATAL_ERROR "Could not locate Apple's mig with xcrun: ${NE_X_MIG_FIND_ERROR}")
    endif()
    if (NOT DEFINED ENV{SDKROOT} OR NOT EXISTS "$ENV{SDKROOT}/usr/include/mach/mach_exc.defs")
        message(FATAL_ERROR "Set SDKROOT to the macOS SDK with mach/mach_exc.defs")
    endif()
    set(NE_X_MIG_DIR "${DYNARMIC_SOURCE_DIR}/backend/x64/mig")
    file(MAKE_DIRECTORY "${NE_X_MIG_DIR}")
    execute_process(
        COMMAND "${NE_X_MIG_TOOL}" -arch x86_64 -isysroot "$ENV{SDKROOT}"
                -user "${NE_X_MIG_DIR}/mach_exc_user.c"
                -header "${NE_X_MIG_DIR}/mach_exc_user.h"
                -server "${NE_X_MIG_DIR}/mach_exc_server.c"
                -sheader "${NE_X_MIG_DIR}/mach_exc_server.h"
                "$ENV{SDKROOT}/usr/include/mach/mach_exc.defs"
        RESULT_VARIABLE NE_X_MIG_RESULT
        ERROR_VARIABLE NE_X_MIG_ERROR
    )
    if (NOT NE_X_MIG_RESULT EQUAL 0 OR
        NOT EXISTS "${NE_X_MIG_DIR}/mach_exc_server.h" OR
        NOT EXISTS "${NE_X_MIG_DIR}/mach_exc_server.c")
        message(FATAL_ERROR "Mach MIG generation failed: ${NE_X_MIG_ERROR}")
    endif()
    target_sources(dynarmic PRIVATE
        "${DYNARMIC_SOURCE_DIR}/backend/exception_handler_macos.cpp"
        "${NE_X_MIG_DIR}/mach_exc_server.c"
    )'''


def stage(upstream: Path, cargo_home: Path, work_dir: Path) -> Path:
    upstream = upstream.resolve()
    work_dir = work_dir.resolve()
    registry = cargo_home.expanduser().resolve() / "registry" / "src"
    matches = list(registry.glob(f"*/{CRATE}"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one cached {CRATE} under {registry}, found {len(matches)}")
    source = matches[0]
    if not (source / "vendor/CMakeLists.txt").is_file():
        raise RuntimeError("cached Dynarmic crate is missing vendor/CMakeLists.txt")
    target = work_dir / "dynarmic-sys-mythrax-macos"
    if target.exists():
        raise RuntimeError(f"refusing to overwrite staged dependency: {target}")
    shutil.copytree(source, target)
    cmake = target / "vendor/CMakeLists.txt"
    raw = cmake.read_text(encoding="utf-8")
    if raw.count(OLD) != 1:
        shutil.rmtree(target)
        raise RuntimeError("Dynarmic CMake anchor changed; refusing speculative patch")
    cmake.write_text(raw.replace(OLD, NEW, 1), encoding="utf-8")
    manifest = upstream / "Cargo.toml"
    previous = manifest.read_text(encoding="utf-8")
    if "[patch.crates-io]" in previous or 'dynarmic-sys-mythrax = { path' in previous:
        shutil.rmtree(target)
        raise RuntimeError("Cargo manifest already contains patches; inspect it manually")
    # The source tree and staging directory are siblings in the NeXium work root.
    # This path is intentionally relative so CI and local macOS builds match.
    append = '\n[patch.crates-io]\ndynarmic-sys-mythrax = { path = "../dynarmic-sys-mythrax-macos" }\n'
    manifest.write_text(previous.rstrip() + '\n' + append, encoding="utf-8")
    print(f"Staged local Dynarmic/MIG fix: {target}")
    return target


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("upstream", type=Path)
    p.add_argument("--cargo-home", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    args = p.parse_args()
    try:
        stage(args.upstream, args.cargo_home, args.work)
    except (OSError, RuntimeError) as e:
        print(f"DYNARMIC_MIG_BLOCKED: {e}", file=sys.stderr)
        sys.exit(1)
