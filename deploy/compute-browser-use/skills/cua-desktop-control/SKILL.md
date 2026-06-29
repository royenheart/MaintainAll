---
name: cua-desktop-control
description: Remote Windows desktop control via CUA Control Plane. Use this skill when the user asks you to perform actions on their remote Windows PC.
version: 1.0.0
---

# CUA Desktop Control

You have remote control of a Windows desktop through the CUA Control Plane.

## Available Commands

All commands are invoked via `cuactl`:

### Screen
- `cuactl capture` — Take a screenshot (saves to temp dir, returns path + base64)
- `cuactl screen-size` — Get screen dimensions

### Mouse
- `cuactl click X Y [left|right|middle]` — Click at coordinates
- `cuactl move X Y` — Move cursor to coordinates
- `cuactl scroll [dx] [dy]` — Scroll mouse wheel
- `cuactl drag fromX fromY toX toY` — Drag from one point to another

### Keyboard
- `cuactl type "text to type"` — Type text (supports Unicode)
- `cuactl press_key KEY` — Press a key (e.g., "enter", "escape", "tab", "F5")

### Deterministic Operations (no screenshot needed)
- `cuactl list-apps` — List running applications with windows
- `cuactl list-installed-apps` — List all installed applications
- `cuactl app-info "AppName"` — Get detailed app info (PID, path, window rect)
- `cuactl app-position "AppName"` — Get window position only
- `cuactl open-app "AppName"` — Open/activate an application
- `cuactl close-app "AppName"` — Close an application

## Workflow Best Practices

### 1. Always check current state first
Before any action, take a screenshot or use deterministic ops to understand the current desktop state.

### 2. Prefer deterministic ops over screenshots
When you just need to open an app or find where it is, use `list-apps` / `app-info` / `open-app` instead of screenshot + click. This is faster and more reliable.

### 3. Typical workflow
```
1. cuactl list-apps              # See what's running
2. cuactl open-app "Chrome"      # Activate the browser
3. cuactl capture                # Screenshot to see the page
4. [Analyze screenshot, plan next action]
5. cuactl click 500 300          # Click where needed
6. cuactl type "search query"    # Type text
7. cuactl press_key "enter"      # Press Enter
```

### 4. Coordinate system
- Screenshots are in screen coordinates (origin at top-left of primary monitor)
- Use `app-position` to find exactly where a window is on screen
- Click coordinates are relative to the whole screen, not the window

### 5. Error handling
- If a command fails, read the error message carefully
- Common issues: app not running, wrong coordinates, permission denied
- Use `cuactl list-apps` to verify app state before interacting

### 6. Safety
- Only perform actions the user explicitly requested
- If unsure, ask the user before clicking or typing
- Never type passwords or sensitive information unless explicitly asked
