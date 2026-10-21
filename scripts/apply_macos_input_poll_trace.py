#!/usr/bin/env python3
"""Stage34: no-side-effect one-time InputBackend::poll execution markers.

Applies ONLY to pinned NeXium input.rs when the official Intel experiment
opt-in NEXIUM_EXPERIMENT_INPUT_POLL_MARKERS=1 is set. The runtime guard
NEXIUM_MACOS_INPUT_POLL_TRACE=1 emits only phase IDs, never button values,
device identifiers, file paths, or private event data.
"""
from pathlib import Path
import argparse
import sys

START = (
    "    pub fn poll(&mut self, cfg: &ControllerConfig, left_dz: f32, right_dz: f32) -> InputSnapshot {\n"
)
END = "        let mut snap = InputSnapshot::new();"
ENTRY_ANCHOR = START
PUMP_ANCHOR = "        self.gamepad.update();"
PAD_ANCHOR = "        self.ensure_pad();"
PREFIX = "STAGE34_INPUT_POLL_"


def marker(name: str) -> str:
    return (
        '        #[cfg(target_os = "macos")]\n'
        '        if std::env::var("NEXIUM_MACOS_INPUT_POLL_TRACE")'
        '.ok().as_deref() == Some("1") {\n'
        '            static OBSERVED: std::sync::atomic::AtomicBool = '
        'std::sync::atomic::AtomicBool::new(false);\n'
        '            if !OBSERVED.swap(true, std::sync::atomic::Ordering::Relaxed) {\n'
        f'                eprintln!("{PREFIX}{name}");\n'
        '            }\n'
        '        }\n'
    )


def patch_source(source: str) -> str:
    marks = [marker(k) for k in ("ENTRY", "AFTER_EVENT_PUMP", "AFTER_GAMEPAD_UPDATE")]
    if PREFIX in source:
        if all(source.count(x) == 1 for x in marks) and source.count(PREFIX) == 3:
            return source
        raise RuntimeError("incomplete or extra Stage34 one-time markers")
    if source.count(START) != 1 or source.count(END) < 1:
        raise RuntimeError("pinned InputBackend poll method missing/ambiguous")
    pre, rest = source.split(START, 1)
    body, post = rest.split(END, 1)
    body = START + body
    if body.count(PUMP_ANCHOR) != 1 or body.count(PAD_ANCHOR) != 1:
        raise RuntimeError("pinned original SDL3 event pump/update anchor mismatch")
    if body.index(PUMP_ANCHOR) >= body.index(PAD_ANCHOR):
        raise RuntimeError("original SDL3 input poll ordering changed")
    body = body.replace(ENTRY_ANCHOR, ENTRY_ANCHOR + marks[0], 1)
    body = body.replace(PUMP_ANCHOR, marks[1] + PUMP_ANCHOR, 1)
    body = body.replace(PAD_ANCHOR, marks[2] + PAD_ANCHOR, 1)
    return pre + body + END + post


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    args=parser.parse_args(argv)
    path=args.source/"nexium-gui/src/input.rs"
    try:
        original=path.read_text(encoding="utf-8")
        revised=patch_source(original)
        if revised!=original:
            path.write_text(revised,encoding="utf-8")
        print("STAGE34_POLL_MARKERS_APPLIED" if revised!=original
              else "STAGE34_POLL_MARKERS_ALREADY_APPLIED")
        return 0
    except (OSError,UnicodeError,RuntimeError) as exc:
        print("STAGE34_POLL_MARKERS_BLOCKED: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
