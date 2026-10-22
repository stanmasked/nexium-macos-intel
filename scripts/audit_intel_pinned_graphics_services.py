#!/usr/bin/env python3
"""Stage72: immutable upstream VI/BufferQueue source risk audit, NOT runtime proof.

Reads a separate, pinned checkout of the PUBLIC upstream NeXium source. File
Git blob IDs are checked before evaluating code anchors. No source is patched,
no Git refs are pushed, and no proprietary GPU/device firmware is required.

The result exposes code-path risks only, not a verified cause of Stage68's
guest-framebuffer runtime failure; service registration is not dispatch proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PINNED_COMMIT = "089562567a0a8760dfdd8420e1f57c35159a9219"
PINNED_BLOBS = {
    "nexium-kernel/src/services/vi.rs":
        "22c94ef20c70f748f5afbc341dcf40ec68fc8240",
    "nexium-kernel/src/services/nvnflinger.rs":
        "26c2472797508bd7fba6172aed1575c1db8c760d",
    "nexium-kernel/src/services/application_display_service/handlers.rs":
        "429f5652428bd59395a1514fae2a387607815ece",
    "nexium-kernel/src/services/vi_root_service/handlers.rs":
        "40e2a8997fb8ffdb7be0a2f20d7b1e9e28f8895a",
    "nexium-kernel/src/services/sm.rs":
        "b051c1bdf645bc4401d78652daf7e14aabb4b229",
}

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii")
                        + b"\x00" + data).hexdigest()


def read_exact_public_sources(root: Path, *, expected=None) -> dict[str, str]:
    if expected is None:
        expected = PINNED_BLOBS
    if not root.is_dir() or root.is_symlink():
        raise ValueError("pinned source checkout is missing or linked")
    results = {}
    for name, expected_sha in expected.items():
        if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
            raise ValueError("malformed pinned public source blob ID")
        f = root / name
        if (f.is_symlink() or not f.is_file()
                or f.stat().st_size > 256 * 1024):
            raise ValueError("pinned public source file missing/oversized/linked")
        raw = f.read_bytes()
        if git_blob_sha(raw) != expected_sha:
            raise ValueError("public graphics source Git blob differs from pinned commit")
        results[name] = raw.decode("utf-8").replace("\r\n", "\n")
    return results


def inspect_pinned_graphics_sources(sources: dict[str, str]) -> dict:
    try:
        vi = sources["nexium-kernel/src/services/vi.rs"]
        bq = sources["nexium-kernel/src/services/nvnflinger.rs"]
        display = sources["nexium-kernel/src/services/application_display_service/handlers.rs"]
        root = sources["nexium-kernel/src/services/vi_root_service/handlers.rs"]
        sm = sources["nexium-kernel/src/services/sm.rs"]
    except KeyError as e:
        raise ValueError("missing pinned graphics source file") from e
    # Anchors are intentionally narrowly pinned to the source at PINNED_COMMIT.
    observations = {
        "graphics_service_names_registered_in_source":
            all(x in sm for x in ('"vi:m"', '"vi:s"', '"vi:u"', '"nvdrv"')),
        "vi_root_get_display_service_u_is_empty_stub":
            bool(re.search(r"pub fn get_display_service_u_from_root\([^)]*\)\s*\{\s*\}", root)),
        "application_display_open_layer_returns_only_parcel_size":
            bool(re.search(r"pub fn open_layer\([^)]*\)\s*->\s*u64\s*\{\s*NATIVE_WINDOW_PARCEL_SIZE\s*\}", display)),
        "vi_unhandled_command_returns_success":
            "VI.cmd_{} UNHANDLED" in vi and
            bool(re.search(r"_\s*=>\s*\{[^}]*log::warn!\([\s\S]*?\);\s*SUCCESS\s*\}", vi)),
        "vi_framebuffer_queue_is_separate_mutex_vector":
            "framebuffer_queue: Arc<Mutex<Vec<Vec<u8>>>>" in vi,
        "binder_unsupported_commands_return_success":
            'nvnflinger stub command:' in bq and
            bool(re.search(r"_\s*=>\s*\{\s*log::info!\([\s\S]*?\);\s*SUCCESS\s*\}", bq)),
        "binder_dequeue_and_request_appear_noop_success":
            "REQUEST_BUFFER | DEQUEUE_BUFFER => {" in bq
            and 'log::trace!("IGBP buffer op {}"' in bq
            and "SUCCESS" in bq,
        "binder_fallback_frame_is_constant_fill":
            "pixels: vec![0x10u8; pixel_count * 4]" in bq,
    }
    if not all(observations.values()):
        raise ValueError("pinned VI source contracts changed unexpectedly")
    return {
        "schema": "nexium-intel-pinned-public-graphics-source-risk/v1",
        "upstream_pin": PINNED_COMMIT,
        "source_blob_digests_verified": True,
        "source_files_reviewed": len(sources),
        **observations,
        "runtime_graphics_failure_cause_confirmed": False,
        "guest_gpu_frames_verified": False,
        "commercial_gameplay_verified": False,
        "production_release_verified": False,
        "raw_logs_uploaded": False,
        "main_merge_approved": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pinned-upstream-checkout", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rev = subprocess.run(
            ["git", "-C", str(args.pinned_upstream_checkout), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if rev.returncode != 0 or rev.stdout.strip() != PINNED_COMMIT:
            raise ValueError("upstream checkout not at exact pinned revision")
        result = inspect_pinned_graphics_sources(
            read_exact_public_sources(args.pinned_upstream_checkout)
        )
        print(json.dumps(result, sort_keys=True))
        print("STAGE72_PINNED_VI_SOURCE_RISKS_IDENTIFIED_NOT_RUNTIME_CAUSE")
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        print("STAGE72_PINNED_GRAPHICS_SOURCE_AUDIT_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
