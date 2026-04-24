# aura_launcher.py
"""
AURA Launcher — Premium GUI with interactive gesture simulation.
Dark mode, animated, professional. Click 'Launch AURA' to start the gesture system.
"""

import tkinter as tk
from tkinter import font as tkfont
import subprocess
import sys
import os
import math
import time
import threading

# ── Lite Mode Detection ───────────────────────────────────────
LITE_MODE = False
try:
    import psutil
    total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    if total_ram_gb < 6.0:
        LITE_MODE = True
except ImportError:
    pass


# ── Color Palette ──────────────────────────────────────────────
BG_DARK      = "#0a0a0f"
BG_CARD      = "#12121a"
BG_CARD_HOVER = "#1a1a28"
ACCENT       = "#6c5ce7"
ACCENT_LIGHT = "#a29bfe"
ACCENT_GLOW  = "#8b7ff5"
GREEN        = "#00cec9"
GREEN_DARK   = "#00b894"
RED          = "#ff6b6b"
ORANGE       = "#fdcb6e"
TEXT_PRIMARY = "#f0f0f5"
TEXT_SECONDARY = "#8a8a9a"
TEXT_DIM     = "#555566"
BORDER       = "#2a2a3a"


# ── Hand Landmark Drawing ─────────────────────────────────────
# 21 landmarks relative positions for a right hand (normalized 0-1)
HAND_BASE = [
    (0.50, 0.90),  # 0: Wrist
    (0.45, 0.75),  # 1: Thumb CMC
    (0.38, 0.60),  # 2: Thumb MCP
    (0.32, 0.48),  # 3: Thumb IP
    (0.27, 0.38),  # 4: Thumb TIP
    (0.43, 0.48),  # 5: Index MCP
    (0.42, 0.32),  # 6: Index PIP
    (0.41, 0.20),  # 7: Index DIP
    (0.40, 0.12),  # 8: Index TIP
    (0.50, 0.45),  # 9: Middle MCP
    (0.50, 0.28),  # 10: Middle PIP
    (0.50, 0.16),  # 11: Middle DIP
    (0.50, 0.08),  # 12: Middle TIP
    (0.57, 0.47),  # 13: Ring MCP
    (0.58, 0.32),  # 14: Ring PIP
    (0.59, 0.20),  # 15: Ring DIP
    (0.60, 0.12),  # 16: Ring TIP
    (0.63, 0.52),  # 17: Pinky MCP
    (0.65, 0.40),  # 18: Pinky PIP
    (0.67, 0.30),  # 19: Pinky DIP
    (0.68, 0.22),  # 20: Pinky TIP
]

CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),
    (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),
]

# Gesture poses: which fingers are curled (tip moves to MCP area)
GESTURES = {
    "Peace Sign\n(Move Cursor)": {
        "desc": "Index + Middle up\nCursor follows palm",
        "color": GREEN,
        "curled": [3, 4, 14, 15, 16, 18, 19, 20],  # Ring + Pinky curled
        "thumb_in": True,
    },
    "Left Click": {
        "desc": "Drop Index finger\n(Middle stays up)",
        "color": ORANGE,
        "curled": [3, 4, 6, 7, 8, 14, 15, 16, 18, 19, 20],  # All except middle
        "thumb_in": True,
    },
    "Right Click": {
        "desc": "Drop Middle finger\n(Index stays up)",
        "color": ORANGE,
        "curled": [3, 4, 10, 11, 12, 14, 15, 16, 18, 19, 20],  # All except index
        "thumb_in": True,
    },
    "Fist\n(Drag & Drop)": {
        "desc": "All fingers down\nHold 0.3s to drag",
        "color": RED,
        "curled": [3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 16, 18, 19, 20],
        "thumb_in": True,
    },
    "Scroll\n(3 Fingers)": {
        "desc": "Index + Middle + Ring\nJoystick-style scroll",
        "color": ACCENT_LIGHT,
        "curled": [3, 4, 18, 19, 20],  # Pinky curled
        "thumb_in": True,
    },
    "Zoom\n(Open Hand)": {
        "desc": "All fingers up\nJoystick-style zoom",
        "color": ACCENT,
        "curled": [],
        "thumb_in": False,
    },
    "Volume\n(L-Shape)": {
        "desc": "Thumb + Index out\nHand up/down = volume",
        "color": GREEN_DARK,
        "curled": [10, 11, 12, 14, 15, 16, 18, 19, 20],
        "thumb_in": False,
    },
    "Lock\n(Index+Pinky)": {
        "desc": "Index + Pinky up\nPauses all tracking",
        "color": RED,
        "curled": [3, 4, 10, 11, 12, 14, 15, 16],
        "thumb_in": True,
    },
    "Clutch\n(Pinky Only)": {
        "desc": "Pinky up only\nRecenter your hand",
        "color": "#00ffff",
        "curled": [3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 16],
        "thumb_in": True,
    },
    "Double Click\n(Peace+Thumb)": {
        "desc": "Index + Middle + Thumb\nFires once",
        "color": ORANGE,
        "curled": [14, 15, 16, 18, 19, 20],
        "thumb_in": False,
    },
}


