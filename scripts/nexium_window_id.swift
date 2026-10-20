// macOS-only helper: find the largest visible, layer-zero window owned by
// the exact NeXium process ID. Never capture arbitrary desktop windows.
// Also reports *counts only* of the target process's windows when no matching
// window is visible, so headless CI can be distinguished from a missing GUI.
// Compile with: xcrun swiftc -framework CoreGraphics -o window-id window-id.swift
import Foundation
import CoreGraphics

guard CommandLine.arguments.count == 2,
      let ownerPID = Int32(CommandLine.arguments[1]),
      ownerPID > 0 else {
    fputs("WINDOW_ID_BLOCKED: supply an actual process ID\n", stderr)
    exit(2)
}

// Enumerate all windows but immediately filter by the supplied process ID.
// Never print, capture or otherwise report windows belonging to other apps.
guard let entries = CGWindowListCopyWindowInfo(
    [.optionAll, .excludeDesktopElements],
    kCGNullWindowID
) as? [[String: Any]] else {
    fputs("WINDOW_ID_BLOCKED: CoreGraphics window enumeration failed\n", stderr)
    exit(3)
}

var pidOwned = 0
var onScreen = 0
var regularLayer = 0
var largeEnough = 0
var bestWindow: Int? = nil
var bestArea: Double = 0

for entry in entries {
    guard let pid = entry[kCGWindowOwnerPID as String] as? NSNumber,
          pid.int32Value == ownerPID else {
        continue
    }
    pidOwned += 1
    guard let visible = entry[kCGWindowIsOnscreen as String] as? NSNumber,
          visible.boolValue else {
        continue
    }
    onScreen += 1
    guard let layer = entry[kCGWindowLayer as String] as? NSNumber,
          layer.intValue == 0 else {
        continue
    }
    regularLayer += 1
    guard let number = entry[kCGWindowNumber as String] as? NSNumber,
          number.intValue > 0,
          let bounds = entry[kCGWindowBounds as String] as? [String: Any],
          let width = bounds["Width"] as? NSNumber,
          let height = bounds["Height"] as? NSNumber,
          width.doubleValue >= 100, height.doubleValue >= 100 else {
        continue
    }
    largeEnough += 1
    let area = width.doubleValue * height.doubleValue
    if area > bestArea {
        bestArea = area
        bestWindow = number.intValue
    }
}

guard let id = bestWindow else {
    fputs("WINDOW_ID_NOT_FOUND: target_pid_windows=\(pidOwned) onscreen=\(onScreen) regular_layer=\(regularLayer) large_enough=\(largeEnough)\n", stderr)
    exit(4)
}
print(id)
