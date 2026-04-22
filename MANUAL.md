# AURA — User manual

AURA drives your Windows cursor with your **right hand** via the webcam. The preview window is mirrored so it feels like pointing at the screen.

## Requirements

- Windows 10/11  
- Webcam  
- Python packages: `pip install -r requirements.txt` (includes **pywin32** for focus safety)  
- **Offline:** copy **`hand_landmarker.task`** into the same folder as `mediapipe_process.py` (the app does **not** download it at runtime).  

Run:

```text
python main.py
```

Logs: **`aura.log`** in the project folder. Press **Ctrl+C** to exit.

---

## Auto-Calibration

AURA now **auto-calibrates** your pinch threshold during the first ~60 frames of cursor movement. No manual calibration step needed:

1. Point with **index finger only** — move your hand naturally for ~2 seconds.  
2. The system samples your open-hand pinch distance and sets the threshold automatically.  
3. Progress is logged: `Adaptive pinch threshold: X.XXXX`.  

---

## Cursor Tracking

The cursor is driven by the **palm centroid** (average of the four MCP joints), **not** the fingertip. This means:

- **No jitter** when you flex or pinch your fingers.  
- The cursor tracks your **hand position**, not individual finger movements.  
- Pinching to click does **not** move the cursor — it stays locked where you aimed.  

---

## Gestures (finger count, no overlap)

| Pose | Mode |
|------|------|
| **Index only** (other fingers down) | Move cursor; pinch = click / drag (see below). |
| **Fist** (0 fingers) **6 frames** | **LOCKED** — pause; cursor stays put. **Open 2+ fingers** → **PASSIVE**, then engage move again. |
| **Pinky only** (pinky up, others down) **6 frames** | **CLUTCH** — cursor frozen; recenter hand; **index up 4 frames** to resume with **relative** aim. |
| **Index + middle** (ring + pinky down) | Scroll (cursor fixed). Stays stable — exits only after **4 frames** without the pose. |
| **Index + middle + ring** (pinky down) | Zoom (cursor fixed; pinch open/close). Exits only after **4 frames** without the pose. |

### Clicking

- Pinch your index finger toward your thumb past **70%** of the calibrated threshold for **5 frames** to **arm** a click.  
- The cursor **freezes** the instant arming begins — your aim is locked.  
- **Open** past **108%** of the threshold to fire the click at the pinned location.  
- Hold the pinch for **12 frames** instead to start a **drag**.  

---

## Auto-restart

If **Camera**, **MediaPipe**, or **Controller** exits unexpectedly, **main.py** respawns that worker (see log).

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| MediaPipe exits immediately | Add **`hand_landmarker.task`** next to `mediapipe_process.py`. |
| Clicks too sensitive | The adaptive threshold should handle this automatically. If it persists, try keeping your hand still for the first 2 seconds of use to get a clean calibration. |
| Cursor wrong after clutch | Hold **pinky-only** to clutch, recenter, then **index** clearly up for 4 frames. |
| LOCKED exits too fast | Make sure to close **all** fingers into a fist. Opening requires **2+ fingers** clearly extended. |

---

## Technical

- **Cursor anchor:** Palm centroid (average of landmarks 5, 9, 13, 17 — MCP joints).  
- **Pinch detection:** 3D distance (X+Y+Z) between landmarks 4 and 8, normalized by palm scale.  
- **Scroll velocity:** Landmark 9 (middle MCP) Y-axis movement — stable, not affected by finger flexion.  
- **Queues:** blocking `get(timeout=0.033)` in MediaPipe and Controller (low busy-wait).  
- **Smoothing:** One Euro `freq=60`, `fmin=1.5`, `beta=0.007`, `dcutoff=1.0`; anti-teleport **4%** of desktop width.  
- **FSM:** `gesture_fsm.py` — `update(inputs, prev_lm)` → `state`, `action`, `pinch_threshold`, `arming`.  
- **MediaPipe timestamps:** Real milliseconds (not frame counter) for accurate internal tracking.  
