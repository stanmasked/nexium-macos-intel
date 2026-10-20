#!/usr/bin/env python3
"""Stage25: isolated Intel Mac eframe creator ablation after normal host init.

This experiment extends Stage22 ONLY in a local pinned NeXium checkout.
NEXIUM_MACOS_FULL_INIT_MINIMAL_APP=1 retains the normal app settings,
logging, host audio policy, eframe options and run_native entry point,
but replaces HorizonApp::new with Stage22MinimalEframe at app creation.
Without this environment variable NeXium source behavior is unchanged.

Never describe process survival as window rendering or game execution.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ORIGINAL = '''        Box::new(move |cc| {
            Ok(Box::new(HorizonApp::new(
                cc,
                log_feed_for_app.take(),
                settings.clone(),
                nro_arg.clone(),
            )))
        }),'''
UPDATED = '''        Box::new(move |cc| {
            // Stage25: full normal host initialization and options have run;
            // keep one run_native but bypass HorizonApp constructor only.
            #[cfg(target_os = "macos")]
            if std::env::var("NEXIUM_MACOS_FULL_INIT_MINIMAL_APP")
                .ok().as_deref() == Some("1")
            {
                eprintln!("STAGE25_HOST_INIT_MINIMAL_APP_ENTERED");
                return Ok(Box::new(Stage22MinimalEframe) as Box<dyn eframe::App>);
            }
            Ok(Box::new(HorizonApp::new(
                cc,
                log_feed_for_app.take(),
                settings.clone(),
                nro_arg.clone(),
            )) as Box<dyn eframe::App>)
        }),'''
MARKER = "STAGE25_HOST_INIT_MINIMAL_APP_ENTERED"

def patch_source(content: str) -> str:
    if MARKER in content:
        if content.count(MARKER) != 1 or UPDATED not in content or ORIGINAL in content:
            raise RuntimeError("Stage25 partial or inconsistent source modification")
        return content
    if "STAGE22_MINIMAL_EFRAME_ENTERED" not in content:
        raise RuntimeError("Stage22 minimal eframe must be present")
    if content.count(ORIGINAL) != 1:
        raise RuntimeError("expected exactly one pinned HorizonApp closure")
    return content.replace(ORIGINAL, UPDATED, 1)

def apply(root: Path) -> bool:
    source = root / "nexium-gui/src/main.rs"
    original = source.read_text(encoding="utf-8")
    updated = patch_source(original)
    if updated == original:
        return False
    source.write_text(updated, encoding="utf-8")
    return True

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    a = parser.parse_args(argv)
    try:
        changed=apply(a.source)
        print("STAGE25_HOST_INIT_APP_PATCH_APPLIED" if changed else
              "STAGE25_HOST_INIT_APP_PATCH_ALREADY_APPLIED")
    except (OSError, UnicodeError, RuntimeError) as exc:
        print("STAGE25_HOST_INIT_APP_PATCH_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    sys.exit(main())
