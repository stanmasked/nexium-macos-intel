# Stage69 — bind every private window capture to the exact smoke PID

Stage66 successfully observed 24 frames with 15 unique hashes from a NeXium-owned macOS window while the original public libnx input guest ran. Stage68 now attempts the original public libnx framebuffer guest in the same reviewed virtual Intel build. The host screenshot is a separate observation; it must not be conflated with guest GPU proof.

A review of the evidence contract identified a narrow provenance gap: `capture_macos_window.py` writes the PID it was asked to capture, but the Stage66 classifier previously checked only the generic `macos_pid_owned_window_only` capture type. The smoke report had the exact launch's Mach-O/NRO hashes, but did not retain the PID of that launch. The capture helper validates the process name, yet the classifier did not independently compare the report's PID to the exact process started by `nro_smoke_test.py`.

Stage69 closes that gap:

1. The private smoke JSON now records `emulator_pid` immediately after `Popen` successfully launches NeXium.
2. The capture auditor requires `window_capture_result.json.pid` to be an actual positive integer equal to the exact smoke `emulator_pid`. Missing, Boolean, zero, mismatched, or malformed PID values fail closed.
3. No-frame/no-capture results remain explicitly unverified and do not require a PID comparison because there is no capture evidence to attribute.
4. Three additional tests reject a different capture PID, missing capture PID, and Boolean-as-integer PID. Existing fixtures continue to validate binary/NRO hashes, private frame bytes and ownership policy.
5. The dedicated Ubuntu test workflow runs Stage66's capture-evidence fixtures, Stage68's original guest-marker fixtures, and Stage65's guest audit fixtures. It uploads no runtime screenshots, raw logs or binaries.

This makes the evidence chain more precise: **exact native Mach-O + exact guest NRO + smoke-launched PID + capture helper's same PID + frame hashes**. It still proves only which host window was observed. It does not by itself prove the pixels originate from the Switch guest renderer or are visually correct.

The Stage69 branch is stacked on Stage68, whose native Intel runtime experiment is still pending at the time of writing. No branch is merged to `main`; no commercial game/firmware/key material is used or uploaded.
