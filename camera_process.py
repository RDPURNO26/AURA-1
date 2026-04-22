# camera_process.py
"""
AURA – Camera Capture Process
Captures webcam frames, flips them, timestamps them,
and puts (timestamp, frame) into frame_queue.
Queue max size = 1. Always fresh. Never stale.

Fixes from stress test review:
- Timestamp taken AT capture (not after queue delay)
- Camera auto-recovery if device temporarily claimed by another app
- Pre-allocated flip buffer (no new numpy array every frame)
- 5-frame warmup to skip black CAP_DSHOW startup frames
"""

import cv2
import multiprocessing as mp
import time
import numpy as np


def camera_process(frame_queue: mp.Queue, stop_event: mp.Event):
    print("[Camera] Started")

    flip_buffer = None  # Pre-allocated once — reused every frame

    def open_camera():
        c = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        c.set(cv2.CAP_PROP_FPS, 30)
        if not c.isOpened():
            return None
        for _ in range(5):   # Warmup — CAP_DSHOW first frames are often black
            c.read()
        print("[Camera] Webcam opened successfully.")
        return c

    cap = open_camera()
    if cap is None:
        print("[Camera] ERROR: Could not open webcam. Check connection.")
        return

    consecutive_failures = 0
    MAX_FAILURES = 30  # ~1 second at 30fps before recovery attempt

    while not stop_event.is_set():
        ret, frame = cap.read()
        ts = time.time()  # Timestamp RIGHT at capture — critical for FSM timing

        if not ret or frame is None:
            consecutive_failures += 1
            if consecutive_failures >= MAX_FAILURES:
                print("[Camera] Camera lost — attempting recovery...")
                cap.release()
                time.sleep(1.0)
                cap = open_camera()
                if cap is None:
                    print("[Camera] Recovery failed. Stopping.")
                    break
                consecutive_failures = 0
                flip_buffer = None  # Reset buffer shape after recovery
            continue

        consecutive_failures = 0

        # Allocate flip buffer once on first valid frame
        if flip_buffer is None or flip_buffer.shape != frame.shape:
            flip_buffer = np.empty_like(frame)

        cv2.flip(frame, 1, flip_buffer)  # Flip into pre-allocated buffer

        # Drop stale frame before inserting new one
        if not frame_queue.empty():
            try:
                frame_queue.get_nowait()
            except Exception:
                pass

        try:
            frame_queue.put_nowait((ts, flip_buffer.copy()))
        except Exception:
            pass

    if cap is not None:
        cap.release()
    print("[Camera] Stopped")


if __name__ == "__main__":
    """Standalone test — run this file to verify camera works before full integration."""
    import threading

    test_queue = mp.Queue(maxsize=1)
    test_stop = mp.Event()

    t = threading.Thread(target=camera_process, args=(test_queue, test_stop))
    t.start()

    print("[Camera Test] Press Q to stop.")
    try:
        while True:
            if not test_queue.empty():
                ts, frame = test_queue.get_nowait()
                cv2.imshow("Camera Test — AURA", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        test_stop.set()
        t.join(timeout=3)
        cv2.destroyAllWindows()
        print("[Camera Test] Complete.")