def get_hand_pose(gesture_data, hand_base):
    """Generate hand landmark positions for a given gesture."""
    pts = [list(p) for p in hand_base]
    curled = set(gesture_data.get("curled", []))

    # Curl specified landmarks toward wrist
    for idx in curled:
        if idx < len(pts):
            mcp_map = {6: 5, 7: 5, 8: 5, 10: 9, 11: 9, 12: 9,
                       14: 13, 15: 13, 16: 13, 18: 17, 19: 17, 20: 17,
                       3: 1, 4: 1}
            mcp = mcp_map.get(idx, 0)
            # Move curled fingertip toward its MCP base
            wx, wy = pts[0]
            mx, my = pts[mcp]
            factor = 0.7
            pts[idx][0] = mx + (wx - mx) * 0.3
            pts[idx][1] = my + (wy - my) * 0.15 + 0.05

    if gesture_data.get("thumb_in", False):
        # Tuck thumb in
        pts[3][0] = pts[2][0] + 0.04
        pts[3][1] = pts[2][1] + 0.08
        pts[4][0] = pts[3][0] + 0.03
        pts[4][1] = pts[3][1] + 0.06

    return pts


def draw_hand_on_canvas(canvas, pts, color, cx, cy, scale, tag_prefix="hand"):
    """Draw a hand skeleton on a tkinter canvas."""
    canvas.delete(tag_prefix)

    screen_pts = []
    for px, py in pts:
        sx = cx + (px - 0.5) * scale
        sy = cy + (py - 0.5) * scale
        screen_pts.append((sx, sy))

    # Draw connections
    for a, b in CONNECTIONS:
        x1, y1 = screen_pts[a]
        x2, y2 = screen_pts[b]
        canvas.create_line(x1, y1, x2, y2, fill=TEXT_DIM, width=2, tags=tag_prefix)

    # Draw joints
    for i, (sx, sy) in enumerate(screen_pts):
        r = 5 if i in (5, 9, 13, 17) else 3
        jcolor = color if i in (4, 8, 12, 16, 20) else TEXT_SECONDARY
        canvas.create_oval(sx-r, sy-r, sx+r, sy+r, fill=jcolor, outline="", tags=tag_prefix)


