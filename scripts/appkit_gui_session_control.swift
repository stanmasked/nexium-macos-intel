// Independent macOS AppKit window-session control experiment.
// Tests runner GUI availability, NOT NeXium graphics or NRO execution.
// Never captures the desktop, prints window titles or enumerates other PID details.
import AppKit
import CoreGraphics
import Foundation

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let window = NSWindow(
    contentRect: NSRect(x: 64, y: 64, width: 440, height: 240),
    styleMask: [.titled, .closable],
    backing: .buffered,
    defer: false
)
window.title = "NeXium GUI session diagnostic"
window.makeKeyAndOrderFront(nil)
app.activate(ignoringOtherApps: true)

DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
    let pid = ProcessInfo.processInfo.processIdentifier
    let entries = CGWindowListCopyWindowInfo(
        [.optionAll, .excludeDesktopElements],
        kCGNullWindowID
    ) as? [[String: Any]] ?? []
    var owned = 0
    var visible = 0
    for entry in entries {
        guard let windowPid = entry[kCGWindowOwnerPID as String] as? NSNumber,
              windowPid.int32Value == pid else {
            continue
        }
        owned += 1
        if (entry[kCGWindowIsOnscreen as String] as? NSNumber)?.boolValue == true {
            visible += 1
        }
    }
    print("APPKIT_CONTROL_SESSION: own_windows=\(owned) own_visible=\(visible)")
    fflush(stdout)
    exit(visible > 0 ? 0 : 4)
}
app.run()
