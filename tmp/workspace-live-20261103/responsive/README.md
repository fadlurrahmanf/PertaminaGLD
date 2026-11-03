# Actual Workspace responsive audit

Read-only browser audit of actual app source on isolated PC fixture. No Scan, Connect, recording commands, session writes, native dialog, COM, firmware or hardware access.

Eight cases passed: widths1600/1024/736/320, each light and dark. All had viewport scrollWidth equal viewport width, no Dataset child escaping viewport, five steps, eight readings, no JS errors, and all visible configuration/Reset/Export controls with nonzero boxes. Table horizontal scroll stays within its own wrapper. Primary/Stop remain intentionally hidden until Lock.

Screenshots and detailed measured boxes are in report.json. Visual review of1600/light and320/dark confirmed the Dataset workspace layout. At320px the existing global app toolbar clips items; this is outside Dataset scope and was not changed. The backend disconnected state has literal English copy; optional localized wording polish remains.
