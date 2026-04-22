# AURA — AI-powered User-hand Recognition & Automation

Vision-Based Hand Gesture Control System for Windows — no extra hardware, just a webcam.

## What is AURA?

AURA is a real-time hand gesture system that fully replaces your computer mouse using only a standard webcam and Google's MediaPipe hand tracking AI. By translating specific hand poses into cursor movements and clicks, it enables precise touchless interaction across your entire Windows desktop. AURA tracks your palm centroid instead of fingertips to ensure jitter-free control, making it a reliable solution for daily hands-free usage.

## Features

- **Smooth Cursor Control**: Move the cursor seamlessly with a two-finger "peace sign" (index + middle fingers extended).
- **Precision Drop-Finger Clicks**: Drop your index finger for left-click, or drop your middle finger for right-click. The cursor freezes instantly to prevent aim drift.
- **Double Click**: Extend your thumb while holding the peace sign.
- **Drag & Drop**: Make a fist (all fingers down) to start dragging with relative, stable tracking. Release by returning to a peace sign.
- **Position-Based Joystick Scroll**: Raise three fingers (index, middle, ring) and move your hand up/down to scroll.
- **Position-Based Joystick Zoom**: Open your entire hand (all fingers extended) and move it up/down to zoom in/out.
- **Volume Control**: Raise your ring finger only and move your hand up/down to adjust system volume.
- **Clutch / Recenter**: Raise your pinky only to pause cursor tracking, allowing you to reposition your hand comfortably.
- **Full Lock**: Raise your ring finger only to completely lock and pause the system.
- **Voice Typing Toggle**: Extend your pinky and thumb to toggle the Windows Voice Typing feature (Win+H) for hands-free text input.

## Tech Stack

AURA is built entirely in Python using the following core libraries:
- **Python**: Core application language.
- **MediaPipe**: Google's AI framework for robust real-time hand landmark detection.
- **OpenCV (cv2)**: High-performance webcam capture, image flipping, and overlay rendering.
- **NumPy**: Efficient vector math for computing distances, angles, and One Euro filtering.
- **Pynput**: Operating system-level keyboard simulation (e.g., triggering Win+H and Ctrl keys).
- **Pywin32 (ctypes, user32)**: Direct Windows API calls for zero-latency absolute cursor positioning and mouse events.
- **Multiprocessing**: Concurrent execution to separate camera capture, AI inference, and OS input control.

## System Architecture

AURA relies on a highly responsive, parallel three-process pipeline to ensure smooth, zero-latency performance:

1. **Camera Process**: Captures webcam frames at 30 FPS, flips them, timestamps them precisely at capture time, and pushes them to a shared queue.
2. **MediaPipe Process**: Reads the latest frame, runs the MediaPipe Hand Landmarker model to extract 21 3D hand landmarks, and forwards the results.
3. **Controller Process**: Applies a custom One Euro Filter to smooth coordinates, processes the landmarks through a Finite State Machine (FSM), and issues direct Windows API commands to control the cursor and fire actions.

Communication between these processes happens via non-blocking `multiprocessing.Queue(maxsize=1)` buffers, ensuring that the system always works with the freshest frame and never processes stale data.

## Getting Started

```bash
git clone https://github.com/RDPURNO26/AURA
cd AURA
pip install -r requirements.txt
python main.py
```

> **Note:** The `hand_landmarker.task` AI model file is NOT included in this repository due to its file size. Before running the application, you must download the MediaPipe hand landmarker bundle separately and place `hand_landmarker.task` directly into the project root directory alongside `main.py`.

## Gesture Reference

| Gesture | Fingers | Action |
| --- | --- | --- |
| Fist | 0 (All down) | Drag & Drop |
| Index only | 1 (Index up) | Right Click |
| Middle only | 1 (Middle up) | Left Click |
| Ring only | 1 (Ring up) | Lock (Full pause) |
| Pinky only | 1 (Pinky up) | Clutch (Recenter hand) |
| Pinky + Thumb | 2 (Pinky, Thumb up) | Toggle Voice Typing |
| Peace sign | 2 (Index, Middle up) | Move Cursor |
| Peace + Thumb | 3 (Index, Middle, Thumb up) | Double Click |
| Three fingers | 3 (Index, Middle, Ring up) | Scroll (Joystick style) |
| Open hand | 4+ (All fingers up) | Zoom (Joystick style) |

## Project Structure

- `main.py`: Main Entry Point — Connects all three processes and launches the system.
- `camera_process.py`: Camera Capture Process — Captures webcam frames, flips them, timestamps them, and puts them into the queue.
- `mediapipe_process.py`: MediaPipe Hand Tracking Process (Tasks API) — Runs offline inference to extract hand landmarks.
- `controller_process.py`: Controller — Handles cursor mapping, One Euro filtering, input dispatch, and screen overlay.
- `gesture_fsm.py`: Two-finger control system — Maintains the 8-state finite state machine for robust debounced gesture detection.
- `CONTROLS_GUIDE.txt`: Quick reference text document outlining all gestures and rules.
- `MANUAL.md`: Technical user manual detailing calibration, architecture, and troubleshooting.
- `PROJECT_REPORT.md`: Comprehensive project report explaining the design, rationale, and underlying mechanics.
- `requirements.txt`: List of required Python dependencies for the project.

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| MediaPipe exits immediately | Add `hand_landmarker.task` next to `mediapipe_process.py`. |
| Clicks too sensitive | The adaptive threshold should handle this automatically. If it persists, try keeping your hand still for the first 2 seconds of use to get a clean calibration. |
| Cursor wrong after clutch | Hold pinky-only to clutch, recenter, then index clearly up for 4 frames. |
| LOCKED exits too fast | Make sure to close all fingers into a fist. Opening requires 2+ fingers clearly extended. |

## Author

Built by **RD Purno**

## License

MIT License
