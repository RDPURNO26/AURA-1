# gesture_fsm.py
"""
AURA v3 – Two-finger control system.
MOVE = index+middle (peace sign). Drop one finger = click. Cursor freezes on drop.
CLUTCH = pinky only. LOCK = ring only. Voice typing = pinky+thumb.
"""
import logging
_log = logging.getLogger("aura.fsm")

class GestureStateMachine:
    ENGAGE_FRAMES = 3
    LCLICK_FRAMES = 3
    RCLICK_FRAMES = 3
    DBLCLICK_FRAMES = 3
    FIST_FRAMES = 3
    DRAG_HOLD = 10
    PEACE_RESUME = 2
    SCROLL_ENTER = 4
    SCROLL_EXIT = 4
    ZOOM_ENTER = 4
    ZOOM_EXIT = 4
    CLUTCH_FRAMES = 6
    CLUTCH_RESUME = 3
    LOCK_FRAMES = 6
    LOCK_EXIT = 5
    VOLUME_FRAMES = 4
    VOLUME_EXIT = 4
    VOICE_FRAMES = 6
    NO_HAND_MAX = 15
    SCROLL_DEADZONE = 0.05
    SCROLL_SLOW_RATE = 10
    SCROLL_MED_RATE = 5
    SCROLL_FAST_RATE = 2

    def __init__(self):
        self.state = "IDLE"
        self.action = None
        self.no_hand = 0
        self._reset()

    def _reset(self):
        self._engage = 0
        self._lclick = 0
        self._rclick = 0
        self._dblclick = 0
        self._fist = 0
        self._drag_count = 0
        self._peace = 0
        self._scroll_enter = 0
        self._scroll_exit = 0
        self._scroll_motion = 0
        self._zoom_enter = 0
        self._zoom_exit = 0
        self._zoom_motion = 0
        self._clutch = 0
        self._clutch_resume = 0
        self._lock = 0
        self._lock_exit = 0
        self._vol = 0
        self._vol_exit = 0
        self._vol_motion = 0
        self._voice = 0
        self._voice_cd = False
        self._click_cd = False

    def _go(self, s):
        if s != self.state:
            _log.info("%s -> %s", self.state, s)
            self.state = s
            self._reset()

    def _out(self):
        return {"state": self.state, "action": self.action}

    def update(self, inputs):
        self.action = None
        if inputs is None:
            self.no_hand += 1
            if self.no_hand >= self.NO_HAND_MAX:
                self._go("IDLE")
            return self._out()
        self.no_hand = 0

        p = inputs.get("is_peace", False)
        f = inputs.get("is_fist", False)
        ro = inputs.get("is_ring_only", False)
        io = inputs.get("is_index_only", False)
        mo = inputs.get("is_middle_only", False)
        t3 = inputs.get("is_three", False)
        t4 = inputs.get("is_four", False)
        pk = inputs.get("is_pinky_only", False)
        db = inputs.get("is_dblclick", False)
        to = inputs.get("is_thumb_only", False)
        cy = float(inputs.get("hand_cy", 0.5))

        s = self.state

        if s == "IDLE":
            if p:
                self._engage += 1
                if self._engage >= self.ENGAGE_FRAMES:
                    self._go("MOVE")
            else:
                self._engage = 0

        elif s == "MOVE":
            self.action = "MOVE"

            # Double click: index+middle+thumb (fire once only)
            if db and not self._click_cd:
                self._dblclick += 1
                self._lclick = 0; self._rclick = 0; self._fist = 0
                self._scroll_enter = 0; self._zoom_enter = 0; self._clutch = 0
                if self._dblclick >= self.DBLCLICK_FRAMES:
                    self.action = "DOUBLE_CLICK"
                    self._click_cd = True
                return self._out()
            self._dblclick = 0

            # Voice typing: thumb only toggle
            if to:
                if not self._voice_cd:
                    self._voice += 1
                    if self._voice >= self.VOICE_FRAMES:
                        self.action = "VOICE_TOGGLE"
                        self._voice_cd = True
                return self._out()
            self._voice = 0
            self._voice_cd = False

            # Left click: drop index (middle stays)
            if mo and not self._click_cd:
                self._lclick += 1
                self._rclick = 0; self._fist = 0
                self._scroll_enter = 0; self._zoom_enter = 0; self._clutch = 0
                if self._lclick >= self.LCLICK_FRAMES:
                    self.action = "LEFT_CLICK"
                    self._click_cd = True
                return self._out()
            self._lclick = 0

            # Right click: drop middle (index stays)
            if io and not self._click_cd:
                self._rclick += 1
                self._lclick = 0; self._fist = 0
                self._scroll_enter = 0; self._zoom_enter = 0; self._clutch = 0
                if self._rclick >= self.RCLICK_FRAMES:
                    self.action = "RIGHT_CLICK"
                    self._click_cd = True
                return self._out()
            self._rclick = 0

            # Fist: drag
            if f:
                self._fist += 1
                self._scroll_enter = 0; self._zoom_enter = 0; self._clutch = 0
                if self._fist >= self.FIST_FRAMES:
                    self._go("CLICKING")
                return self._out()
            self._fist = 0

            # Pinky only: clutch
            if pk:
                self._clutch += 1
                self._lock = 0; self._scroll_enter = 0; self._zoom_enter = 0
                if self._clutch >= self.CLUTCH_FRAMES:
                    self._go("CLUTCH")
                return self._out()
            self._clutch = 0

            # Ring only: volume control
            if ro:
                self._vol += 1
                self._scroll_enter = 0; self._zoom_enter = 0
                if self._vol >= self.VOLUME_FRAMES:
                    self._go("VOLUME")
                return self._out()
            self._vol = 0

            # 4 fingers: zoom (check before 3 fingers)
            if t4:
                self._zoom_enter += 1
                self._scroll_enter = 0
                if self._zoom_enter >= self.ZOOM_ENTER:
                    self._go("ZOOMING")
                return self._out()
            self._zoom_enter = 0

            # 3 fingers: scroll
            if t3:
                self._scroll_enter += 1
                if self._scroll_enter >= self.SCROLL_ENTER:
                    self._go("SCROLLING")
                return self._out()
            self._scroll_enter = 0

            # Peace sign: clear cooldown (only pure peace, not dblclick pose)
            if p and not db:
                self._click_cd = False

        elif s == "CLICKING":
            self._drag_count += 1
            if p:
                self._peace += 1
                if self._peace >= self.PEACE_RESUME:
                    self._go("MOVE")
                    return self._out()
            else:
                self._peace = 0
            if self._drag_count >= self.DRAG_HOLD:
                self.action = "DRAG_START"
                self._go("DRAGGING")

        elif s == "DRAGGING":
            self.action = "DRAGGING"
            if p:
                self._peace += 1
                if self._peace >= self.PEACE_RESUME:
                    self.action = "DRAG_END"
                    self._go("MOVE")
            else:
                self._peace = 0

        elif s == "SCROLLING":
            if not t3:
                self._scroll_exit += 1
                if self._scroll_exit >= self.SCROLL_EXIT:
                    self._go("MOVE")
                return self._out()
            self._scroll_exit = 0
            # Position-based scroll: hand Y relative to center
            offset = cy - 0.5
            abs_off = abs(offset)
            if abs_off < self.SCROLL_DEADZONE:
                self._scroll_motion = 0
            else:
                rate = (self.SCROLL_FAST_RATE if abs_off >= 0.25
                        else self.SCROLL_MED_RATE if abs_off >= 0.15
                        else self.SCROLL_SLOW_RATE)
                self._scroll_motion += 1
                if self._scroll_motion >= rate:
                    self._scroll_motion = 0
                    self.action = "SCROLL_DOWN" if offset > 0 else "SCROLL_UP"

        elif s == "ZOOMING":
            if not t4:
                self._zoom_exit += 1
                if self._zoom_exit >= self.ZOOM_EXIT:
                    self._go("MOVE")
                return self._out()
            self._zoom_exit = 0
            # Position-based zoom: hand Y relative to center
            offset = cy - 0.5
            abs_off = abs(offset)
            if abs_off < self.SCROLL_DEADZONE:
                self._zoom_motion = 0
            else:
                rate = (self.SCROLL_FAST_RATE if abs_off >= 0.25
                        else self.SCROLL_MED_RATE if abs_off >= 0.15
                        else self.SCROLL_SLOW_RATE)
                self._zoom_motion += 1
                if self._zoom_motion >= rate:
                    self._zoom_motion = 0
                    self.action = "ZOOM_IN" if offset < 0 else "ZOOM_OUT"

        elif s == "CLUTCH":
            self.action = "CLUTCH"
            if p:
                self._clutch_resume += 1
                if self._clutch_resume >= self.CLUTCH_RESUME:
                    self.action = "CLUTCH_RESUME"
                    self._go("MOVE")
            else:
                self._clutch_resume = 0

        elif s == "VOLUME":
            if not ro:
                self._vol_exit += 1
                if self._vol_exit >= self.VOLUME_EXIT:
                    self._go("MOVE")
                return self._out()
            self._vol_exit = 0
            # Position-based volume: hand Y relative to center
            offset = cy - 0.5
            abs_off = abs(offset)
            if abs_off < self.SCROLL_DEADZONE:
                self._vol_motion = 0
            else:
                rate = (self.SCROLL_FAST_RATE if abs_off >= 0.25
                        else self.SCROLL_MED_RATE if abs_off >= 0.15
                        else self.SCROLL_SLOW_RATE)
                self._vol_motion += 1
                if self._vol_motion >= rate:
                    self._vol_motion = 0
                    self.action = "VOL_UP" if offset < 0 else "VOL_DOWN"

        return self._out()