class AuraLauncher(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("AURA — Gesture Control Launcher")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)

        # Window size and centering
        w, h = 960, 680
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Remove default title bar styling
        self.overrideredirect(False)

        # Fonts
        self.title_font = tkfont.Font(family="Segoe UI", size=28, weight="bold")
        self.subtitle_font = tkfont.Font(family="Segoe UI", size=11)
        self.gesture_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.desc_font = tkfont.Font(family="Segoe UI", size=9)
        self.button_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        self.small_font = tkfont.Font(family="Segoe UI", size=8)

        self.aura_process = None
        self.selected_gesture = None
        self.gesture_keys = list(GESTURES.keys())
        self.current_gesture_idx = 0
        self.anim_phase = 0.0

        self._build_ui()
        self._start_animation()

    def _build_ui(self):
        # ── Header ──
        header = tk.Frame(self, bg=BG_DARK, height=90)
        header.pack(fill="x", padx=30, pady=(20, 0))
        header.pack_propagate(False)

        tk.Label(header, text="✦ AURA", font=self.title_font,
                 fg=ACCENT_LIGHT, bg=BG_DARK).pack(side="left")
        tk.Label(header, text="AI-powered User-hand Recognition & Automation",
                 font=self.subtitle_font, fg=TEXT_SECONDARY, bg=BG_DARK).pack(
                     side="left", padx=(15, 0), pady=(12, 0))

        # Status badge
        self.status_frame = tk.Frame(header, bg=BG_DARK)
        self.status_frame.pack(side="right", pady=(10, 0))

        # Lite mode badge
        if LITE_MODE:
            tk.Label(self.status_frame, text="⚡ Lite", font=tkfont.Font(family="Segoe UI", size=7, weight="bold"),
                     fg=BG_DARK, bg="#ffb347", padx=4, pady=1).pack(side="left", padx=(0, 8))

        self.status_dot = tk.Label(self.status_frame, text="●", font=self.desc_font,
                                    fg=TEXT_DIM, bg=BG_DARK)
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(self.status_frame, text="Ready",
                                      font=self.desc_font, fg=TEXT_DIM, bg=BG_DARK)
        self.status_label.pack(side="left", padx=(4, 0))

        # ── Divider ──
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(10, 15))

        # ── Main content area ──
        content = tk.Frame(self, bg=BG_DARK)
        content.pack(fill="both", expand=True, padx=30)

        # Left: Gesture cards (scrollable list)
        left_frame = tk.Frame(content, bg=BG_DARK, width=420)
        left_frame.pack(side="left", fill="y")
        left_frame.pack_propagate(False)

        tk.Label(left_frame, text="GESTURE CONTROLS", font=self.gesture_font,
                 fg=TEXT_SECONDARY, bg=BG_DARK).pack(anchor="w", pady=(0, 8))

        self.card_frames = []
        self.card_labels = []

        cards_container = tk.Frame(left_frame, bg=BG_DARK)
        cards_container.pack(fill="both", expand=True)

        for i, name in enumerate(self.gesture_keys):
            gesture = GESTURES[name]
            card = tk.Frame(cards_container, bg=BG_CARD, highlightbackground=BORDER,
                           highlightthickness=1, cursor="hand2")
            card.pack(fill="x", pady=2)

            inner = tk.Frame(card, bg=BG_CARD, padx=12, pady=6)
            inner.pack(fill="x")

            # Color indicator dot
            dot = tk.Label(inner, text="●", fg=gesture["color"], bg=BG_CARD,
                          font=self.desc_font)
            dot.pack(side="left", padx=(0, 8))

            # Gesture name
            name_label = tk.Label(inner, text=name.replace("\n", " — "),
                                  fg=TEXT_PRIMARY, bg=BG_CARD, font=self.gesture_font,
                                  anchor="w")
            name_label.pack(side="left", fill="x", expand=True)

            # Bind click events
            for widget in [card, inner, dot, name_label]:
                widget.bind("<Button-1>", lambda e, idx=i: self._select_gesture(idx))
                widget.bind("<Enter>", lambda e, c=card, inn=inner, d=dot, nl=name_label:
                           self._card_hover(c, inn, d, nl, True))
                widget.bind("<Leave>", lambda e, c=card, inn=inner, d=dot, nl=name_label:
                           self._card_hover(c, inn, d, nl, False))

            self.card_frames.append((card, inner, dot, name_label))

        # Right: Hand simulation canvas
        right_frame = tk.Frame(content, bg=BG_DARK)
        right_frame.pack(side="right", fill="both", expand=True, padx=(20, 0))

        # Simulation header
        self.sim_title = tk.Label(right_frame, text="Select a gesture to preview",
                                   font=self.gesture_font, fg=TEXT_SECONDARY, bg=BG_DARK)
        self.sim_title.pack(anchor="w", pady=(0, 8))

        # Canvas for hand drawing
        self.hand_canvas = tk.Canvas(right_frame, bg=BG_CARD, highlightthickness=0,
                                      width=450, height=350)
        self.hand_canvas.pack(fill="both", expand=True)

        # Draw initial idle hand
        self._draw_idle_hand()

        # Gesture description
        self.gesture_desc = tk.Label(right_frame, text="",
                                      font=self.desc_font, fg=TEXT_SECONDARY,
                                      bg=BG_DARK, justify="left", wraplength=400)
        self.gesture_desc.pack(anchor="w", pady=(10, 0))

        # ── Bottom bar ──
        bottom = tk.Frame(self, bg=BG_DARK)
        bottom.pack(fill="x", padx=30, pady=(15, 20))

        # Launch button
        self.launch_btn = tk.Canvas(bottom, width=260, height=50, bg=BG_DARK,
                                     highlightthickness=0, cursor="hand2")
        self.launch_btn.pack(side="right")
        self._draw_button(self.launch_btn, "▶  LAUNCH AURA", ACCENT, 260, 50)
        self.launch_btn.bind("<Button-1>", self._toggle_launch)
        self.launch_btn.bind("<Enter>", lambda e: self._draw_button(
            self.launch_btn, "▶  LAUNCH AURA", ACCENT_GLOW, 260, 50))
        self.launch_btn.bind("<Leave>", lambda e: self._draw_button(
            self.launch_btn, "▶  LAUNCH AURA", ACCENT, 260, 50))

        # Version info
        version_text = "AURA v4.0  •  Shared Memory IPC  •  One Euro Smoothing"
        if LITE_MODE:
            version_text += "  •  ⚡ Lite Mode"
        tk.Label(bottom, text=version_text,
                 font=self.small_font, fg=TEXT_DIM, bg=BG_DARK).pack(side="left")

        # Select first gesture by default
        self._select_gesture(0)

    def _draw_button(self, canvas, text, color, w, h):
        canvas.delete("all")
        r = 12
        # Rounded rectangle
        canvas.create_arc(0, 0, r*2, r*2, start=90, extent=90, fill=color, outline="")
        canvas.create_arc(w-r*2, 0, w, r*2, start=0, extent=90, fill=color, outline="")
        canvas.create_arc(0, h-r*2, r*2, h, start=180, extent=90, fill=color, outline="")
        canvas.create_arc(w-r*2, h-r*2, w, h, start=270, extent=90, fill=color, outline="")
        canvas.create_rectangle(r, 0, w-r, h, fill=color, outline="")
        canvas.create_rectangle(0, r, w, h-r, fill=color, outline="")
        canvas.create_text(w//2, h//2, text=text, fill="white",
                          font=self.button_font)

    def _card_hover(self, card, inner, dot, label, entering):
        bg = BG_CARD_HOVER if entering else BG_CARD
        for w in [card, inner, dot, label]:
            w.configure(bg=bg)

    def _select_gesture(self, idx):
        self.current_gesture_idx = idx
        name = self.gesture_keys[idx]
        gesture = GESTURES[name]

        # Update card highlights
        for i, (card, inner, dot, label) in enumerate(self.card_frames):
            if i == idx:
                card.configure(highlightbackground=gesture["color"], highlightthickness=2)
            else:
                card.configure(highlightbackground=BORDER, highlightthickness=1)

        # Update simulation
        self.sim_title.configure(text=name.replace("\n", " — "), fg=gesture["color"])
        self.gesture_desc.configure(text=gesture["desc"])

        # Draw the hand pose
        pts = get_hand_pose(gesture, HAND_BASE)
        cw = self.hand_canvas.winfo_width() or 450
        ch = self.hand_canvas.winfo_height() or 350
        draw_hand_on_canvas(self.hand_canvas, pts, gesture["color"],
                           cw // 2, ch // 2, min(cw, ch) * 0.8)

        # Draw gesture label on canvas
        self.hand_canvas.delete("label")
        self.hand_canvas.create_text(cw // 2, 25, text=name.replace("\n", " — "),
                                      fill=gesture["color"], font=self.gesture_font,
                                      tags="label")

    def _draw_idle_hand(self):
        pts = HAND_BASE
        cw = 450
        ch = 350
        draw_hand_on_canvas(self.hand_canvas, pts, TEXT_DIM, cw // 2, ch // 2,
                           min(cw, ch) * 0.8)

    def _start_animation(self):
        """Subtle breathing glow animation on the status dot."""
        self.anim_phase += 0.05
        brightness = int(80 + 40 * math.sin(self.anim_phase))
        color = f"#{brightness:02x}{brightness:02x}{brightness + 20:02x}"
        if not self.aura_process:
            self.status_dot.configure(fg=color)
        self.after(50, self._start_animation)

    def _toggle_launch(self, event=None):
        if self.aura_process and self.aura_process.poll() is None:
            # Stop
            self._kill_aura_process()
            self.status_dot.configure(fg=TEXT_DIM)
            self.status_label.configure(text="Ready", fg=TEXT_DIM)
            self._draw_button(self.launch_btn, "▶  LAUNCH AURA", ACCENT, 260, 50)
            self.launch_btn.bind("<Enter>", lambda e: self._draw_button(
                self.launch_btn, "▶  LAUNCH AURA", ACCENT_GLOW, 260, 50))
            self.launch_btn.bind("<Leave>", lambda e: self._draw_button(
                self.launch_btn, "▶  LAUNCH AURA", ACCENT, 260, 50))
        else:
            # Launch
            try:
                if getattr(sys, 'frozen', False):
                    # Running as compiled exe
                    cmd = [sys.executable, "--run-aura"]
                else:
                    # Running as script
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    main_py = os.path.join(script_dir, "main.py")
                    cmd = [sys.executable, main_py]

                if LITE_MODE:
                    cmd.append("--lite")

                self.aura_process = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                self.status_dot.configure(fg=GREEN)
                self.status_label.configure(text="Running", fg=GREEN)
                self._draw_button(self.launch_btn, "■  STOP AURA", RED, 260, 50)
                self.launch_btn.bind("<Enter>", lambda e: self._draw_button(
                    self.launch_btn, "■  STOP AURA", "#ff8888", 260, 50))
                self.launch_btn.bind("<Leave>", lambda e: self._draw_button(
                    self.launch_btn, "■  STOP AURA", RED, 260, 50))
                # Monitor process in background
                threading.Thread(target=self._monitor_process, daemon=True).start()
            except Exception as e:
                self.status_label.configure(text=f"Error: {e}", fg=RED)

    def _kill_aura_process(self):
        if self.aura_process:
            try:
                # Kill process tree on Windows to ensure camera/mediapipe children die
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.aura_process.pid)], creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass
            self.aura_process = None

    def _monitor_process(self):
        """Watch the AURA process and update UI if it exits."""
        if self.aura_process:
            self.aura_process.wait()
            self.after(0, self._on_process_exit)

    def _on_process_exit(self):
        self.aura_process = None
        self.status_dot.configure(fg=TEXT_DIM)
        self.status_label.configure(text="Stopped", fg=ORANGE)
        self._draw_button(self.launch_btn, "▶  LAUNCH AURA", ACCENT, 260, 50)
        self.launch_btn.bind("<Enter>", lambda e: self._draw_button(
            self.launch_btn, "▶  LAUNCH AURA", ACCENT_GLOW, 260, 50))
        self.launch_btn.bind("<Leave>", lambda e: self._draw_button(
            self.launch_btn, "▶  LAUNCH AURA", ACCENT, 260, 50))

    def destroy(self):
        self._kill_aura_process()
        super().destroy()


if __name__ == "__main__":
    app = AuraLauncher()
    app.mainloop()
