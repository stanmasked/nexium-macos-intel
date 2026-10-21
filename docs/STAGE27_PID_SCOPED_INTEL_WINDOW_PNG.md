# Stage27 — original Intel NeXium minimal window PNG capture, privacy scoped

## Source of truth and reason

On native Intel macOS, [Stage25 Actions #39514962640](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39514962640), authenticated job 118953692601, created a real NeXium Rustarmic Mach-O SHA-256 38f66e29623995835af8f35409d802e929e084774e40727223de7b3bf9f5e5ad. Standard HorizonApp process SIGABRT; host initialization with minimal app and early minimal app both survived 12s with own visible CoreGraphics windows. That **did not** establish that any actual rendered pixel was captured.

This experiment does **not** rebuild or alter that Mach-O. The dedicated Stage27 workflow downloads the **exact original Stage25 GitHub Actions artifact** by its official run ID and insists on its exact architecture and SHA-256. It runs the already-compiled early minimal eframe mode without NRO, with both audio and HorizonApp disabled, in a temporary isolated data home. The process is identified by its actual PID.

The original pinned same-repository capture helper chooses **only the window owned by that verified PID** and calls macOS screencapture with a window ID, never a desktop or random app window. The generated PNGs are kept only in a temporary directory and deleted after processing. **Only validated image dimensions, sizes and SHA-256 digests go into public CI JSON; no raw PNG or private window text is uploaded.** Seven source-unit tests check sanitized reporting and reject malformed image metadata.

The workflow explicitly accepts a legitimate negative result if macOS screen recording permission is denied: no_window_png_captured. It never treats absence of PNG as success. A successful PNG demonstrates a window-specific captured image, not correctness of rendered egui widgets and emphatically **not NeXium emulation, NRO execution, gameplay, game audio or physical Switch hardware**.

Do not infer full graphical functionality from Stage24/25's window IDs. This experiment is independent of all active Stage23 and Stage26 builds, cannot cancel their jobs, and does not modify the Vandal Hearts game PR #176.
