// macOS-only helper: find the largest visible, layer-zero window owned by
// the exact NeXium process ID. Never capture arbitrary desktop windows.
// Compile with: xcrun swiftc -framework CoreGraphics -o window-id window-id.swift
import Foundation
import CoreGraphics

guard CommandLine.arguments.count == 2,
      let ownerPID = Int32(CommandLine.arguments[1]),
      ownerPID > 0 else {
    fputs("WINDOW_ID_BLOCKED: supply an actual process ID\n", stderr)
    exit(2)
}

guard let entries = CGWindowListCopyWindowInfo(
    [.optionOnScreenOnly, .excludeDesktopElements],
    kCGNullWindowID
) as? [[String: Any]] else {
    fputs("WINDOW_ID_BLOCKED: CoreGraphics window enumeration failed\n", stderr)
    exit(3)
}

var bestWindow: Int? = nil
var bestArea: Double = 0
for entry in entries {
    guard let pid = entry[kCGWindowOwnerPID as String] as? NSNumber,
          pid.int32Value == ownerPID,
          let layer = entry[kCGWindowLayer as String] as? NSNumber,
          layer.intValue == 0,
          let number = entry[kCGWindowNumber as String] as? NSNumber,
          number.intValue > 0,
          let bounds = entry[kCGWindowBounds as String] as? [String: Any],
          let width = bounds["Width"] as? NSNumber,
          let height = bounds["Height"] as? NSNumber else {
        continue
    }
    let area = width.doubleValue * height.doubleValue
    if area > bestArea && width.doubleValue >= 100 && height.doubleValue >= 100 {
        bestArea = area
        bestWindow = number.intValue
    }
}

guard let id = bestWindow else {
    fputs("WINDOW_ID_NOT_FOUND: no suitable visible window owned by PID\n", stderr)
    exit(4)
}
print(id)
