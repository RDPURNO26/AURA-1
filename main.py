# main.py
"""
AURA v4 – Main Entry Point
Connects all three processes via Shared Memory IPC and launches the system.

Run this file to start AURA.
Press Ctrl+C to shut down cleanly.

Requirements: see requirements.txt (includes pywin32 for focus guard).
Place hand_landmarker.task next to mediapipe_process.py (bundle for offline demos).
"""

import logging
import multiprocessing as mp
from multiprocessing import shared_memory
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

# Shared memory constants
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FRAME_CHANNELS = 3
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT * FRAME_CHANNELS
SHM_NAME = "aura_frame_buffer"


def configure_logging():
    import sys
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).parent
    else:
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
    try:
        print("")
        print("=" * 55)
        print("         █████╗ ██╗   ██╗██████╗  █████╗         ")
        print("        ██╔══██╗██║   ██║██╔══██╗██╔══██╗        ")
        print("        ███████║██║   ██║██████╔╝███████║        ")
        print("        ██╔══██║██║   ██║██╔══██╗██╔══██║        ")
        print("        ██║  ██║╚██████╔╝██║  ██║██║  ██║        ")
        print("        ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝        ")
    except UnicodeEncodeError:
        print("")
        print("=" * 55)
        print("         AURA - AI User-hand Recognition")
    
    print("=" * 55)
    print(f"   Screen: {screen_w}x{screen_h}")
    print("   Mode: Gesture Control — Right Hand")
    print("   IPC: Shared Memory (zero-copy)")
    print("   Log: aura.log")
    print("   Press Ctrl+C to exit")
    print("=" * 55)
    print("")


def create_shared_memory():
    """Create or connect to shared memory block for frame transfer."""
    # Clean up any leftover shared memory from a previous crash
    try:
        old_shm = shared_memory.SharedMemory(name=SHM_NAME)
        old_shm.close()
        old_shm.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass

    shm = shared_memory.SharedMemory(name=SHM_NAME, create=True, size=FRAME_SIZE)
    _log.info("Shared memory created: %s (%d bytes)", SHM_NAME, FRAME_SIZE)
    return shm


def respawn_worker(name, frame_queue, landmark_queue, stop_event, shm_name, lite_mode=False):
    if name == "Camera":
        p = mp.Process(
            target=camera_process,
            args=(frame_queue, stop_event, shm_name, lite_mode),
            name="CameraProcess",
            daemon=True,
        )
    elif name == "MediaPipe":
        p = mp.Process(
            target=mediapipe_process,
            args=(frame_queue, landmark_queue, stop_event, shm_name, lite_mode),
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


def shutdown(processes, stop_event, shm=None):
    _log.info("Shutting down…")
    stop_event.set()

    for name, proc in processes:
        proc.join(timeout=5)
        if proc.is_alive():
            _log.warning("Force terminating %s", name)
            proc.terminate()
            proc.join(timeout=2)

    # Clean up shared memory
    if shm:
        try:
            shm.close()
            shm.unlink()
            _log.info("Shared memory cleaned up")
        except Exception:
            pass

    _log.info("All processes stopped.")


def main():
    configure_logging()
    import sys as _sys
    lite_mode = '--lite' in _sys.argv
    screen_w, screen_h = get_screen_size()
    print_banner(screen_w, screen_h)
    if lite_mode:
        _log.info("⚡ Lite Mode active (low RAM detected)")
        print("  ⚡ Lite Mode — reduced FPS & thresholds for performance")

    # Create shared memory for zero-copy frame transfer
    shm = create_shared_memory()

    frame_queue = mp.Queue(maxsize=1)
    landmark_queue = mp.Queue(maxsize=1)
    stop_event = mp.Event()

    cam_proc = mp.Process(
        target=camera_process,
        args=(frame_queue, stop_event, SHM_NAME, lite_mode),
        name="CameraProcess",
        daemon=True,
    )
    mp_proc = mp.Process(
        target=mediapipe_process,
        args=(frame_queue, landmark_queue, stop_event, SHM_NAME, lite_mode),
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
    print("[Main] Index+Pinky = LOCK | Pinky only = CLUTCH | L-shape = Volume")
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
                        processes[i] = (name, respawn_worker(
                            name, frame_queue, landmark_queue, stop_event, SHM_NAME, lite_mode))
                    except Exception:
                        _log.exception("Failed to respawn %s", name)
                    time.sleep(0.5 if name == "Camera" else 0.25)

    except KeyboardInterrupt:
        pass
    finally:
        shutdown(processes, stop_event, shm)


if __name__ == "__main__":
    main()
