# AURA v1.0 — Project Report
### Hand Gesture Desktop Control System
### Author: AURA Team | Date: April 2026

---

## Table of Contents

1. [What is AURA](#what-is-aura)
2. [How It Works](#how-it-works)
3. [The Control System](#the-control-system)
4. [Technical Architecture](#technical-architecture)
5. [Key Innovations](#key-innovations)
6. [Current Capabilities](#current-capabilities)
7. [Known Limitations](#known-limitations)
8. [Production Roadmap](#production-roadmap)
9. [File Reference](#file-reference)

---

## What is AURA

AURA is a **real-time hand gesture system that fully replaces the mouse** on Windows. Using only a standard webcam and Google's MediaPipe hand tracking AI, it translates hand poses into cursor movement, clicks, scrolling, zooming, volume control, drag-and-drop, and voice typing — all with zero additional hardware.

The system runs as a lightweight multi-process Python application that operates alongside any Windows application. It doesn't require focus, doesn't need a special window active, and works across the entire desktop including all monitors.

**In simple terms:** You point at your screen with your hand, and AURA moves your mouse. You close a finger, it clicks. You raise three fingers, it scrolls. No touchpad, no mouse, no stylus needed.

---

## How It Works

### The Pipeline

```
  WEBCAM                MEDIAPIPE AI              GESTURE FSM              WINDOWS
    │                       │                         │                      │
    │  30fps RGB frames     │  21 hand landmarks      │  State + Action      │
    ├──────────────────────►├────────────────────────►├─────────────────────►│
    │                       │  (x, y, z per joint)    │  (MOVE, CLICK, etc)  │
    │                       │                         │                      │
    │  Camera Process       │  MediaPipe Process      │  Controller Process  │
    │  (capture + flip)     │  (AI inference)         │  (cursor + input)    │
```

1. **Camera Process** captures frames from the webcam at ~30fps, flips them horizontally (mirror mode), and timestamps each frame with real millisecond precision.

2. **MediaPipe Process** receives each frame and runs Google's Hand Landmarker AI model. It outputs 21 3D landmark points (x, y, z) for every joint in the hand, plus a confidence score.

3. **Controller Process** takes those 21 landmarks and:
   - Classifies which fingers are extended (using bone angle cosine checks)
   - Feeds the classification into the Gesture FSM (Finite State Machine)
   - Maps the palm centroid to screen coordinates
   - Applies One Euro smoothing filters
   - Sends mouse/keyboard events to Windows via ctypes

All three processes run in parallel using Python's `multiprocessing` module, connected by thread-safe queues. The main process (`main.py`) orchestrates startup and auto-restarts any crashed worker.

---

## The Control System

### v3 — "Two-Finger" Design

The control system went through three major iterations to reach the current design:

- **v1** (original): Index finger tracking + pinch-to-click. Failed because pinching moves the fingertip, causing cursor drift.
- **v2**: Open hand tracking + fist-to-click. Better, but finger-count transitions caused "buzzing" (state oscillation).
- **v3** (current): Peace sign tracking + drop-finger clicking. The breakthrough design.

### Complete Gesture Table

```
┌─────────────────────────────┬────────────────────────────────────────┐
│ GESTURE                     │ ACTION                                 │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ ✌️  Peace sign               │ MOVE CURSOR                            │
│ (index + middle up)         │ Cursor follows palm centroid            │
│                             │ ONLY pose that moves cursor             │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ Drop INDEX finger           │ LEFT CLICK                             │
│ (middle stays up)           │ Cursor freezes → fires once            │
│                             │ Raise index to resume                  │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ Drop MIDDLE finger          │ RIGHT CLICK                            │
│ (index stays up)            │ Cursor freezes → fires once            │
│                             │ Raise middle to resume                 │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ ✌️ + 👍 Thumb out            │ DOUBLE CLICK                           │
│ (index+middle+thumb)        │ Fires once, return to peace to reset   │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ ✊ Fist (hold 0.3s)          │ DRAG                                   │
│ (0 fingers, thumb tucked)   │ Relative mode — no cursor jump         │
│                             │ Peace sign to release                  │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ 🤟 Three fingers             │ SCROLL (joystick mode)                 │
│ (index+middle+ring)         │ Hand above center = scroll up          │
│                             │ Hand below center = scroll down        │
│                             │ Further from center = faster           │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ 🖐️ Open hand (4+ fingers)    │ ZOOM (joystick mode)                   │
│                             │ Hand up = zoom in                      │
│                             │ Hand down = zoom out                   │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ 🤙 Pinky only               │ CLUTCH (recenter)                      │
│                             │ Cursor freezes, reposition hand        │
│                             │ Peace sign to resume from frozen spot  │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ 💍 Ring only                 │ VOLUME CONTROL (joystick mode)         │
│                             │ Hand up = volume up                    │
│                             │ Hand down = volume down                │
│                             │                                        │
├─────────────────────────────┼────────────────────────────────────────┤
│                             │                                        │
│ 👍 Thumb only                │ VOICE TYPING TOGGLE                    │
│ (thumb out, all fingers in) │ Sends Win+H to start/stop              │
│                             │ Windows voice dictation                │
│                             │                                        │
└─────────────────────────────┴────────────────────────────────────────┘
```

### Finger Count Map (Zero Overlap)

```
  0 fingers (fist, thumb in)    = DRAG
  0 fingers (thumb out)         = VOICE TYPING
  1 finger  (index only)        = RIGHT CLICK trigger
  1 finger  (middle only)       = LEFT CLICK trigger
  1 finger  (ring only)         = VOLUME CONTROL
  1 finger  (pinky only)        = CLUTCH
  2 fingers (index+middle)      = MOVE CURSOR  ← only moving pose
  2 fingers (index+middle+thumb)= DOUBLE CLICK
  3 fingers (index+middle+ring) = SCROLL
  4+ fingers (open hand)        = ZOOM
```

Every gesture uses a completely different finger configuration. No two gestures share the same finger pattern. Transitions between gestures pass through intermediate states that act as "dead zones" — they don't trigger any action, preventing buzzing.

---

## Technical Architecture

### Process Architecture

```
main.py (orchestrator)
  │
  ├── camera_process.py      → Captures webcam frames
  │     └── Queue ──────────────┐
  │                             │
  ├── mediapipe_process.py   ← Receives frames, runs AI
  │     └── Queue ──────────────┐
  │                             │
  └── controller_process.py  ← Receives landmarks, drives cursor
        ├── gesture_fsm.py      (state machine logic)
        └── Windows API         (SetCursorPos, mouse_event, keybd_event)
```

### Cursor Tracking System

**Palm Centroid:** The cursor position is calculated from the average of four MCP (metacarpophalangeal) joints — landmarks 5, 9, 13, and 17. These are the knuckle joints at the base of each finger. Unlike fingertips, MCP joints barely move when you flex or extend fingers, providing a stable tracking anchor.

**One Euro Filter:** Raw palm coordinates are passed through a One Euro filter before being mapped to screen coordinates. The filter provides:
- Low jitter at rest (high smoothing when hand is still)
- Low latency during movement (smoothing decreases as speed increases)
- Parameters: `fmin=1.5` (minimum cutoff), `beta=0.007` (speed coefficient)

**Drag Filter:** A separate, heavier One Euro filter (`fmin=3.0, beta=0.004`) is used during dragging for extra stability. Dragging requires precision, and the fist pose introduces more palm centroid noise than the peace sign.

**Zone Margin:** A 10% margin on all sides of the camera frame maps to the full screen. This means the usable tracking area is the central 80% of the frame, giving the user room to move without hitting edges.

**Anti-Teleport:** If the filtered cursor position jumps more than 5% of the screen width in a single frame (2% during drag), the jump is rejected and the cursor stays at its previous position. This prevents the cursor from teleporting due to MediaPipe tracking glitches.

### Gesture State Machine

The FSM has 8 states with debounced transitions:

```
States: IDLE, MOVE, CLICKING, DRAGGING, SCROLLING, ZOOMING, CLUTCH, VOLUME

IDLE ──(peace 3f)──► MOVE
MOVE ──(fist 2f)───► CLICKING ──(hold 10f)──► DRAGGING
MOVE ──(3 fingers)─► SCROLLING
MOVE ──(4 fingers)─► ZOOMING
MOVE ──(pinky)─────► CLUTCH
MOVE ──(ring)──────► VOLUME
CLICKING ──(open)──► MOVE (+ LEFT_CLICK action)
CLICKING ──(index)─► MOVE (+ RIGHT_CLICK action)
DRAGGING ──(peace)─► MOVE (+ DRAG_END action)
All states ──(peace)──► MOVE (exit gesture)
```

Every transition requires multiple consecutive frames of the target pose (debounce). This prevents accidental state changes from brief hand jitter.

### Click System

The click mechanism is the core innovation:

1. User is in MOVE state (peace sign, both fingers up, cursor tracking)
2. User drops ONE finger (e.g., index for left click)
3. **Instantly:** `is_peace` becomes False → cursor tracking stops → cursor freezes
4. FSM counts 3 frames of the one-finger pose (debounce)
5. Click action fires at the frozen cursor position
6. `_click_cd` flag is set → prevents re-firing
7. User raises finger back to peace sign → `_click_cd` clears → cursor resumes

The cursor is frozen for the entire click sequence. The click fires at the exact pixel where the cursor was when the finger started dropping. No drift, no jitter, no missed targets.

### Relative Drag Mode

When dragging starts, the system saves:
- `drag_cursor_sx/sy`: the cursor position at the moment the fist was made
- `drag_anchor_nx/ny`: the normalized palm position at that moment

During drag, the cursor is computed as:
```
cursor = drag_cursor + (current_palm - drag_anchor) × screen_size
```

This means the cursor starts exactly where it was and moves relative to the hand's movement from the anchor point. No jump when entering drag, and the heavier drag filter ensures smooth, controllable movement.

### Position-Based Joystick (Scroll/Zoom/Volume)

Instead of velocity-based control (which is unpredictable), scroll, zoom, and volume use the hand's Y position relative to the center of the gesture zone:

```
  ┌──── Top of zone ────┐
  │   FAST (rate: 2f)    │   Hand far above center
  │   MEDIUM (rate: 5f)  │   Hand slightly above
  │   ─── DEAD ZONE ──── │   Center ±5% = no action
  │   MEDIUM (rate: 5f)  │   Hand slightly below
  │   FAST (rate: 2f)    │   Hand far below center
  └──── Bottom of zone ──┘
```

The `rate` value determines how many frames pass between each scroll/volume event. Lower rate = more frequent = faster scrolling. The dead zone at center prevents accidental scrolling when the hand is at rest.

---

## Key Innovations

### 1. Drop-Finger Click (Novel)

Most hand gesture mouse projects use **pinch-to-click** (thumb + index finger). This has a fundamental flaw: the index fingertip moves toward the thumb during the pinch, and since the cursor typically tracks the fingertip, the cursor drifts away from the target during the click action.

AURA's solution: track with TWO fingers (peace sign), and the act of LOWERING one finger is the click trigger. Since the palm centroid barely moves when a single finger lowers, the cursor stays perfectly still. The click fires at the exact spot where the cursor was before the finger moved.

This is not just a workaround — it's a fundamentally better input model for hand gesture clicking.

### 2. Position-Based Joystick Scrolling (Novel)

Most gesture systems use hand velocity for scrolling — move hand up fast = scroll up fast. This is hard to control because:
- You have to keep moving to keep scrolling
- Speed is hard to modulate (small hand movements at different speeds)
- Stopping requires actively stopping your hand

AURA uses hand POSITION instead — like a joystick:
- Hold hand above center = scrolling up (continuously)
- Hold further up = scrolling faster
- Return to center = stop scrolling

This is far more intuitive and controllable. You don't have to keep moving. You just hold your hand at the desired position and scrolling happens at a proportional speed.

### 3. Relative Drag Mode

Dragging is notoriously difficult in hand gesture systems because:
- The hand pose changes (from open to fist), shifting the tracking centroid
- The cursor needs to stay precise during the entire drag

AURA saves the cursor position and palm anchor at drag initiation, then computes all subsequent positions as offsets. Combined with a heavier smoothing filter, this makes drag-and-drop usable for real tasks like moving windows and selecting text.

### 4. One-Shot Click Cooldown

Every click type (left, right, double) fires exactly once per gesture, enforced by a `_click_cd` flag that only clears when the user returns to a pure peace sign (without thumb). This prevents click spamming from holding a gesture pose and makes the system predictable.

---

## Current Capabilities

### What Works

- ✅ Full cursor control across entire desktop (all monitors)
- ✅ Left click with precise aim (cursor frozen during click)
- ✅ Right click (drop middle finger)
- ✅ Double click (peace sign + thumb)
- ✅ Drag and drop (fist hold, relative mode, heavy smoothing)
- ✅ Scroll up/down (joystick mode, 3 speed tiers)
- ✅ Zoom in/out (joystick mode, Ctrl+scroll)
- ✅ Volume up/down (joystick mode, system volume keys)
- ✅ Clutch / recenter (pinky only, relative resume)
- ✅ Voice typing toggle (thumb only, Win+H)
- ✅ Anti-teleport cursor protection
- ✅ Auto-restart crashed worker processes
- ✅ Real-time preview window with state/action overlay
- ✅ Works with any application (no focus requirement)

### Performance

- Frame rate: ~30fps (camera dependent)
- Latency: ~100-150ms end-to-end (camera → cursor)
- CPU usage: ~15-25% on a modern quad-core
- Memory: ~200MB (mostly MediaPipe model)

---

## Known Limitations

| Limitation | Impact | Severity |
|-----------|--------|----------|
| Right hand only | Left-handed users can't use the system | Medium |
| Single camera angle | Performance degrades at extreme angles | Medium |
| No multi-hand support | Can't use two hands for different functions | Low |
| Hardcoded thresholds | Different hand sizes may need different settings | High |
| No config file | All parameters require code editing to change | High |
| No installer | Must run from command line with Python | Medium |
| CPU-only MediaPipe | Higher latency than GPU-accelerated alternative | Medium |
| No graceful pause | Must Ctrl+C to stop, or remove hand for IDLE | Low |
| Lighting dependent | Poor lighting reduces MediaPipe accuracy | Medium |
| No gesture customization | Users can't remap gestures | Medium |

---

## Production Roadmap

### Phase 1 — Stability & Configuration (v1.1)

**Goal:** Make the system reliable enough for daily 8-hour use.

| Task | Priority | Effort | Description |
|------|----------|--------|-------------|
| Config file (`config.json`) | 🔴 Critical | 2 days | Extract all hardcoded thresholds (debounce frames, filter params, zone margins, speed tiers) to a JSON config file. Load at startup. |
| Per-user calibration | 🔴 Critical | 3 days | Run a 10-second calibration on first launch that measures the user's hand size, finger extension angles, and optimal thresholds. Save to `~/.aura/profile.json`. |
| Error recovery | 🔴 Critical | 2 days | Add try/except around all landmark processing. If MediaPipe returns garbage for N frames, reset filters and wait for stable tracking before resuming. |
| Logging improvements | 🟡 High | 1 day | Add structured logging with log levels. Include frame timing stats, gesture recognition rates, and error counts. |
| Left hand support | 🟡 High | 1 day | Detect hand chirality from MediaPipe, flip X coordinates for left hand. Add config option. |

### Phase 2 — Performance (v1.2)

**Goal:** Reduce latency below 80ms and support 60fps.

| Task | Priority | Effort | Description |
|------|----------|--------|-------------|
| GPU MediaPipe | 🔴 Critical | 3 days | Switch to MediaPipe GPU delegate or ONNX Runtime with DirectML. Should double frame rate. |
| Shared memory IPC | 🟡 High | 2 days | Replace multiprocessing.Queue with shared memory (mmap) for landmark data. Eliminates serialization overhead. |
| Adaptive frame rate | 🟡 High | 1 day | Run at 15fps when no hand detected (IDLE), ramp to 60fps when tracking. Saves CPU and battery. |
| Predictive tracking | 🟢 Medium | 2 days | Add Kalman filter on top of One Euro for frame-ahead prediction. Reduces perceived latency. |
| Camera resolution optimization | 🟢 Medium | 1 day | Test 320×240 vs 640×480 vs higher. Lower resolution = faster processing, potentially sufficient accuracy. |

### Phase 3 — User Experience (v1.3)

**Goal:** Make the system accessible to non-technical users.

| Task | Priority | Effort | Description |
|------|----------|--------|-------------|
| System tray app | 🔴 Critical | 3 days | Tray icon with pause/resume, settings, gesture guide, exit. No terminal needed. |
| On-screen state indicator | 🟡 High | 2 days | Small floating widget near cursor showing current state (MOVE, SCROLL, etc). Eliminates need to look at preview window. |
| Settings GUI | 🟡 High | 4 days | Tkinter or web-based settings panel. Adjust sensitivity, remap gestures, toggle features. |
| Gesture customization | 🟢 Medium | 3 days | Allow users to assign different finger combos to actions via the settings GUI. |
| Onboarding tutorial | 🟢 Medium | 2 days | Interactive first-run tutorial that teaches each gesture with visual feedback. |
| Sound feedback | 🟢 Medium | 1 day | Optional click/scroll sounds for confirmation. Helps when not looking at the screen. |

### Phase 4 — Distribution (v2.0)

**Goal:** Ship a product that anyone can install and use.

| Task | Priority | Effort | Description |
|------|----------|--------|-------------|
| PyInstaller packaging | 🔴 Critical | 2 days | Bundle everything into a single `.exe` with the MediaPipe model embedded. |
| Auto-updater | 🟡 High | 2 days | Check GitHub releases on startup, offer one-click update. |
| Installer (NSIS/MSI) | 🟡 High | 2 days | Proper Windows installer with Start Menu shortcut, uninstall, auto-start option. |
| Unit tests | 🟡 High | 3 days | Pytest test suite for FSM transitions, filter behavior, coordinate mapping. |
| CI/CD pipeline | 🟢 Medium | 2 days | GitHub Actions: lint, test, build exe, create release on tag push. |
| Documentation site | 🟢 Medium | 2 days | GitHub Pages with animated GIFs showing each gesture, FAQ, troubleshooting. |
| Telemetry (opt-in) | 🟢 Medium | 2 days | Anonymous usage stats: gesture frequency, error rates, session length. |

### Phase 5 — Advanced Features (v2.x)

| Task | Description |
|------|-------------|
| Multi-hand mode | Track both hands — left for cursor, right for actions (or vice versa) |
| Screen edge scrolling | Cursor near screen edge = auto-scroll (like in RDP/VNC) |
| Application profiles | Different gesture sensitivity per-app (e.g., slower for Photoshop, faster for browsing) |
| Gesture macros | Custom gesture → keyboard shortcut mapping (e.g., "L" pose = Alt+Tab) |
| Face tracking fallback | When no hand detected, track head tilt for basic cursor movement |
| Plugin system | Allow third-party gesture packs and action handlers |
| Linux/macOS support | Abstract the Windows-specific APIs (SetCursorPos, mouse_event, keybd_event) |
| AR/VR integration | Output gesture data over WebSocket for Unity/Unreal/WebXR consumption |

---

## File Reference

```
AURA/
├── main.py                  — Process orchestrator, auto-restart logic
├── camera_process.py        — Webcam capture, frame timestamping
├── mediapipe_process.py     — MediaPipe hand landmark inference
├── controller_process.py    — Cursor mapping, filtering, input dispatch
├── gesture_fsm.py           — Finite state machine for gesture recognition
├── hand_landmarker.task     — MediaPipe model file (offline, not downloaded)
├── requirements.txt         — Python dependencies
├── aura.log            — Runtime log file
├── CONTROLS_GUIDE.txt       — User-facing gesture reference
├── MANUAL.md                — Technical manual
├── PROJECT_REPORT.md        — This file
└── README.md                — Project overview
```

---

## Technical Specifications

| Parameter | Value |
|-----------|-------|
| Language | Python 3.10+ |
| AI Model | MediaPipe Hand Landmarker (CPU, VIDEO mode) |
| Landmarks | 21 points × 3 axes (x, y, z) per hand |
| Cursor anchor | Palm centroid (avg of MCP joints 5, 9, 13, 17) |
| Smoothing | One Euro filter (fmin=1.5, beta=0.007) |
| Drag smoothing | One Euro filter (fmin=3.0, beta=0.004) |
| Anti-teleport | 5% screen width (2% during drag) |
| Zone margin | 10% on all sides |
| Click debounce | 3 frames (~100ms) |
| Drag threshold | 10 frames (~330ms) |
| Scroll/zoom/volume | Position-based, 3 speed tiers (slow=10f, med=5f, fast=2f) |
| Scroll dead zone | ±5% from center |
| Scroll wheel amount | 60 units per event (half standard) |
| Process architecture | 3 parallel processes (camera, mediapipe, controller) |
| IPC | multiprocessing.Queue |
| OS API | ctypes (user32.dll: SetCursorPos, mouse_event, keybd_event) |
| Keyboard API | pynput (for Ctrl+scroll zoom and Win+H voice typing) |
| Preview | OpenCV window with landmark overlay and state display |

---

*AURA v1.0 — Built from scratch, designed to be used daily.*
