# main.py
"""
AURA – Main Entry Point
Connects all three processes and launches the system.

Run this file to start AURA.
Press Ctrl+C to shut down cleanly.

Requirements: see requirements.txt (includes pywin32 for focus guard).
Place hand_landmarker.task next to mediapipe_process.py (bundle for offline demos).
"""

import logging
import multiprocessing as mp
import ctypes
import time
from pathlib import Path

# ============================================================
# MUST BE FIRST — before any other multiprocessing import
# ============================================================
if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

from camera_process import camera_process
from mediapipe_process import mediapipe_process
from controller_process import controller_process

_log = logging.getLogger("aura.main")


def configure_logging():
    root = Path(__file__).resolve().parent
    log_path = root / "aura.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    _log.info("Logging to %s", log_path)


def get_screen_size():
    user32 = ctypes.windll.user32
    try:
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception:
        user32.SetProcessDPIAware()
    w = user32.GetSystemMetrics(78)
    h = user32.GetSystemMetrics(79)
    if w <= 0 or h <= 0:
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
    return w, h


def print_banner(screen_w, screen_h):
    print("")
    print("=" * 55)
    print("         █████╗ ██╗   ██╗██████╗  █████╗         ")
    print("        ██╔══██╗██║   ██║██╔══██╗██╔══██╗        ")
    print("        ███████║██║   ██║██████╔╝███████║        ")
    print("        ██╔══██║██║   ██║██╔══██╗██╔══██║        ")
    print("        ██║  ██║╚██████╔╝██║  ██║██║  ██║        ")
    print("        ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝        ")
    print("=" * 55)
    print(f"   Screen: {screen_w}x{screen_h}")
    print("   Mode: Gesture Control — Right Hand")
    print("   Log: aura.log")
    print("   Press Ctrl+C to exit")
    print("=" * 55)
    print("")


def respawn_worker(name, frame_queue, landmark_queue, stop_event):
    if name == "Camera":
        p = mp.Process(
            target=camera_process,
            args=(frame_queue, stop_event),
            name="CameraProcess",
            daemon=True,
        )
    elif name == "MediaPipe":
        p = mp.Process(
            target=mediapipe_process,
            args=(frame_queue, landmark_queue, stop_event),
            name="MediaPipeProcess",
            daemon=True,
        )
    elif name == "Controller":
        p = mp.Process(
            target=controller_process,
            args=(landmark_queue, stop_event),
            name="ControllerProcess",
            daemon=True,
        )
    else:
        raise ValueError(name)
    p.start()
    return p


def shutdown(processes, stop_event):
    _log.info("Shutting down…")
    stop_event.set()

    for name, proc in processes:
        proc.join(timeout=5)
        if proc.is_alive():
            _log.warning("Force terminating %s", name)
            proc.terminate()
            proc.join(timeout=2)

    _log.info("All processes stopped.")


def main():
    configure_logging()
    screen_w, screen_h = get_screen_size()
    print_banner(screen_w, screen_h)

    frame_queue = mp.Queue(maxsize=1)
    landmark_queue = mp.Queue(maxsize=1)
    stop_event = mp.Event()

    cam_proc = mp.Process(
        target=camera_process,
        args=(frame_queue, stop_event),
        name="CameraProcess",
        daemon=True,
    )
    mp_proc = mp.Process(
        target=mediapipe_process,
        args=(frame_queue, landmark_queue, stop_event),
        name="MediaPipeProcess",
        daemon=True,
    )
    ctrl_proc = mp.Process(
        target=controller_process,
        args=(landmark_queue, stop_event),
        name="ControllerProcess",
        daemon=True,
    )

    processes = [
        ("Camera", cam_proc),
        ("MediaPipe", mp_proc),
        ("Controller", ctrl_proc),
    ]

    _log.info("Starting camera…")
    cam_proc.start()
    time.sleep(0.5)

    _log.info("Starting MediaPipe…")
    mp_proc.start()
    time.sleep(0.3)

    _log.info("Starting controller…")
    ctrl_proc.start()

    _log.info("All workers running. See MANUAL.md for gestures.")
    print("[Main] aura.log — full diagnostics")
    print("[Main] Fist = LOCK (pause) | Pinky only = CLUTCH (recenter)")
    print("")

    try:
        while True:
            time.sleep(1.0)
            if stop_event.is_set():
                break

            for i, (name, proc) in enumerate(processes):
                if stop_event.is_set():
                    break
                if not proc.is_alive():
                    _log.error("%s died — respawning", name)
                    try:
                        proc.terminate()
                        proc.join(timeout=1)
                    except Exception:
                        pass
                    try:
                        processes[i] = (name, respawn_worker(name, frame_queue, landmark_queue, stop_event))
                    except Exception:
                        _log.exception("Failed to respawn %s", name)
                    time.sleep(0.5 if name == "Camera" else 0.25)

    except KeyboardInterrupt:
        pass
    finally:
        shutdown(processes, stop_event)


if __name__ == "__main__":
    main()
