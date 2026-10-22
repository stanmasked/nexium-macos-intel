# Stage66 — private Intel GUI-window observation after source-bound libnx guest

Stage65 [PR #67](https://github.com/stanmasked/nexium-macos-intel/pull/67) is **accepted for diagnostic guest execution** on [CI #6](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39802884184). On one 34-PR virtually integrated Intel Mach-O it verified 481/481 Python tests, original libnx below/above-deadzone guest readback, five serialized NPad samples, independent Stage54/55 triplet replay and exact binary/NRO SHA-256.

That is **not** evidence that the guest GPU renders an image or that a macOS window is visible. Stage66 adds a separate source-bound, privacy-limited observation.

## Experiment and boundaries

1. Reproduce the reviewed two-conflict virtual merge for **35 linked Draft PRs** (the new Stage66 PR #68 through PR #1), extract source into disposable directory and run the full Python suite.
2. Compile original public Stage53 libnx diagnostic NRO, then compile the exact combined source on physical x86_64 macOS using Rustarmic and the branch-neutral diagnostic profile.
3. Execute the original guest NRO with the same Stage65 HID/NPad success gates, but opt into `nro_smoke_test.py --capture-window`. The pre-existing capture tool only accepts a living process named `nexium`, discovers that exact PID's regular on-screen window and uses macOS `screencapture -l` for the specific window ID.
4. Independently classify GUI-session availability with an AppKit control window so a headless CI environment is not mistaken for an emulator graphics failure. Do not turn an unverified GUI session into an artificial success.
5. Read the local smoke and capture reports with strict size/type/duplicate-key checking, then verify **same Intel Mach-O SHA-256 and public NRO SHA-256**, process-owned capture type, exact frame list, individual PNG dimensions/file sizes and independent SHA-256. Reject any path traversal, symlink, forged hashes or conflicting counts.
6. Report **only counts and taxonomy**, never PNGs, paths, raw guest logs, window title, desktop screenshots or screenshots from other processes. All private files and the virtual Mach-O are deleted with the temporary runner directory.

## Outcomes to distinguish

- `no_capture_report` / `no_owned_window_frames`: window capture unavailable or denied; **GUI unverified**, even if the same original libnx guest NPad proof passes.
- `owned_window_static_frame`: one or more verified frames but only one unique hash. Own visible NeXium window is evidenced, **frame progress is not**.
- `owned_window_frames_changed`: two or more independently hashed, distinct frames from NeXium's own window. **Only pixel differences**, not proof that Switch guest graphics are accurate or gameplay is correct.

In all cases `guest_gpu_frames_verified=false`, `commercial_gameplay_verified=false`, `physical_controller_verified=false`, `raw_frames_uploaded=false` and `main_merge_approved=false`. Sixteen negative-control/positive-control tests protect the classifier.

## Review and next work

We can accept Stage66 as **honest window telemetry with source-bound guest proof** only after its dedicated Intel CI passes. A successful job with no frames is *not* a GUI success. Genuine guest GPU frame verification will require a separate controlled guest rendering workload, renderer attribution, and measurable nontrivial output in a GUI-capable Mac session. No PR merged to `main`.