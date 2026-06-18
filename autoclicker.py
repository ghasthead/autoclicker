"""
AutoClicker Pro — Cross-platform autoclicker with macro recorder
Requirements:
  Windows: pip install keyboard mouse pyautogui
  macOS:   pip install keyboard mouse pyautogui
  Linux:   pip install keyboard mouse pyautogui python-xlib
"""

import tkinter as tk
from tkinter import simpledialog, messagebox
import threading
import time
import json
import os
import sys
import copy
import platform

# Imported at module level (not just inside FloatingOrb) so PyInstaller's
# static analysis reliably bundles these submodules into the .exe.
try:
    from PIL import Image, ImageDraw, ImageTk
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False

_OS = platform.system()  # "Windows", "Darwin", "Linux"

# ── Cross-platform mouse layer ────────────────────────────────────────────────
if _OS == "Windows":
    import ctypes
    import ctypes.wintypes

    INPUT_MOUSE            = 0
    MOUSEEVENTF_LEFTDOWN   = 0x0002
    MOUSEEVENTF_LEFTUP     = 0x0004
    MOUSEEVENTF_RIGHTDOWN  = 0x0008
    MOUSEEVENTF_RIGHTUP    = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP   = 0x0040
    MOUSEEVENTF_MOVE       = 0x0001
    MOUSEEVENTF_ABSOLUTE   = 0x8000

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.wintypes.LONG), ("dy", ctypes.wintypes.LONG),
                    ("mouseData", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
                    ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _IU(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _IU)]

    _send     = ctypes.windll.user32.SendInput
    _screen_w = ctypes.windll.user32.GetSystemMetrics(0)
    _screen_h = ctypes.windll.user32.GetSystemMetrics(1)

    _BTN_FLAGS = {
        "left":   (MOUSEEVENTF_LEFTDOWN,   MOUSEEVENTF_LEFTUP),
        "right":  (MOUSEEVENTF_RIGHTDOWN,  MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }

    def _mouse_down(button="left"):
        d, _ = _BTN_FLAGS[button]
        inp = (INPUT*1)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(dwFlags=d))))
        _send(1, inp, ctypes.sizeof(INPUT))

    def _mouse_up(button="left"):
        _, u = _BTN_FLAGS[button]
        inp = (INPUT*1)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(dwFlags=u))))
        _send(1, inp, ctypes.sizeof(INPUT))

    def _move_to(x, y):
        ax = int(x * 65535 / _screen_w)
        ay = int(y * 65535 / _screen_h)
        inp = (INPUT*1)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(
            dx=ax, dy=ay, dwFlags=MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE))))
        _send(1, inp, ctypes.sizeof(INPUT))

elif _OS == "Darwin":
    # macOS — uses Quartz (built-in) for low-latency clicks
    try:
        import Quartz
        from Quartz import (CGEventCreateMouseEvent, CGEventPost,
                            kCGEventMouseMoved,
                            kCGEventLeftMouseDown, kCGEventLeftMouseUp,
                            kCGEventRightMouseDown, kCGEventRightMouseUp,
                            kCGEventOtherMouseDown, kCGEventOtherMouseUp,
                            kCGMouseButtonLeft, kCGMouseButtonRight,
                            kCGMouseButtonCenter, kCGHIDEventTap)
        _USE_QUARTZ = True
    except ImportError:
        _USE_QUARTZ = False
        import pyautogui
        pyautogui.PAUSE = 0
        pyautogui.FAILSAFE = False

    _MAC_BTN_DOWN = {
        "left":   (kCGEventLeftMouseDown,   kCGMouseButtonLeft)   if "_USE_QUARTZ" and _USE_QUARTZ else None,
        "right":  (kCGEventRightMouseDown,  kCGMouseButtonRight)  if "_USE_QUARTZ" and _USE_QUARTZ else None,
        "middle": (kCGEventOtherMouseDown,  kCGMouseButtonCenter) if "_USE_QUARTZ" and _USE_QUARTZ else None,
    }
    _MAC_BTN_UP = {
        "left":   (kCGEventLeftMouseUp,   kCGMouseButtonLeft)   if "_USE_QUARTZ" and _USE_QUARTZ else None,
        "right":  (kCGEventRightMouseUp,  kCGMouseButtonRight)  if "_USE_QUARTZ" and _USE_QUARTZ else None,
        "middle": (kCGEventOtherMouseUp,  kCGMouseButtonCenter) if "_USE_QUARTZ" and _USE_QUARTZ else None,
    }

    def _get_mouse_pos():
        try:
            import Quartz
            pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            return int(pos.x), int(pos.y)
        except Exception:
            import pyautogui
            return pyautogui.position()

    def _mouse_down(button="left"):
        if _USE_QUARTZ:
            x, y = _get_mouse_pos()
            ev_type, btn_num = _MAC_BTN_DOWN[button]
            ev = CGEventCreateMouseEvent(None, ev_type, (x, y), btn_num)
            CGEventPost(kCGHIDEventTap, ev)
        else:
            btn = {"left":"left","right":"right","middle":"middle"}[button]
            pyautogui.mouseDown(button=btn)

    def _mouse_up(button="left"):
        if _USE_QUARTZ:
            x, y = _get_mouse_pos()
            ev_type, btn_num = _MAC_BTN_UP[button]
            ev = CGEventCreateMouseEvent(None, ev_type, (x, y), btn_num)
            CGEventPost(kCGHIDEventTap, ev)
        else:
            btn = {"left":"left","right":"right","middle":"middle"}[button]
            pyautogui.mouseUp(button=btn)

    def _move_to(x, y):
        if _USE_QUARTZ:
            ev = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), kCGMouseButtonLeft)
            CGEventPost(kCGHIDEventTap, ev)
        else:
            pyautogui.moveTo(x, y)

else:
    # Linux — uses pyautogui (X11/Wayland via xdotool fallback)
    import pyautogui
    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = False

    def _mouse_down(button="left"):
        pyautogui.mouseDown(button=button)

    def _mouse_up(button="left"):
        pyautogui.mouseUp(button=button)

    def _move_to(x, y):
        pyautogui.moveTo(x, y)


def _do_click(button="left"):
    _mouse_down(button)
    _mouse_up(button)

import keyboard
import mouse

# ── Theme (mutable — changed by the theme tab) ───────────────────────────────
THEME = {
    "BG":      "#0b0d14",
    "BORDER":  "#1a2236",
    "ACCENT":  "#1e6fff",
    "ACCENT2": "#ff3c6e",
    "TEXT":    "#dde4f5",
    "SUBTEXT": "#4a5880",
    "SUCCESS": "#00d48a",
    "BTN_BG":  "#111827",
    "BTN_HOV": "#172040",
    "SEL_BG":  "#0d1f40",
    "WARN":    "#ffaa00",
}

def T(key):
    return THEME[key]

# Shorthand globals (updated by apply_theme)
def _g(): return THEME
BG      = THEME["BG"]
BORDER  = THEME["BORDER"]
ACCENT  = THEME["ACCENT"]
ACCENT2 = THEME["ACCENT2"]
TEXT    = THEME["TEXT"]
SUBTEXT = THEME["SUBTEXT"]
SUCCESS = THEME["SUCCESS"]
BTN_BG  = THEME["BTN_BG"]
BTN_HOV = THEME["BTN_HOV"]
SEL_BG  = THEME["SEL_BG"]
WARN    = THEME["WARN"]

THEMES_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "theme.json")

MACROS_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "macros.json")

# ── Autoclicker engine ───────────────────────────────────────────────────────
class AutoClicker:
    def __init__(self):
        self.running     = False
        self.thread      = None
        self.total       = 0
        self.interval_ms = 100.0
        self.hold_ms     = 0.0    # 0 = instant click, >0 = hold duration
        self.button      = "left"
        self.limit       = 0
        self.on_stop     = None
        # Click-at-position
        self.cap_enabled = False
        self.cap_x       = None
        self.cap_y       = None

    def _loop(self):
        err = 0.0
        while self.running:
            if self.limit and self.total >= self.limit:
                self.running = False
                if self.on_stop: self.on_stop()
                break
            t0 = time.perf_counter()
            if self.cap_enabled and self.cap_x is not None:
                # Get current position, move to target, click, return
                try:
                    import ctypes as _ct
                    class _PT(_ct.Structure):
                        _fields_ = [("x",_ct.c_long),("y",_ct.c_long)]
                    pt = _PT()
                    _ct.windll.user32.GetCursorPos(_ct.byref(pt))
                    orig_x, orig_y = pt.x, pt.y
                except Exception:
                    orig_x, orig_y = None, None
                _move_to(self.cap_x, self.cap_y)
                time.sleep(0.01)  # brief settle
                if self.hold_ms > 0:
                    _mouse_down(self.button)
                    time.sleep(self.hold_ms / 1000.0)
                    _mouse_up(self.button)
                else:
                    _do_click(self.button)
                if orig_x is not None:
                    _move_to(orig_x, orig_y)
            elif self.hold_ms > 0:
                _mouse_down(self.button)
                time.sleep(self.hold_ms / 1000.0)
                _mouse_up(self.button)
            else:
                _do_click(self.button)
            self.total += 1
            elapsed = (time.perf_counter()-t0)*1000
            # interval must be >= hold_ms to avoid overlapping clicks
            effective_interval = max(self.interval_ms, self.hold_ms)
            wait = max(0.0, effective_interval - elapsed - err)
            t1 = time.perf_counter()
            if wait > 0: time.sleep(wait/1000)
            err = (elapsed + (time.perf_counter()-t1)*1000) - effective_interval

    def start(self):
        if self.running: return
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):  self.running = False
    def reset(self): self.total = 0

# ── Macro engine ─────────────────────────────────────────────────────────────
class MacroEngine:
    def __init__(self):
        self.recording   = False
        self.playing     = False
        self._events     = []
        self._mouse_hook = None
        self._key_hook   = None
        self._t0         = 0.0
        self.play_thread = None
        self.on_done     = None

    def start_record(self):
        if self.recording or self.playing: return
        self._events = []
        self._t0     = time.perf_counter()
        self.recording = True
        self._mouse_hook = mouse.hook(self._on_mouse)
        self._key_hook   = keyboard.hook(self._on_key)

    def stop_record(self):
        if not self.recording: return
        self.recording = False
        # Only unhook OUR hooks — do NOT call unhook_all() as that kills hotkeys
        try: mouse.unhook(self._mouse_hook)
        except Exception: pass
        try: keyboard.unhook(self._key_hook)
        except Exception: pass
        self._mouse_hook = None
        self._key_hook   = None

    def _on_mouse(self, ev):
        t = (time.perf_counter()-self._t0)*1000
        if isinstance(ev, mouse.MoveEvent):
            self._events.append({"type":"move","x":ev.x,"y":ev.y,"t":t})
        elif isinstance(ev, mouse.ButtonEvent):
            self._events.append({"type":"click","button":ev.button,
                                  "event_type":ev.event_type,"x":ev.x,"y":ev.y,"t":t})
        elif isinstance(ev, mouse.WheelEvent):
            self._events.append({"type":"scroll","delta":ev.delta,"t":t})

    def _on_key(self, ev):
        t = (time.perf_counter()-self._t0)*1000
        self._events.append({"type":"key","name":ev.name,
                              "event_type":ev.event_type,"t":t})

    def get_events(self): return copy.deepcopy(self._events)

    def play(self, events, speed=1.0, repeat=1, infinite=False, on_done=None):
        if self.playing: return
        self.playing = True
        self.on_done = on_done
        self.play_thread = threading.Thread(
            target=self._play_loop,
            args=(events, speed, repeat, infinite), daemon=True)
        self.play_thread.start()

    def _play_loop(self, events, speed, repeat, infinite):
        count = 0
        while self.playing and (infinite or count < repeat):
            if not events:
                break
            prev_t = 0.0
            for ev in events:
                if not self.playing: break
                gap = (ev["t"] - prev_t) / max(speed, 0.01)
                if gap > 0: time.sleep(gap/1000)
                prev_t = ev["t"]
                try:
                    if ev["type"] == "move":
                        _move_to(ev["x"], ev["y"])
                    elif ev["type"] == "click":
                        _move_to(ev["x"], ev["y"])
                        btn = ev.get("button", "left")
                        if ev["event_type"] == "down":
                            _mouse_down(btn)
                        elif ev["event_type"] == "up":
                            _mouse_up(btn)
                    elif ev["type"] == "key":
                        if ev["event_type"] == "down":
                            keyboard.press(ev["name"])
                        elif ev["event_type"] == "up":
                            keyboard.release(ev["name"])
                except Exception:
                    pass
            count += 1
        self.playing = False
        if self.on_done: self.on_done()

    def stop(self):
        self.playing = False

# ── Colour helpers ────────────────────────────────────────────────────────────
def _clamp(v): return max(0, min(255, v))

def _hex_to_rgb(h):
    h = (h or "#888888").lstrip("#")
    if len(h) == 3: h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) < 6:  h = h.ljust(6, "0")
    return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)

def _rgb_to_hex(r,g,b):
    return "#{:02x}{:02x}{:02x}".format(_clamp(r),_clamp(g),_clamp(b))

def _lighten(c, amt=20):
    try:
        r,g,b = _hex_to_rgb(c)
        return _rgb_to_hex(r+amt, g+amt, b+amt)
    except Exception:
        return c or "#888888"

def _darken(c, amt=20):
    try:
        r,g,b = _hex_to_rgb(c)
        return _rgb_to_hex(r-amt, g-amt, b-amt)
    except Exception:
        return c or "#222222"

def _blend(c1, c2, t):
    try:
        r1,g1,b1 = _hex_to_rgb(c1)
        r2,g2,b2 = _hex_to_rgb(c2)
        return _rgb_to_hex(int(r1+(r2-r1)*t), int(g1+(g2-g1)*t), int(b1+(b2-b1)*t))
    except Exception:
        return c1 or c2 or "#888888"

def _apply_theme():
    """Copy THEME dict values into module globals."""
    global BG,BORDER,ACCENT,ACCENT2,TEXT,SUBTEXT,SUCCESS,BTN_BG,BTN_HOV,SEL_BG,WARN
    BG=THEME["BG"]; BORDER=THEME["BORDER"]; ACCENT=THEME["ACCENT"]
    ACCENT2=THEME["ACCENT2"]; TEXT=THEME["TEXT"]; SUBTEXT=THEME["SUBTEXT"]
    SUCCESS=THEME["SUCCESS"]; BTN_BG=THEME["BTN_BG"]; BTN_HOV=THEME["BTN_HOV"]
    SEL_BG=THEME["SEL_BG"]; WARN=THEME["WARN"]

# ── Custom rounded widget library ─────────────────────────────────────────────

def _rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Draw a rounded rectangle on a canvas."""
    r = min(r, (x2-x1)//2, (y2-y1)//2)
    pts = [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
        x1+r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundedButton(tk.Canvas):
    """A canvas-based button with rounded corners, hover expand, and press animation."""
    RADIUS   = 10
    PAD_X    = 18
    PAD_Y    = 8
    EXPAND   = 3       # px to grow on each side when hovered
    STEPS    = 8       # animation frames
    FRAME_MS = 12

    def __init__(self, parent, text, cmd, color=None, textcolor=None,
                 font=("Segoe UI", 10, "bold"), radius=None, padx=None, pady=None, **kw):
        self._base_color  = color    or THEME.get("ACCENT","#1e6fff")
        self._text_color  = textcolor or THEME.get("TEXT","#dde4f5")
        self._cmd         = cmd
        self._text        = text
        self._font        = font
        self._radius      = radius if radius is not None else self.RADIUS
        self._padx        = padx   if padx   is not None else self.PAD_X
        self._pady        = pady   if pady   is not None else self.PAD_Y
        self._hover       = False
        self._pressed     = False
        self._expand      = 0.0    # current expansion (0..EXPAND)
        self._anim_id     = None
        self._parent_bg   = THEME.get("BG","#0b0d14")

        # Measure text to size canvas
        tmp = tk.Label(parent, text=text, font=font)
        tw  = tmp.winfo_reqwidth()
        th  = tmp.winfo_reqheight()
        tmp.destroy()
        self._tw = tw
        self._th = th
        self._bw = tw + self._padx * 2 + self.EXPAND * 2
        self._bh = th + self._pady * 2 + self.EXPAND * 2

        super().__init__(parent, width=self._bw, height=self._bh,
                         bg=self._parent_bg, highlightthickness=0,
                         cursor="hand2", **kw)

        self._draw(0.0)

        self.bind("<Enter>",            self._on_enter)
        self.bind("<Leave>",            self._on_leave)
        self.bind("<ButtonPress-1>",    self._on_press)
        self.bind("<ButtonRelease-1>",  self._on_release)

    def _cur_color(self, expand_frac):
        if self._pressed:
            return _darken(self._base_color, 30)
        if expand_frac > 0:
            return _lighten(self._base_color, int(20 * expand_frac))
        return self._base_color

    def _draw(self, expand_frac):
        self.delete("all")
        e  = expand_frac * self.EXPAND
        bw = self._bw
        bh = self._bh
        x1 = self.EXPAND - e
        y1 = self.EXPAND - e
        x2 = bw - self.EXPAND + e
        y2 = bh - self.EXPAND + e
        col = self._cur_color(expand_frac)
        # Shadow / border
        _rounded_rect(self, x1+1, y1+2, x2+1, y2+2, self._radius,
                      fill=_darken(col, 40), outline="")
        # Main body
        _rounded_rect(self, x1, y1, x2, y2, self._radius,
                      fill=col, outline=_lighten(col, 15), width=1)
        # Text
        cx = bw / 2
        cy = bh / 2
        # Slight text color lighten on hover
        tc = self._text_color
        if expand_frac > 0:
            try:
                r,g,b = _hex_to_rgb(tc)
                if r+g+b > 200:
                    tc = _lighten(tc, int(15 * expand_frac))
            except Exception:
                pass
        self.create_text(cx, cy, text=self._text, fill=tc,
                         font=self._font, anchor="center")

    def _animate(self, target):
        if self._anim_id:
            self.after_cancel(self._anim_id)
        step = [self._expand]
        def tick():
            diff = target - step[0]
            if abs(diff) < 0.05:
                step[0] = target
            else:
                step[0] += diff * 0.35
            self._expand = step[0]
            self._draw(self._expand)
            if abs(target - step[0]) > 0.02:
                self._anim_id = self.after(self.FRAME_MS, tick)
        tick()

    def _on_enter(self, e):
        self._hover = True
        self._animate(1.0)

    def _on_leave(self, e):
        self._hover = False
        self._pressed = False
        self._animate(0.0)

    def _on_press(self, e):
        self._pressed = True
        self._draw(self._expand)

    def _on_release(self, e):
        self._pressed = False
        self._draw(self._expand)
        if self._hover:
            self._cmd()

    def config_text(self, text):
        self._text = text
        self._draw(self._expand)

    def config_color(self, color):
        self._base_color = color
        self._draw(self._expand)

    # Allow .config(text=...) like a normal widget
    def config(self, **kw):
        # Intercept all non-Canvas options before passing to super
        if "text"      in kw: self.config_text(kw.pop("text"))
        if "bg"        in kw: self._base_color = kw.pop("bg"); self._draw(self._expand)
        if "fg"        in kw: self._text_color  = kw.pop("fg"); self._draw(self._expand)
        if "font"      in kw: self._font        = kw.pop("font"); self._draw(self._expand)
        if "command"   in kw: self._cmd         = kw.pop("command")
        if "state"     in kw: kw.pop("state")   # ignore — Canvas has no state
        if "padx"      in kw: kw.pop("padx")
        if "pady"      in kw: kw.pop("pady")
        if "relief"    in kw: kw.pop("relief")
        if "activebackground" in kw: kw.pop("activebackground")
        if "activeforeground" in kw: kw.pop("activeforeground")
        if "disabledforeground" in kw: kw.pop("disabledforeground")
        if kw:
            try: super().config(**kw)
            except Exception: pass   # silently drop any remaining unsupported opts

    def cget(self, key):
        if key == "text": return self._text
        if key == "bg":   return self._base_color
        if key == "fg":   return self._text_color
        try: return super().cget(key)
        except Exception: return ""


class RoundedEntry(tk.Frame):
    """
    A text entry with a rounded-looking border achieved via a
    highlight frame — fully compatible with all tkinter versions.
    """
    RADIUS = 8   # kept for API compat, styling via highlight

    def __init__(self, parent, textvariable=None, width=120,
                 font=("Segoe UI", 11, "bold"), **kw):
        bg  = THEME.get("BTN_BG","#111827")
        fg  = THEME.get("TEXT","#dde4f5")
        acc = THEME.get("ACCENT","#1e6fff")
        bdr = THEME.get("BORDER","#1a2236")
        pbg = THEME.get("BG","#0b0d14")

        # Outer frame acts as the border ring
        super().__init__(parent, bg=bdr, highlightthickness=0)

        # Inner frame gives the fill colour
        inner = tk.Frame(self, bg=bg)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        self._var = textvariable or tk.StringVar()
        # width in chars: approximate from pixel width
        char_w = max(4, width // 9)
        self._entry = tk.Entry(inner, textvariable=self._var,
                               font=font, bg=bg, fg=fg,
                               insertbackground=acc, relief="flat",
                               bd=0, highlightthickness=0,
                               justify="center",
                               width=char_w)
        self._entry.pack(fill="x", expand=True, padx=4, pady=3)

        self._bg    = bg
        self._acc   = acc
        self._bdr   = bdr
        self._inner = inner
        self._focused = False

        self._entry.bind("<FocusIn>",  self._on_focus)
        self._entry.bind("<FocusOut>", self._on_blur)

        if textvariable is None:
            self._entry.config(textvariable=self._var)

    def _on_focus(self, e):
        self._focused = True
        self.config(bg=THEME.get("ACCENT","#1e6fff"))

    def _on_blur(self, e):
        self._focused = False
        self.config(bg=THEME.get("BORDER","#1a2236"))

    def get(self):            return self._var.get()
    def set(self, v):         self._var.set(v)
    def bind(self, seq, fn):  self._entry.bind(seq, fn)

    def config(self, **kw):
        if "state" in kw:
            self._entry.config(state=kw.pop("state"))
        if "textvariable" in kw:
            self._var = kw.pop("textvariable")
            self._entry.config(textvariable=self._var)
        if kw:
            super().config(**kw)

    def cget(self, key):
        try: return self._entry.cget(key)
        except Exception: return super().cget(key)


class RoundedCheckbox(tk.Canvas):
    """A rounded toggle checkbox."""
    SIZE   = 20
    RADIUS = 6

    def __init__(self, parent, variable=None, text="", command=None,
                 font=("Segoe UI", 10), **kw):
        # Try to get parent's background colour for seamless blending
        try:
            pbg = parent.cget("bg")
        except Exception:
            pbg = THEME.get("BTN_BG","#111827")
        self._var  = variable or tk.BooleanVar()
        self._text = text
        self._cmd  = command
        self._font = font
        self._pbg  = pbg

        # Measure text
        tmp = tk.Label(parent, text=text, font=font)
        tw  = tmp.winfo_reqwidth() + 4
        th  = tmp.winfo_reqheight()
        tmp.destroy()
        w = self.SIZE + 8 + tw if text else self.SIZE
        h = max(self.SIZE, th)

        # Fixed height: SIZE + 4px padding ensures circle never clips
        w = w + 4
        h = max(self.SIZE + 6, h + 4)
        super().__init__(parent, width=w, height=h,
                         bg=pbg, highlightthickness=0, cursor="hand2", **kw)
        # Draw immediately so it's correct before first resize event
        self.after(0, self._draw)

        self._draw()
        self.bind("<ButtonRelease-1>", self._toggle)
        self._var.trace_add("write", lambda *_: self._draw())

    def _draw(self):
        self.delete("all")
        s  = self.SIZE
        ch = self.winfo_height()
        if ch < s: ch = s + 6   # not yet laid out — use design height
        y0 = (ch - s) // 2
        checked = self._var.get()
        acc = THEME.get("ACCENT","#1e6fff")
        bg  = THEME.get("BTN_BG","#111827")
        bdr = THEME.get("BORDER","#1a2236")
        tc  = THEME.get("TEXT","#dde4f5")

        box_fill    = acc if checked else bg
        box_outline = _lighten(acc,20) if checked else bdr
        # Draw circle with 2px inset so outline is never clipped
        x0, y0b = 3, y0 + 2
        x1, y1b = s - 1, y0 + s - 2
        self.create_oval(x0, y0b, x1, y1b,
                         fill=box_fill, outline=box_outline, width=2)
        if checked:
            cx = s // 2
            cy = y0 + s // 2
            dr = max(2, s // 5)
            self.create_oval(cx-dr, cy-dr, cx+dr, cy+dr,
                             fill="#fff", outline="")
        if self._text:
            self.create_text(s + 10, ch//2, text=self._text,
                             fill=tc, font=self._font, anchor="w")

    def _toggle(self, e):
        self._var.set(not self._var.get())
        if self._cmd: self._cmd()

    def config(self, **kw):
        if "text" in kw:    self._text = kw.pop("text")
        if "command" in kw: self._cmd  = kw.pop("command")
        if "variable" in kw:
            self._var = kw.pop("variable")
            self._var.trace_add("write", lambda *_: self._draw())
        super().config(**kw)
        self._draw()

# ── Floating orb window ───────────────────────────────────────────────────────
class FloatingOrb(tk.Toplevel):
    ORB_R = 28
    SIZE  = 56

    def __init__(self, app):
        super().__init__(app)
        self.app          = app
        self._drag_x      = 0
        self._drag_y      = 0
        self._expanded    = False
        self._hover       = False
        self._glow        = 0.0
        self._poll_id     = None
        self._collapse_id = None
        self._photo       = None   # keep reference alive (PhotoImage gc)
        self._last_glow_drawn = -1.0

        d = self.SIZE
        # Magic colour key for transparency around the circle. A HARD
        # (non-anti-aliased) silhouette edge is used so no pixel is ever
        # partially transparent — every pixel is either fully the key
        # colour (made invisible) or fully opaque artwork. That removes
        # the fringe that soft/anti-aliased edges caused previously.
        self._transparent_key = "#fe01fe"

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{d}x{d}+80+80")
        self.resizable(False, False)
        self.configure(bg=self._transparent_key)
        try:
            self.attributes("-transparentcolor", self._transparent_key)
        except Exception:
            pass   # not supported on this platform — falls back to opaque square

        self._canvas = tk.Canvas(self, width=d, height=d,
                                  bg=self._transparent_key,
                                  highlightthickness=0)
        self._canvas.pack()
        self._draw_orb(force=True)

        self._canvas.bind("<ButtonPress-1>",    self._drag_start)
        self._canvas.bind("<B1-Motion>",        self._drag_move)
        self._canvas.bind("<Enter>",            self._on_enter)
        self._canvas.bind("<Leave>",            self._on_leave)
        self.bind("<Enter>",                    self._on_enter)
        self.bind("<Leave>",                    self._on_leave)

        self._start_poll()

    # ── Drawing — "Echo" cursor + ripple mark (matches app icon) ───────────────
    # Rendered at high resolution via PIL then downscaled for crisp,
    # anti-aliased edges (Tkinter Canvas alone cannot anti-alias).
    def _draw_orb(self, force=False):
        # Throttle redraws to glow changes only (avoid needless re-render)
        g = round(self._glow, 3)
        if not force and g == self._last_glow_drawn:
            return
        self._last_glow_drawn = g

        if not _PIL_AVAILABLE:
            self._draw_orb_fallback()
            return

        SS   = 8                      # supersample factor
        d    = self.SIZE
        S    = d * SS
        r    = S // 2
        acc  = _hex_to_rgb(THEME.get("ACCENT","#1e6fff"))
        bgh  = THEME.get("BG","#0b0d14")
        bg   = _hex_to_rgb(bgh)

        def lerp(c1, c2, t):
            return tuple(int(c1[i] + (c2[i]-c1[i]) * t) for i in range(3))
        def lighten(c, amt):
            return tuple(min(255, c[i] + amt) for i in range(3))
        def darken(c, amt):
            return tuple(max(0, c[i] - amt) for i in range(3))

        # Transparent canvas (RGBA) — only the circle itself gets painted
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        dr  = ImageDraw.Draw(img)

        pad = S // 18

        # Drop shadow (soft, offset slightly down-right, only inside circle area)
        shadow_off = S // 70
        dr.ellipse([pad+shadow_off, pad+shadow_off*2, S-pad+shadow_off, S-pad+shadow_off],
                   fill=darken(bg, 18) + (140,))

        # Main circle body + border (border brightens with glow)
        border_col = lighten(acc, int(g * 60))
        border_w   = max(2, S // 38)
        dr.ellipse([pad, pad, S-pad, S-pad], fill=bg + (255,), outline=border_col + (255,), width=border_w)

        # Ripple arcs emanating from the cursor tip (upper-left of centre)
        tip_x = r - S * 0.12
        tip_y = r - S * 0.12
        ring_count = 3
        max_r = S * 0.30
        for i in range(ring_count, 0, -1):
            frac   = i / ring_count
            rr     = max_r * frac
            base_t = 0.42 + 0.13 * (ring_count - i)
            boost  = g * 0.45
            col    = lerp(bg, lighten(acc, 25), min(1.0, base_t + boost))
            width  = max(2, S // 50) + (S // 100 if i == 1 else 0) + int(g * S/40)
            bbox = [tip_x-rr, tip_y-rr, tip_x+rr, tip_y+rr]
            dr.arc(bbox, start=-15, end=105, fill=col + (255,), width=width)

        # Cursor arrow polygon, scaled and centred to balance with ripple
        scale = S * 0.36
        ox = tip_x - scale * 0.30
        oy = tip_y - scale * 0.30
        pointer = [
            (0.00,0.00),(0.00,0.78),(0.18,0.62),(0.30,0.94),
            (0.42,0.90),(0.30,0.58),(0.55,0.58),(0.00,0.00)
        ]
        pts = [(ox+px*scale, oy+py*scale) for px, py in pointer]

        # Cursor drop shadow
        shadow_pts = [(x + S*0.012, y + S*0.012) for x, y in pts]
        dr.polygon(shadow_pts, fill=darken(bg, 25) + (170,))

        # Cursor body (light fill) + crisp outline
        cursor_fill = (248, 250, 254)
        dr.polygon(pts, fill=cursor_fill + (255,))
        outline_w = max(2, S // 110)
        closed = pts + [pts[0]]
        for i in range(len(closed) - 1):
            dr.line([closed[i], closed[i+1]], fill=darken(acc, 5) + (255,), width=outline_w)

        # Small highlight facet on the cursor
        hi_pts = [(ox + 0.06*scale, oy + 0.10*scale),
                  (ox + 0.06*scale, oy + 0.45*scale),
                  (ox + 0.16*scale, oy + 0.36*scale)]
        dr.polygon(hi_pts, fill=lighten(acc, 70) + (190,))

        # Glow ring overlay on activity (drawn last, outside main border)
        if g > 0.05:
            glow_w = max(1, int(g * S/45))
            dr.ellipse([pad-2, pad-2, S-pad+2, S-pad+2],
                       outline=lighten(acc, int(g*50)) + (int(200*g),), width=glow_w)

        # Downscale with high-quality filter for crisp, non-pixelated result
        final = img.resize((d, d), Image.LANCZOS)

        # ── Hard-threshold the alpha channel ────────────────────────────────
        # The colour-key trick (-transparentcolor) can only ever hide pixels
        # that are EXACTLY the key colour. Anti-aliased / soft edges have
        # partial alpha, so after compositing they end up as a blend of key
        # colour + artwork colour — a visible fringe. Fix: snap every pixel
        # to either fully opaque (real artwork) or fully transparent (key
        # colour) with a 50% cutoff. The downscale already smoothed the
        # silhouette via supersampling, so this keeps it looking round
        # without leaving any partially-keyed pixels behind.
        r_ch, g_ch, b_ch, a_ch = final.split()
        hard_alpha = a_ch.point(lambda v: 255 if v >= 128 else 0)
        final_hard = Image.merge("RGBA", (r_ch, g_ch, b_ch, hard_alpha))

        key_rgb = _hex_to_rgb(self._transparent_key)
        backing = Image.new("RGBA", final_hard.size, key_rgb + (255,))
        composited = Image.alpha_composite(backing, final_hard).convert("RGB")

        self._photo = ImageTk.PhotoImage(composited)
        self._canvas.delete("all")
        self._canvas.create_image(d//2, d//2, image=self._photo, anchor="center")

    def _draw_orb_fallback(self):
        """Plain-canvas fallback if PIL/ImageTk is unavailable."""
        c = self._canvas
        c.delete("all")
        d = self.SIZE
        acc = THEME.get("ACCENT", "#1e6fff")
        bg  = THEME.get("BG", "#0b0d14")
        c.create_oval(2, 2, d-2, d-2, fill=bg, outline=acc, width=2)
        c.create_text(d//2, d//2, text="E", fill=acc, font=("Segoe UI", 14, "bold"))

    # ── Drag ──────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root-self._drag_x}+{e.y_root-self._drag_y}")

    def _on_enter(self, e):
        self._hover = True

    def _on_leave(self, e):
        # Only mark as not-hovering if cursor actually left the window
        try:
            x, y = self.winfo_pointerxy()
            wx, wy = self.winfo_rootx(), self.winfo_rooty()
            ww, wh = self.winfo_width(), self.winfo_height()
            if not (wx <= x <= wx+ww and wy <= y <= wy+wh):
                self._hover = False
        except Exception:
            self._hover = False

    # ── Poll loop ─────────────────────────────────────────────────────────────
    def _start_poll(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
        self._poll_id = self.after(30, self._poll)

    def _poll(self):
        if not self.winfo_exists():
            return
        if self._expanded:
            self._poll_id = self.after(50, self._poll)
            return

        # Check expand key
        key = getattr(self.app, "orb_expand_key", "ctrl")
        try:
            held = keyboard.is_pressed(key)
        except Exception:
            held = False

        # Also check pointer position manually for hover
        try:
            mx, my = self.winfo_pointerxy()
            wx = self.winfo_rootx(); wy = self.winfo_rooty()
            ww = self.winfo_width(); wh = self.winfo_height()
            self._hover = (wx <= mx <= wx+ww and wy <= my <= wy+wh)
        except Exception:
            pass

        active = held and self._hover

        # Smooth glow animation
        target = 1.0 if active else (0.35 if held or self._hover else 0.0)
        self._glow += (target - self._glow) * 0.22
        if abs(self._glow - target) > 0.005:
            self._draw_orb()
        elif abs(self._glow) < 0.005:
            self._glow = 0.0
            self._draw_orb()

        # Trigger expand
        if active:
            self._do_expand()
            return

        self._poll_id = self.after(30, self._poll)

    # ── Expand ────────────────────────────────────────────────────────────────
    def _do_expand(self):
        if self._expanded: return
        self._expanded = True
        tw, th = self.app.WIN_W, self.app.WIN_H

        # Smart positioning: keep window fully on screen
        ox = self.winfo_rootx() + self.ORB_R
        oy = self.winfo_rooty() + self.ORB_R
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # Default: centre on orb
        ax = ox - tw // 2
        ay = oy - th // 2

        # Push away from nearest edge
        if ox > sw // 2:  ax = ox - tw - 20   # orb right-half → open left
        else:             ax = ox + 20          # orb left-half  → open right
        if oy > sh // 2:  ay = oy - th - 20    # orb bottom-half → open up
        else:             ay = oy + 20          # orb top-half    → open down

        # Hard clamp to screen
        ax = max(10, min(ax, sw - tw - 10))
        ay = max(10, min(ay, sh - th - 10))

        # Resize/alpha only — never deiconify/withdraw (that causes the
        # window to flash in and out of the taskbar on every expand/collapse)
        self.app.geometry(f"2x2+{ax + tw//2}+{ay + th//2}")
        self.app.attributes("-alpha", 0.0)
        self._animate_expand(ax + tw//2, ay + th//2, tw, th, 0)
        self.withdraw()
        # Start watching for key release
        self.after(200, self._watch_collapse)

    def _animate_expand(self, cx, cy, tw, th, step):
        steps = 14
        t    = (step + 1) / steps
        ease = t * (2 - t)
        w    = max(2, int(ease * tw))
        h    = max(2, int(ease * th))
        x    = cx - w // 2
        y    = cy - h // 2
        try:
            self.app.geometry(f"{w}x{h}+{x}+{y}")
            self.app.attributes("-alpha", min(1.0, ease * 1.1))
        except Exception: pass
        if step < steps - 1:
            self.app.after(14, lambda: self._animate_expand(cx, cy, tw, th, step+1))
        else:
            try:
                self.app.geometry(f"{tw}x{th}")
                self.app.attributes("-alpha", 1.0)
            except Exception: pass

    def _watch_collapse(self):
        """Poll for key release while app is expanded."""
        if not self._expanded: return
        key = getattr(self.app, "orb_expand_key", "ctrl")
        try:
            held = keyboard.is_pressed(key)
        except Exception:
            held = True
        if not held:
            self._do_collapse()
        else:
            self.after(40, self._watch_collapse)

    def _do_collapse(self):
        if not self._expanded: return
        ox = self.winfo_rootx() + self.ORB_R
        oy = self.winfo_rooty() + self.ORB_R
        self._animate_collapse(ox, oy, 0)

    def start_collapse(self, ox, oy):
        """External call to collapse (e.g. window close button)."""
        self._expanded = True   # pretend expanded so collapse works
        self._animate_collapse(ox, oy, 0)

    def _animate_collapse(self, ox, oy, step):
        steps  = 12
        t      = (step + 1) / steps
        ease   = t * t
        cur_w  = self.app.winfo_width()
        cur_h  = self.app.winfo_height()
        tw, th = self.SIZE, self.SIZE
        w  = max(tw, int(cur_w + (tw - cur_w) * ease))
        h  = max(th, int(cur_h + (th - cur_h) * ease))
        al = max(0.0, 1.0 - ease * 1.1)
        try:
            self.app.geometry(f"{w}x{h}+{ox - w//2}+{oy - h//2}")
            self.app.attributes("-alpha", al)
        except Exception: pass
        if step < steps - 1:
            self.app.after(14, lambda: self._animate_collapse(ox, oy, step+1))
        else:
            try:
                # Shrink to a 1x1 invisible sliver instead of withdraw() —
                # avoids the taskbar add/remove flash. Alpha stays at the
                # final faded-out value (effectively invisible) until the
                # orb expands it again.
                self.app.geometry(f"1x1+{ox}+{oy}")
                self.app.attributes("-alpha", 0.0)
            except Exception: pass
            self._expanded    = False
            self._expand_held = False
            self._glow        = 0.0
            self.deiconify()
            self._draw_orb()
            self._start_poll()


# ═══════════════════════════════════════════════════════════════════════════════
# GUI — Clean rewrite
# ═══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    WIN_W, WIN_H = 480, 640

    def __init__(self):
        super().__init__()
        self.clicker = AutoClicker()
        self.clicker.on_stop = self._on_click_limit
        self.macro   = MacroEngine()
        self._macros = {}
        self._load_macros()

        self.hotkey_name    = "F6"
        self.quit_key       = "F12"
        self.rec_key        = "F8"
        self.macro_play_key = "F9"
        self.kb_lock_key    = "F7"
        self._setting_hk    = None
        self._hk_hooks      = {}
        self._setting_hotkey = False

        # Keyboard autoclicker state
        self._kb_running     = False
        self._kb_thread      = None
        self._kb_key         = None
        self._kb_interval_ms = 100.0
        self._kb_hold_ms     = 0.0
        self._kb_limit       = 0
        self._kb_total       = 0
        self._kb_locked_keys = set()
        self._kb_lock_active = False
        self._kb_lock_hook   = None

        # CPS tester state
        self._test_clicks    = []
        self._test_ripples   = []
        self._test_total_L   = 0
        self._test_total_R   = 0
        self._peak_cps_L     = 0.0
        self._peak_cps_R     = 0.0
        self._test_duration  = 5
        self._test_active    = False
        self._test_done      = False
        self._test_end_time  = 0.0
        self._test_timer_id  = None
        self._test_btn       = "left"   # which mouse button we're testing

        # Keep old total for compat
        self._test_total = 0
        self._peak_cps   = 0.0

        # Simple/advanced mode
        self._simple_mode = tk.BooleanVar(value=True)

        # Click-at-position state
        self._cap_x       = None   # target X
        self._cap_y       = None   # target Y
        self._cap_picking = False  # waiting for user to click to set pos

        # Theme + orb
        self._orb           = None
        self._orb_mode      = False
        self.orb_expand_key = "ctrl"   # key to hold for orb expand
        self._load_theme()
        _apply_theme()

        self.title("Echo AutoClicker")
        self.resizable(False, False)
        self.configure(bg=THEME["BG"])
        self.geometry(f"{self.WIN_W}x{self.WIN_H}")
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.attributes("-alpha", 1.0)
        self._set_app_icon()

        self._build_ui()
        self._bind_all_hotkeys()
        self._tick()

    # ═══════════════════════════════════════════════════════════════════════
    # WIDGET HELPERS
    # ═══════════════════════════════════════════════════════════════════════
    def _div(self, p):
        tk.Frame(p, bg=THEME["BORDER"], height=1).pack(fill="x", padx=14, pady=5)

    def _sec(self, p, text):
        row = tk.Frame(p, bg=THEME["BG"])
        row.pack(fill="x", padx=14, pady=(5,2))
        tk.Frame(row, bg=THEME["ACCENT"], width=3, height=13).pack(side="left")
        tk.Label(row, text=f"  {text}", bg=THEME["BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7, "bold")).pack(side="left", anchor="w")

    def _card(self, p, fill="x", padx=14, pady=(2,4)):
        """Alias for _box — kept for compat."""
        return self._box(p, fill, padx, pady)

    def _fancy_btn(self, p, text, cmd, color=None, textcolor=None, padx=14, pady=9):
        color     = color     or THEME["ACCENT"]
        textcolor = textcolor or THEME["TEXT"]
        btn = RoundedButton(p, text, cmd, color=color, textcolor=textcolor,
                            font=("Segoe UI", 10, "bold"),
                            padx=int(padx), pady=int(pady), radius=10)
        return btn, btn

    def _small_btn(self, p, text, cmd, color=None, fg=None):
        color = color or THEME["BTN_BG"]
        fg    = fg    or THEME["TEXT"]
        btn = RoundedButton(p, text, cmd, color=color, textcolor=fg,
                            font=("Segoe UI", 8, "bold"),
                            padx=10, pady=5, radius=8)
        return btn, btn

    def _seg_btn(self, p, label, val, var, on_select, group_list,
                 font=("Segoe UI", 9, "bold")):
        """Segmented/toggle button. Stored in group_list for mutual deselect."""
        is_sel = (val == var.get())
        def select():
            var.set(val)
            try: on_select()
            except Exception: pass
            for b in group_list:
                s = b._val == var.get()
                b.config_color(THEME["SEL_BG"] if s else THEME["BTN_BG"])
                b._text_color = THEME["ACCENT"] if s else THEME["SUBTEXT"]
                b._draw(b._expand)
        b = RoundedButton(p, label, select,
                          color=THEME["SEL_BG"] if is_sel else THEME["BTN_BG"],
                          textcolor=THEME["ACCENT"] if is_sel else THEME["SUBTEXT"],
                          font=font, padx=14, pady=6, radius=8)
        b._val = val
        group_list.append(b)
        return b

    def _hk_badge(self, p, key_text, label_attr=None):
        """Returns a styled key badge Label."""
        outer = tk.Frame(p, bg=THEME["ACCENT"], padx=1, pady=1)
        outer.pack(side="left", padx=(0,6))
        lbl = tk.Label(outer, text=key_text.upper(), bg=THEME["SEL_BG"],
                       fg=THEME["ACCENT"], font=("Segoe UI", 9, "bold"),
                       padx=12, pady=3)
        lbl.pack()
        if label_attr: setattr(self, label_attr, lbl)
        return lbl

    def _hk_row(self, p, title, key, attr, hk_name):
        row = tk.Frame(p, bg=THEME["BTN_BG"])
        row.pack(fill="x", padx=10, pady=4)
        tk.Label(row, text=title, bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 8), width=11, anchor="w").pack(side="left")
        lbl = self._hk_badge(row, key, attr)
        sb, _ = self._small_btn(row, "SET",
                                 lambda n=hk_name, l=lbl: self._start_hk_capture(n, l,
                                     lambda k, lbl2, name=n: self._apply_hk(name, k, lbl2)),
                                 color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        sb.pack(side="left")

    def _entry(self, p, var, width=6, font=("Segoe UI", 11, "bold")):
        """Compact inline entry using RoundedEntry."""
        e = RoundedEntry(p, textvariable=var, width=max(30, width*9),
                         font=font)
        return e

    # ═══════════════════════════════════════════════════════════════════════
    # TAB SHELL
    # ═══════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        bg = THEME["BG"]

        # Tab bar
        bar = tk.Frame(self, bg=_darken(bg, 8), height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self._tab_frames = {}
        self._tab_btns   = {}

        self._tab_container = tk.Frame(self, bg=bg)
        self._tab_container.pack(fill="both", expand=True)
        container = self._tab_container

        # Settings gear button is packed FIRST on the right so it always
        # reserves its space — the other tabs are packed after and will
        # never be able to cover it, regardless of their combined width.
        settings_frame = tk.Frame(container, bg=bg)
        self._tab_frames["settings"] = settings_frame
        gear_btn = self._make_gear_tab_btn(bar)
        gear_btn.pack(side="right", fill="y", padx=(2,4))
        self._tab_btns["settings"] = gear_btn

        for name, label in [("clicker","CLICKER"), ("tester","CPS TEST"),
                             ("macro","MACRO"), ("keyboard","KEYBOARD"),
                             ("theme","THEME")]:
            frame = tk.Frame(container, bg=bg)
            self._tab_frames[name] = frame
            btn = RoundedButton(bar, label, lambda n=name: self._switch_tab(n),
                                color=_darken(bg,8), textcolor=THEME["SUBTEXT"],
                                font=("Segoe UI", 7, "bold"), padx=10, pady=6, radius=0)
            btn.pack(side="left", fill="y")
            self._tab_btns[name] = btn

        self._build_clicker(self._tab_frames["clicker"])
        self._build_tester(self._tab_frames["tester"])
        self._build_macro(self._tab_frames["macro"])
        self._build_keyboard(self._tab_frames["keyboard"])
        self._build_theme_tab(self._tab_frames["theme"])
        self._build_settings_tab(self._tab_frames["settings"])
        self._switch_tab("clicker")

    def _make_gear_tab_btn(self, bar):
        """A square canvas button with a drawn gear icon (not a font glyph)."""
        SIZE = 36
        bg0 = _darken(THEME["BG"], 8)
        c = tk.Canvas(bar, width=SIZE, height=SIZE, bg=bg0,
                      highlightthickness=0, cursor="hand2")
        c._is_gear   = True
        c._base_bg   = bg0
        c._sel       = False
        c._hover_amt = 0.0

        def draw(hover_t=0.0, selected=False):
            c.delete("all")
            col = THEME["SEL_BG"] if selected else _blend(bg0, THEME["BTN_HOV"], hover_t)
            c.create_rectangle(0, 0, SIZE, SIZE, fill=col, outline="")
            cx, cy = SIZE//2, SIZE//2
            r_outer = 8
            r_inner = 3.2
            teeth = 8
            gear_col = THEME["ACCENT"] if selected else THEME["SUBTEXT"]
            if hover_t > 0 and not selected:
                gear_col = _blend(THEME["SUBTEXT"], THEME["ACCENT"], hover_t)
            import math
            pts = []
            for i in range(teeth * 2):
                ang = math.pi * i / teeth
                rad = r_outer if i % 2 == 0 else r_outer - 2.6
                pts.append((cx + rad*math.cos(ang), cy + rad*math.sin(ang)))
            c.create_polygon(pts, fill=gear_col, outline="")
            c.create_oval(cx-r_inner, cy-r_inner, cx+r_inner, cy+r_inner,
                          fill=col, outline="")

        draw()

        def on_enter(e):
            c._hover_amt = 1.0
            draw(1.0, c._sel)
        def on_leave(e):
            c._hover_amt = 0.0
            draw(0.0, c._sel)
        def on_click(e):
            self._switch_tab("settings")

        c.bind("<Enter>", on_enter)
        c.bind("<Leave>", on_leave)
        c.bind("<ButtonRelease-1>", on_click)

        # Expose a config_color-like interface so _switch_tab can call it
        def config_color(new_bg):
            c._sel = (new_bg == THEME["SEL_BG"])
            draw(c._hover_amt, c._sel)
        c.config_color = config_color
        c._text_color  = None
        c._draw        = lambda *_: draw(c._hover_amt, c._sel)
        c._expand      = 0

        return c

    def _switch_tab(self, name):
        for n, f in self._tab_frames.items(): f.pack_forget()
        if name == "clicker":
            self._tab_frames[name].pack(fill="x")
            self.after(50, self._snap_height)
        else:
            self._tab_frames[name].pack(fill="both", expand=True)
            self.geometry(f"{self.WIN_W}x{self.WIN_H}")
        for n, b in self._tab_btns.items():
            sel = (n == name)
            b.config_color(THEME["SEL_BG"] if sel else _darken(THEME["BG"], 8))
            b._text_color = THEME["ACCENT"] if sel else THEME["SUBTEXT"]
            b._draw(b._expand)

    # ═══════════════════════════════════════════════════════════════════════
    # CLICKER TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_clicker(self, p):
        bg = THEME["BG"]

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(p, bg=bg)
        hdr.pack(fill="x", padx=14, pady=(10,6))

        # Status indicator
        status_box = tk.Frame(hdr, bg=bg)
        status_box.pack(side="left")
        self.status_dot = tk.Label(status_box, text="●", bg=bg, fg=THEME["ACCENT2"],
                                    font=("Segoe UI", 10))
        self.status_dot.pack(side="left")
        self.status_lbl = tk.Label(status_box, text="STOPPED", bg=bg,
                                    fg=THEME["ACCENT2"], font=("Segoe UI", 8, "bold"))
        self.status_lbl.pack(side="left", padx=4)

        # Simple ↔ Advanced pill switch (right side)
        tog_frame = tk.Frame(hdr, bg=bg)
        tog_frame.pack(side="right")
        self._simple_lbl = tk.Label(tog_frame, text="SIMPLE", bg=bg,
                                     fg=THEME["ACCENT"], font=("Segoe UI", 8, "bold"))
        self._simple_lbl.pack(side="left", padx=(0,5))
        self._mode_canvas = tk.Canvas(tog_frame, width=44, height=22,
                                       bg=bg, highlightthickness=0, cursor="hand2")
        self._mode_canvas.pack(side="left")
        self._mode_canvas.bind("<ButtonRelease-1>", lambda e: self._toggle_mode())
        self._adv_lbl = tk.Label(tog_frame, text="ADVANCED", bg=bg,
                                  fg=THEME["SUBTEXT"], font=("Segoe UI", 8, "bold"))
        self._adv_lbl.pack(side="left", padx=(5,0))
        self._draw_mode_switch()

        # ── Session counter box ───────────────────────────────────────────────
        sc = self._box(p)
        sr = tk.Frame(sc, bg=THEME["BTN_BG"])
        sr.pack(fill="x", padx=10, pady=8)
        tk.Label(sr, text="CLICKS", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7, "bold")).pack(side="left")
        self.count_lbl = tk.Label(sr, text="0", bg=THEME["BTN_BG"],
                                   fg=THEME["ACCENT"], font=("Segoe UI", 20, "bold"))
        self.count_lbl.pack(side="left", padx=8)
        rst, _ = self._small_btn(sr, "RESET", self.clicker.reset,
                                  color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        rst.pack(side="right")

        # ── Simple panel (always visible) ─────────────────────────────────────
        self._simple_panel = tk.Frame(p, bg=bg)

        sp = self._simple_panel

        # Mouse button box
        bb = self._box(sp)
        br = tk.Frame(bb, bg=THEME["BTN_BG"])
        br.pack(anchor="center", pady=8)
        self._btn_grp = []
        self.btn_var  = tk.StringVar(value="left")
        for b in ("Left", "Middle", "Right"):
            w = self._seg_btn(br, b, b.lower(), self.btn_var,
                               lambda v=b.lower(): setattr(self.clicker, 'button', v),
                               self._btn_grp)
            w.pack(side="left", padx=3)

        # Click-at-position box
        self._cap_enabled = tk.BooleanVar(value=False)
        cap_box = self._box(sp)
        cap_top = tk.Frame(cap_box, bg=THEME["BTN_BG"])
        cap_top.pack(anchor="center", pady=(8,4))
        RoundedCheckbox(cap_top, variable=self._cap_enabled,
                         text="Click at fixed position",
                         command=self._toggle_cap).pack(side="left")
        cap_coord = tk.Frame(cap_box, bg=THEME["BTN_BG"])
        cap_coord.pack(anchor="center", pady=(0,4))
        self.cap_coord_lbl = tk.Label(cap_coord, text="No position set",
                                       bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                                       font=("Segoe UI", 8))
        self.cap_coord_lbl.pack(side="left", padx=(0,8))
        pk_btn, _ = self._small_btn(cap_coord, "PICK", self._pick_cap_position,
                                     color=THEME["BTN_BG"], fg=THEME["ACCENT"])
        pk_btn.pack(side="left", padx=2)
        cl_btn, _ = self._small_btn(cap_coord, "CLEAR", self._clear_cap_position,
                                     color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        cl_btn.pack(side="left", padx=2)
        tk.Label(cap_box,
                 text="Each click: move to target → click → return",
                 bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7)).pack(pady=(0,6))

        # Click rate box
        rb2 = self._box(sp)
        self.click_mode = tk.StringVar(value="cps")
        mode_grp = []
        mr = tk.Frame(rb2, bg=THEME["BTN_BG"])
        mr.pack(anchor="center", pady=(8,4))
        for lbl, val in [("Clicks Per", "cps"), ("Interval", "interval")]:
            w = self._seg_btn(mr, lbl, val, self.click_mode,
                               self._on_mode_change, mode_grp)
            w.pack(side="left", padx=3)

        # CPS row
        self.cps_frame = tk.Frame(rb2, bg=THEME["BTN_BG"])
        cr = tk.Frame(self.cps_frame, bg=THEME["BTN_BG"])
        cr.pack(anchor="center", pady=(0,8))
        self._unit_grp = []
        self.unit_var  = tk.StringVar(value="sec")
        self.cps_var   = tk.StringVar(value="10")
        e = self._entry(cr, self.cps_var, width=5)
        e.pack(side="left", padx=(0,6))
        e.bind("<KeyRelease>", lambda _: self._update_interval())
        tk.Label(cr, text="per", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0,4))
        for u in ("sec","min","hr"):
            w = self._seg_btn(cr, u.upper(), u, self.unit_var,
                               self._update_interval, self._unit_grp,
                               font=("Segoe UI", 8, "bold"))
            w.pack(side="left", padx=2)

        # Interval row
        self.interval_frame = tk.Frame(rb2, bg=THEME["BTN_BG"])
        ir = tk.Frame(self.interval_frame, bg=THEME["BTN_BG"])
        ir.pack(anchor="center", pady=(0,8))
        self._ivars = {}
        tk.Label(ir, text="Every", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0,6))
        for lbl, default in [("hr","0"),("min","0"),("sec","0"),("ms","100")]:
            sub = tk.Frame(ir, bg=THEME["BTN_BG"])
            sub.pack(side="left", padx=3)
            v = tk.StringVar(value=default)
            self._ivars[lbl] = v
            ent = self._entry(sub, v, width=4, font=("Segoe UI", 10, "bold"))
            ent.pack()
            ent.bind("<KeyRelease>", lambda _: self._update_interval())
            tk.Label(sub, text=lbl, bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                     font=("Segoe UI", 6)).pack()

        # ── Advanced panel ────────────────────────────────────────────────────
        self._adv_panel = tk.Frame(p, bg=bg)
        ap = self._adv_panel

        # Click limit box
        lb = self._box(ap)
        lr = tk.Frame(lb, bg=THEME["BTN_BG"])
        lr.pack(anchor="center", pady=8)
        self.limit_on  = tk.BooleanVar(value=False)
        self.limit_var = tk.StringVar(value="100")
        self.limit_ent = self._entry(lr, self.limit_var, width=6)
        RoundedCheckbox(lr, variable=self.limit_on, text="Limit",
                        command=self._update_limit).pack(side="left")
        self.limit_ent.pack(side="left", padx=8)
        self.limit_ent.bind("<KeyRelease>", lambda _: self._update_limit())
        tk.Label(lr, text="clicks", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 9)).pack(side="left")

        # Click duration box
        db = self._box(ap)
        dr = tk.Frame(db, bg=THEME["BTN_BG"])
        dr.pack(anchor="center", pady=(8,4))
        self.dur_on  = tk.BooleanVar(value=False)
        self.dur_var = tk.StringVar(value="50")
        self.dur_ent = self._entry(dr, self.dur_var, width=6)
        RoundedCheckbox(dr, variable=self.dur_on, text="Hold",
                        command=self._update_duration).pack(side="left")
        self.dur_ent.pack(side="left", padx=8)
        self.dur_ent.bind("<KeyRelease>", lambda _: self._update_duration())
        tk.Label(dr, text="ms per click", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.dur_warn = tk.Label(db, text="", bg=THEME["BTN_BG"],
                                  fg=THEME["WARN"], font=("Segoe UI", 7))
        self.dur_warn.pack(padx=8, anchor="w", pady=(0,4))

        # Hotkeys box
        hk_box = self._box(ap)
        self._hk_row(hk_box, "Toggle clicker:", self.hotkey_name, "toggle_hk_lbl", "toggle")
        self._hk_row(hk_box, "Force quit:",      self.quit_key,   "quit_hk_lbl",   "quit")
        self.footer_lbl = tk.Label(hk_box,
                                    text=f"Toggle: {self.hotkey_name}   Quit: {self.quit_key}",
                                    bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                                    font=("Segoe UI", 7))
        self.footer_lbl.pack(padx=10, pady=(0,6), anchor="w")

        # Orb mode box
        orb_box = self._box(ap)
        orbr = tk.Frame(orb_box, bg=THEME["BTN_BG"])
        orbr.pack(anchor="center", pady=(8,4))
        tk.Label(orbr, text="Orb expand key:", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 8)).pack(side="left", padx=(0,4))
        self.orb_expand_key = getattr(self, "orb_expand_key", "ctrl")
        self.orb_key_lbl = self._hk_badge(orbr, self.orb_expand_key, "orb_key_lbl")
        ob2, _ = self._small_btn(orbr, "SET",
                                  lambda: self._start_hk_capture("orb_expand",
                                      self.orb_key_lbl,
                                      lambda k,l: self._apply_hk("orb_expand",k,l)),
                                  color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        ob2.pack(side="left", padx=4)
        orb_btn_row = tk.Frame(orb_box, bg=THEME["BTN_BG"])
        orb_btn_row.pack(anchor="center", pady=(0,8))
        self.orb_toggle_btn, _ = self._small_btn(
            orb_btn_row,
            "DISABLE ORB MODE" if self._orb_mode else "ENABLE ORB MODE",
            self._toggle_orb_mode,
            color=THEME["BTN_BG"], fg=THEME["ACCENT"])
        self.orb_toggle_btn.pack()

        self._on_mode_change()
        self._on_mode_switch()
        self._update_interval()

    def _box(self, parent, fill="x", padx=14, pady=4):
        """Clean bordered box — no label."""
        outer = tk.Frame(parent, bg=THEME["BORDER"], padx=1, pady=1)
        outer.pack(fill=fill, padx=padx, pady=pady)
        inner = tk.Frame(outer, bg=THEME["BTN_BG"])
        inner.pack(fill="both", expand=True)
        return inner

    def _draw_mode_switch(self):
        """Draw the simple/advanced pill toggle switch."""
        c = self._mode_canvas
        c.delete("all")
        adv = not self._simple_mode.get()
        acc  = THEME["ACCENT"]
        track = THEME["BTN_BG"]   # single neutral track colour always
        # ── Track (pill shape) ───────────────────────────────────────────
        # Left cap
        c.create_oval(2,3,19,19, fill=track, outline=THEME["BORDER"], width=1)
        # Right cap
        c.create_oval(25,3,42,19, fill=track, outline=THEME["BORDER"], width=1)
        # Middle fill (covers the seam)
        c.create_rectangle(10,3,34,19, fill=track, outline="")
        # Border line on top/bottom of middle
        c.create_line(10,3,34,3,   fill=THEME["BORDER"])
        c.create_line(10,19,34,19, fill=THEME["BORDER"])
        # ── Knob ─────────────────────────────────────────────────────────
        kx = 24 if adv else 2   # right side = advanced
        # Shadow
        c.create_oval(kx+1, 4, kx+19, 20, fill=_darken(track,20), outline="")
        # Knob
        c.create_oval(kx, 3, kx+18, 19, fill=acc, outline=_lighten(acc,15), width=1)
        # Highlight on knob
        c.create_arc(kx+3, 5, kx+11, 12, start=40, extent=100,
                     outline=_lighten(acc,40), width=1, style="arc")

    def _toggle_mode(self):
        self._simple_mode.set(not self._simple_mode.get())
        adv = not self._simple_mode.get()
        self._simple_lbl.config(fg=THEME["ACCENT"] if not adv else THEME["SUBTEXT"])
        self._adv_lbl.config(fg=THEME["ACCENT"] if adv else THEME["SUBTEXT"])
        self._draw_mode_switch()
        self._on_mode_switch()
        # Force the clicker tab frame to repack so reqheight is accurate
        cf = self._tab_frames.get("clicker")
        if cf and cf.winfo_manager():
            cf.pack_forget()
            cf.pack(fill="x")

    # ── Click-at-position methods ─────────────────────────────────────────────
    def _toggle_cap(self):
        pass  # enabled via _cap_enabled BooleanVar checked in engine

    def _pick_cap_position(self):
        """Minimise, wait 2s, snapshot mouse position."""
        self.iconify()
        self._cap_picking = True
        self.after(2000, self._capture_position)

    def _capture_position(self):
        try:
            import pyautogui as _pag
            x, y = _pag.position()
        except Exception:
            try:
                import ctypes
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                pt = POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                x, y = pt.x, pt.y
            except Exception:
                x, y = 0, 0
        self._cap_x = x
        self._cap_y = y
        self._cap_picking = False
        self.deiconify()
        if hasattr(self, "cap_coord_lbl"):
            self.cap_coord_lbl.config(text=f"({x}, {y})", fg=THEME["ACCENT"])

    def _clear_cap_position(self):
        self._cap_x = None
        self._cap_y = None
        self._cap_enabled.set(False)
        if hasattr(self, "cap_coord_lbl"):
            self.cap_coord_lbl.config(text="No position set", fg=THEME["SUBTEXT"])

    def _on_mode_switch(self):
        simple = self._simple_mode.get()
        self._simple_panel.pack_forget()
        self._adv_panel.pack_forget()
        self._simple_panel.pack(fill="x")
        if not simple:
            self._adv_panel.pack(fill="x")
        # Run two layout passes then snap height
        self.update_idletasks()
        self.after(5, lambda: (self.update_idletasks(), self.after(40, self._snap_height)))

    def _snap_height(self):
        """Snap window height to clicker tab content."""
        self.update_idletasks()
        cf = self._tab_frames.get("clicker")
        if not cf: return
        rh = cf.winfo_reqheight()
        if rh < 10:
            # Layout not done yet — retry
            self.after(50, self._snap_height); return
        total = rh + 44
        total = max(280, min(total, 780))
        self.geometry(f"{self.WIN_W}x{total}")

    def _on_mode_change(self, *_):
        if not hasattr(self, "click_mode"): return
        if self.click_mode.get() == "cps":
            self.interval_frame.pack_forget()
            self.cps_frame.pack(fill="x")
        else:
            self.cps_frame.pack_forget()
            self.interval_frame.pack(fill="x")
        self._update_interval()

    def _update_interval(self):
        if not hasattr(self, "click_mode"): return
        hold = self.clicker.hold_ms
        try:
            if self.click_mode.get() == "cps":
                n    = float(self.cps_var.get())
                mult = {"sec":1,"min":60,"hr":3600}[self.unit_var.get()]
                cps  = n / mult
                if cps <= 0: raise ValueError
                interval = 1000.0 / cps
                self.clicker.interval_ms = max(interval, hold)
                if hasattr(self, "dur_warn"):
                    if hold > 0 and interval < hold:
                        self.dur_warn.config(text=f"Max {1000.0/hold:.1f} CPS with this hold")
                    else:
                        self.dur_warn.config(text="")
            else:
                hr  = max(0, int(self._ivars["hr"].get()  or 0))
                mn  = max(0, int(self._ivars["min"].get() or 0))
                sc  = max(0, int(self._ivars["sec"].get() or 0))
                ms  = max(1, int(self._ivars["ms"].get()  or 1))
                self.clicker.interval_ms = float((hr*3600+mn*60+sc)*1000+ms)
                if hasattr(self, "dur_warn"): self.dur_warn.config(text="")
        except (ValueError, ZeroDivisionError): pass

    def _update_duration(self):
        if not hasattr(self, "dur_ent"): return
        if self.dur_on.get():
            try: self.clicker.hold_ms = max(0.0, float(self.dur_var.get()))
            except: self.clicker.hold_ms = 0.0
        else:
            self.clicker.hold_ms = 0.0
            if hasattr(self, "dur_warn"): self.dur_warn.config(text="")
        self._update_interval()

    def _update_limit(self):
        if not hasattr(self, "limit_ent"): return
        if self.limit_on.get():
            try:    self.clicker.limit = int(self.limit_var.get())
            except: self.clicker.limit = 0
        else:
            self.clicker.limit = 0

    def _set_btn(self, b): self.clicker.button = b

    # ═══════════════════════════════════════════════════════════════════════
    # CPS TESTER TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_tester(self, p):
        bg = THEME["BG"]
        self._test_active   = False
        self._test_done     = False
        self._test_end_time = 0.0
        self._test_timer_id = None
        self._test_btn      = "left"

        hdr = tk.Frame(p, bg=bg)
        hdr.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(hdr, text="CPS",    bg=bg, fg=THEME["ACCENT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(hdr, text=" TESTER", bg=bg, fg=THEME["TEXT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self._div(p)

        # Duration selector
        self._sec(p, "DURATION")
        dur_card = self._box(p, pady=(2,2))
        dr = tk.Frame(dur_card, bg=THEME["BTN_BG"])
        dr.pack(fill="x", padx=8, pady=6)
        self._dur_var  = tk.IntVar(value=5)
        self._dur_btns = []
        for s in (1, 5, 10, 15, 30, 60):
            b = self._seg_btn(dr, f"{s}s", s, self._dur_var,
                               lambda sv=s: self._on_dur_select(sv),
                               self._dur_btns, font=("Segoe UI", 8, "bold"))
            b.pack(side="left", padx=2)

        # Mouse button selector for test
        self._sec(p, "TEST BUTTON")
        tbtn_card = self._box(p, pady=(2,2))
        tb = tk.Frame(tbtn_card, bg=THEME["BTN_BG"])
        tb.pack(fill="x", padx=8, pady=6)
        self._test_btn_var = tk.StringVar(value="left")
        self._test_btn_grp = []
        for lbl in ("Left", "Right"):
            b = self._seg_btn(tb, lbl, lbl.lower(), self._test_btn_var,
                               lambda v=lbl.lower(): self._set_test_btn(v),
                               self._test_btn_grp)
            b.pack(side="left", padx=3)

        # Result display card
        self._sec(p, "RESULT")
        res_card = self._box(p, pady=(2,2))
        rr = tk.Frame(res_card, bg=THEME["BTN_BG"])
        rr.pack(fill="x", padx=8, pady=8)

        for attr, lbl, col in [
            ("cps_display",    "SCORE", THEME["SUCCESS"]),
            ("test_live_lbl",  "LIVE",  THEME["ACCENT"]),
            ("test_total_lbl", "CLICKS",THEME["TEXT"]),
            ("test_peak_lbl",  "BEST",  THEME["ACCENT"]),
        ]:
            box = tk.Frame(rr, bg=_lighten(THEME["BTN_BG"],6))
            box.pack(side="left", fill="both", expand=True, padx=3)
            tk.Label(box, text=lbl, bg=_lighten(THEME["BTN_BG"],6),
                     fg=THEME["SUBTEXT"], font=("Segoe UI", 6, "bold")).pack(pady=(4,0))
            lbl_w = tk.Label(box, text="—", bg=_lighten(THEME["BTN_BG"],6),
                             fg=col, font=("Segoe UI", 14, "bold"))
            lbl_w.pack(pady=(0,4))
            setattr(self, attr, lbl_w)

        # Status line
        self.cps_label_top = tk.Label(p, text="CLICK THE ZONE BELOW TO START",
                                       bg=bg, fg=THEME["SUBTEXT"],
                                       font=("Segoe UI", 8, "bold"))
        self.cps_label_top.pack(pady=(6,0))
        self.cps_label_bot = tk.Label(p, text="", bg=bg, fg=THEME["SUBTEXT"],
                                       font=("Segoe UI", 7))
        self.cps_label_bot.pack()
        self._cooldown_lbl = tk.Label(p, text="", bg=bg, fg=THEME["ACCENT2"],
                                       font=("Segoe UI", 7, "bold"))
        self._cooldown_lbl.pack()

        # Click zone — takes all remaining space
        self._canvas = tk.Canvas(p, bg=THEME["BTN_BG"], highlightthickness=0,
                                  cursor="hand2")
        self._canvas.pack(fill="both", expand=True, padx=14, pady=(4,4))
        self._canvas.bind("<ButtonPress-1>",   self._on_test_click_L)
        self._canvas.bind("<ButtonPress-3>",   self._on_test_click_R)
        self._canvas.bind("<Configure>",        self._draw_hint)

        # Reset
        rst, _ = self._small_btn(p, "RESET", self._reset_test,
                                  color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        rst.pack(pady=(0,8))

    def _on_dur_select(self, secs):
        if self._test_active: return
        self._test_duration = secs
        self._dur_var.set(secs)

    def _set_test_btn(self, btn):
        self._test_btn = btn

    def _on_test_click_L(self, ev):
        if self._test_btn_var.get() == "left":
            self._on_test_click(ev)

    def _on_test_click_R(self, ev):
        if self._test_btn_var.get() == "right":
            self._on_test_click(ev)

    def _on_test_click(self, ev):
        now = time.perf_counter()
        if self._test_done:
            if now - self._test_end_time < 2.0: return
            self._reset_test()
            self._start_test()
            self._test_clicks.append(now)
            self._test_total += 1
            self.test_total_lbl.config(text="1")
            self.test_live_lbl.config(text="—")
            self._spawn_ripple(ev.x, ev.y)
            return
        if not self._test_active:
            self._start_test()
        self._test_clicks.append(now)
        self._test_total += 1
        self.test_total_lbl.config(text=str(self._test_total))
        if len(self._test_clicks) >= 2:
            gap = self._test_clicks[-1] - self._test_clicks[-2]
            if gap > 0:
                self.test_live_lbl.config(text=f"{1.0/gap:.1f}")
        remaining = max(0.0, self._test_end_time - now)
        self.cps_display.config(text=f"{remaining:.1f}s", fg=THEME["ACCENT"])
        self.cps_label_top.config(text="TIME REMAINING")
        self.cps_label_bot.config(text=f"{self._test_total} clicks so far")
        self._spawn_ripple(ev.x, ev.y)

    def _start_test(self):
        self._test_active   = True
        self._test_done     = False
        self._test_end_time = time.perf_counter() + self._test_duration
        self._canvas.delete("hint")
        if self._test_timer_id: self.after_cancel(self._test_timer_id)
        self._test_timer_id = self.after(self._test_duration * 1000, self._end_test)
        self._countdown_tick()

    def _countdown_tick(self):
        if not self._test_active: return
        remaining = max(0.0, self._test_end_time - time.perf_counter())
        self.cps_display.config(text=f"{remaining:.1f}s", fg=THEME["ACCENT"])
        self.cps_label_top.config(text="TIME REMAINING")
        if remaining > 0: self.after(50, self._countdown_tick)

    def _end_test(self):
        self._test_active   = False
        self._test_done     = True
        self._test_end_time = time.perf_counter()
        n   = self._test_total
        dur = self._test_duration
        cps = n / dur if n >= 2 else 0.0
        if cps > self._peak_cps:
            self._peak_cps = cps
            self.test_peak_lbl.config(text=f"{self._peak_cps:.2f}")
        if n >= 2:
            self.cps_display.config(text=f"{cps:.2f}", fg=THEME["SUCCESS"])
            self.cps_label_top.config(text="YOUR CPS")
            self.cps_label_bot.config(text=f"{n} clicks in {dur}s — click to try again")
        else:
            self.cps_display.config(text="—", fg=THEME["SUBTEXT"])
            self.cps_label_top.config(text="NOT ENOUGH CLICKS")
            self.cps_label_bot.config(text="Need ≥ 2 clicks — click to try again")
        self.test_total_lbl.config(text=str(n) if n else "—")
        self._cooldown_lbl.config(text="⏳ 2s before next test")
        self._draw_hint()
        self.after(2000, self._clear_cooldown)

    def _clear_cooldown(self):
        self._cooldown_lbl.config(text="")
        self.cps_label_top.config(text="Click to test again")
        self._draw_hint()

    def _draw_hint(self, e=None):
        self._canvas.delete("hint")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 2 or h < 2: return
        import time as _t
        if self._test_done and (_t.perf_counter() - self._test_end_time) < 2.0:
            msg = "Wait..."; col = THEME["ACCENT2"]
        elif not self._test_active and not self._test_done:
            msg = f"Click here to start  ({self._test_btn_var.get().upper()} BUTTON)"
            col = THEME["SUBTEXT"]
        elif self._test_active:
            msg = f"Keep clicking! ({self._test_btn_var.get().upper()} BUTTON)"
            col = THEME["SUCCESS"]
        else:
            msg = "Click to test again"; col = THEME["SUBTEXT"]
        self._canvas.create_text(w//2, h//2, text=msg, fill=col,
                                  font=("Segoe UI", 12), tags="hint")

    def _spawn_ripple(self, x, y):
        r = {"x":x,"y":y,"r":6,"max_r":70,"ids":[]}
        self._test_ripples.append(r)
        self._anim_ripple(r)

    def _anim_ripple(self, r):
        if r not in self._test_ripples: return
        for oid in r["ids"]:
            try: self._canvas.delete(oid)
            except: pass
        r["ids"] = []
        prog  = r["r"] / r["max_r"]
        alpha = max(0.0, 1.0-prog)
        def lerp(a,b,t): return int(a+(b-a)*t)
        fg=(0x00,0xd4,0x8a); bg=(0x11,0x18,0x27)
        color = "#{:02x}{:02x}{:02x}".format(
            lerp(fg[0],bg[0],prog), lerp(fg[1],bg[1],prog), lerp(fg[2],bg[2],prog))
        x,y,rv = r["x"],r["y"],r["r"]
        r["ids"].append(self._canvas.create_oval(
            x-rv,y-rv,x+rv,y+rv, outline=color, width=max(1,int(4*alpha)), fill=""))
        rv2=max(1,int(rv*0.55)); p2=max(0,prog-0.2); a2=max(0.0,1.0-p2*1.5)
        if a2>0:
            c2="#{:02x}{:02x}{:02x}".format(lerp(fg[0],bg[0],p2),lerp(fg[1],bg[1],p2),lerp(fg[2],bg[2],p2))
            r["ids"].append(self._canvas.create_oval(
                x-rv2,y-rv2,x+rv2,y+rv2,outline=c2,width=max(1,int(3*a2)),fill=""))
        if prog<0.25:
            dr=max(1,int(7*(1-prog/0.25)))
            r["ids"].append(self._canvas.create_oval(
                x-dr,y-dr,x+dr,y+dr,fill=THEME["SUCCESS"],outline=""))
        r["r"] += 4
        if r["r"] < r["max_r"]:
            self.after(14, lambda: self._anim_ripple(r))
        else:
            for oid in r["ids"]:
                try: self._canvas.delete(oid)
                except: pass
            if r in self._test_ripples: self._test_ripples.remove(r)

    def _reset_test(self):
        self._test_active = False; self._test_done = False
        if self._test_timer_id:
            self.after_cancel(self._test_timer_id); self._test_timer_id = None
        self._test_clicks=[]; self._test_total=0; self._peak_cps=0.0
        self.cps_display.config(text="—", fg=THEME["SUCCESS"])
        self.cps_label_top.config(text="CLICK THE ZONE BELOW TO START")
        self.cps_label_bot.config(text="")
        self._cooldown_lbl.config(text="")
        self.test_total_lbl.config(text="—")
        self.test_peak_lbl.config(text="—")
        self.test_live_lbl.config(text="—")
        for r in self._test_ripples:
            for oid in r["ids"]:
                try: self._canvas.delete(oid)
                except: pass
        self._test_ripples=[]
        self._draw_hint()

    # ═══════════════════════════════════════════════════════════════════════
    # MACRO TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_macro(self, p):
        bg = THEME["BG"]
        self._current_macro = None
        self._macro_events  = []

        hdr = tk.Frame(p, bg=bg)
        hdr.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(hdr, text="MACRO",     bg=bg, fg=THEME["ACCENT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(hdr, text=" RECORDER", bg=bg, fg=THEME["TEXT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self.rec_dot    = tk.Label(hdr, text="●", bg=bg, fg=THEME["SUBTEXT"],
                                    font=("Segoe UI", 12))
        self.rec_dot.pack(side="right", padx=(4,0))
        self.rec_status = tk.Label(hdr, text="IDLE", bg=bg, fg=THEME["SUBTEXT"],
                                    font=("Segoe UI", 8, "bold"))
        self.rec_status.pack(side="right")
        self._div(p)

        # Saved macros card
        self._sec(p, "SAVED MACROS")
        mc = self._box(p, pady=(2,2))
        ma = tk.Frame(mc, bg=THEME["BTN_BG"])
        ma.pack(fill="x", padx=8, pady=6)
        lb_f = tk.Frame(ma, bg=THEME["BORDER"], padx=1, pady=1)
        lb_f.pack(side="left", fill="both", expand=True)
        self._macro_lb = tk.Listbox(lb_f, bg=THEME["BTN_BG"], fg=THEME["TEXT"],
                                     selectbackground=THEME["SEL_BG"],
                                     selectforeground=THEME["ACCENT"],
                                     font=("Segoe UI", 9), relief="flat",
                                     height=4, activestyle="none", highlightthickness=0)
        self._macro_lb.pack(fill="both", expand=True)
        self._macro_lb.bind("<<ListboxSelect>>", self._on_macro_select)
        side = tk.Frame(ma, bg=THEME["BTN_BG"])
        side.pack(side="left", padx=(6,0), fill="y")
        for txt, cmd in [("NEW",self._new_macro),("RENAME",self._rename_macro),
                          ("DELETE",self._delete_macro),("EXPORT",self._export_macro),
                          ("IMPORT",self._import_macro)]:
            b, _ = self._small_btn(side, txt, cmd, color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
            b.pack(fill="x", pady=2)

        self.rec_event_lbl = tk.Label(mc, text="No macro selected",
                                       bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                                       font=("Segoe UI", 7))
        self.rec_event_lbl.pack(padx=8, anchor="w", pady=(0,4))

        # Recording card
        self._sec(p, "RECORDING")
        rc = self._box(p, pady=(2,2))
        rr = tk.Frame(rc, bg=THEME["BTN_BG"])
        rr.pack(fill="x", padx=8, pady=6)
        self.rec_frame, self.rec_lbl = self._fancy_btn(
            rr, "⏺  RECORD", self._toggle_record,
            color=THEME["ACCENT2"], textcolor="#fff", padx=14, pady=8)
        self.rec_frame.pack(side="left", padx=(0,10))
        hk2 = tk.Frame(rr, bg=THEME["BTN_BG"])
        hk2.pack(side="left", fill="y")
        tk.Label(hk2, text="Record key:", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7)).pack(anchor="w")
        kr = tk.Frame(hk2, bg=THEME["BTN_BG"])
        kr.pack()
        self.rec_lbl2 = self._hk_badge(kr, self.rec_key, "rec_lbl2")
        b2, _ = self._small_btn(kr, "SET",
                                  lambda: self._start_hk_capture("rec", self.rec_lbl2,
                                      lambda k,l: self._apply_hk("rec",k,l)),
                                  color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        b2.pack(side="left", padx=4)

        # Playback card
        self._sec(p, "PLAYBACK")
        pb = self._box(p, pady=(2,2))
        pbr = tk.Frame(pb, bg=THEME["BTN_BG"])
        pbr.pack(fill="x", padx=8, pady=6)
        self.play_frame, self.play_lbl_btn = self._fancy_btn(
            pbr, "▶  PLAY", self._toggle_macro_play,
            color=THEME["SUCCESS"], textcolor="#000", padx=14, pady=8)
        self.play_frame.pack(side="left", padx=(0,10))

        for label, attr, default in [("Speed", "speed_var","1.0"),
                                      ("Repeat","repeat_var","1")]:
            col = tk.Frame(pbr, bg=THEME["BTN_BG"])
            col.pack(side="left", padx=(0,10))
            tk.Label(col, text=label, bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                     font=("Segoe UI", 7)).pack(anchor="w")
            v = tk.StringVar(value=default)
            setattr(self, attr, v)
            self._entry(col, v, width=4).pack()

        inf = tk.Frame(pbr, bg=THEME["BTN_BG"])
        inf.pack(side="left")
        tk.Label(inf, text="Infinite", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7)).pack(anchor="w")
        self.infinite_var = tk.BooleanVar(value=False)
        RoundedCheckbox(inf, variable=self.infinite_var).pack()

        # Play hotkey
        pkr = tk.Frame(pb, bg=THEME["BTN_BG"])
        pkr.pack(fill="x", padx=8, pady=(0,4))
        tk.Label(pkr, text="Play key:", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7)).pack(side="left")
        self.mplay_lbl = self._hk_badge(pkr, self.macro_play_key, "mplay_lbl")
        spb, _ = self._small_btn(pkr, "SET",
                                  lambda: self._start_hk_capture("macro_play", self.mplay_lbl,
                                      lambda k,l: self._apply_hk("macro_play",k,l)),
                                  color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        spb.pack(side="left")

        self._refresh_macro_list()

    # ═══════════════════════════════════════════════════════════════════════
    # KEYBOARD TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_keyboard(self, p):
        bg = THEME["BG"]

        hdr = tk.Frame(p, bg=bg)
        hdr.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(hdr, text="KEYBOARD", bg=bg, fg=THEME["ACCENT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(hdr, text=" CLICKER", bg=bg, fg=THEME["TEXT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self.kb_status_dot = tk.Label(hdr, text="●", bg=bg, fg=THEME["ACCENT2"],
                                       font=("Segoe UI", 12))
        self.kb_status_dot.pack(side="right", padx=(4,0))
        self.kb_status_lbl = tk.Label(hdr, text="STOPPED", bg=bg,
                                       fg=THEME["ACCENT2"], font=("Segoe UI", 8, "bold"))
        self.kb_status_lbl.pack(side="right")
        self._div(p)

        # Key selector card
        self._sec(p, "KEY TO PRESS")
        kc = self._box(p, pady=(2,2))
        kr = tk.Frame(kc, bg=THEME["BTN_BG"])
        kr.pack(fill="x", padx=8, pady=6)
        self.kb_key_lbl = tk.Label(kr, text="—", bg=THEME["SEL_BG"],
                                    fg=THEME["ACCENT"], font=("Segoe UI", 14, "bold"),
                                    padx=20, pady=6)
        self.kb_key_lbl.pack(side="left")
        sk, _ = self._small_btn(kr, "SET KEY", self._start_kb_key_capture,
                                 color=THEME["BTN_BG"], fg=THEME["TEXT"])
        sk.pack(side="left", padx=6)
        cl, _ = self._small_btn(kr, "CLEAR", self._clear_kb_key,
                                 color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        cl.pack(side="left")

        # Rate card
        self._sec(p, "PRESS RATE")
        rc2 = self._box(p, pady=(2,2))
        rr2 = tk.Frame(rc2, bg=THEME["BTN_BG"])
        rr2.pack(fill="x", padx=8, pady=6)
        self._kb_unit_grp = []
        self.kb_unit_var = tk.StringVar(value="sec")
        self.kb_cps_var  = tk.StringVar(value="10")
        e2 = self._entry(rr2, self.kb_cps_var, width=5)
        e2.pack(side="left", padx=(0,6))
        e2.bind("<KeyRelease>", lambda _: self._update_kb_interval())
        tk.Label(rr2, text="per", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0,4))
        for u in ("sec","min","hr"):
            w = self._seg_btn(rr2, u.upper(), u, self.kb_unit_var,
                               self._update_kb_interval, self._kb_unit_grp,
                               font=("Segoe UI", 8, "bold"))
            w.pack(side="left", padx=2)

        # Options card (hold + limit)
        self._sec(p, "OPTIONS")
        oc = self._box(p, pady=(2,2))

        hr2 = tk.Frame(oc, bg=THEME["BTN_BG"])
        hr2.pack(fill="x", padx=8, pady=(6,2))
        self.kb_hold_on  = tk.BooleanVar(value=False)
        self.kb_hold_var = tk.StringVar(value="100")
        self.kb_hold_ent = self._entry(hr2, self.kb_hold_var, width=5)
        RoundedCheckbox(hr2, variable=self.kb_hold_on, text="Hold for ms",
                        command=self._update_kb_hold).pack(side="left")
        self.kb_hold_ent.pack(side="left", padx=8)
        self.kb_hold_ent.bind("<KeyRelease>", lambda _: self._update_kb_hold())

        lr3 = tk.Frame(oc, bg=THEME["BTN_BG"])
        lr3.pack(fill="x", padx=8, pady=(2,6))
        self.kb_limit_on  = tk.BooleanVar(value=False)
        self.kb_limit_var = tk.StringVar(value="100")
        self.kb_limit_ent = self._entry(lr3, self.kb_limit_var, width=5)
        RoundedCheckbox(lr3, variable=self.kb_limit_on, text="Stop after",
                        command=self._update_kb_limit).pack(side="left")
        self.kb_limit_ent.pack(side="left", padx=8)
        self.kb_limit_ent.bind("<KeyRelease>", lambda _: self._update_kb_limit())
        tk.Label(lr3, text="presses", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 8)).pack(side="left")

        # Key lock card
        self._sec(p, "KEY LOCK")
        lkc = self._box(p, pady=(2,2))
        tk.Label(lkc,
                 text="Hold keys, press lock hotkey → they stay held.\nPress a locked key again to release all.",
                 bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7), justify="left").pack(padx=8, anchor="w", pady=(4,2))
        lkr = tk.Frame(lkc, bg=THEME["BTN_BG"])
        lkr.pack(fill="x", padx=8, pady=(2,4))
        tk.Label(lkr, text="Lock key:", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 8)).pack(side="left")
        self.kb_lock_lbl = self._hk_badge(lkr, self.kb_lock_key, "kb_lock_lbl")
        slk, _ = self._small_btn(lkr, "SET",
                                  lambda: self._start_hk_capture("kb_lock", self.kb_lock_lbl,
                                      lambda k,l: self._apply_hk("kb_lock",k,l)),
                                  color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        slk.pack(side="left")
        self.kb_lock_status  = tk.Label(lkc, text="UNLOCKED", bg=THEME["BTN_BG"],
                                         fg=THEME["SUBTEXT"], font=("Segoe UI", 8, "bold"))
        self.kb_lock_status.pack(padx=8, anchor="w")
        self.kb_locked_display = tk.Label(lkc, text="", bg=THEME["BTN_BG"],
                                           fg=THEME["ACCENT"], font=("Segoe UI", 7))
        self.kb_locked_display.pack(padx=8, anchor="w", pady=(0,4))

        # Stats row
        st = tk.Frame(p, bg=bg)
        st.pack(fill="x", padx=16, pady=4)
        tk.Label(st, text="PRESSES:", bg=bg, fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 8)).pack(side="left")
        self.kb_count_lbl = tk.Label(st, text="0", bg=bg, fg=THEME["ACCENT"],
                                      font=("Segoe UI", 16, "bold"))
        self.kb_count_lbl.pack(side="left", padx=8)
        rb, _ = self._small_btn(st, "RESET", self._reset_kb_count,
                                 color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        rb.pack(side="left")

        # Start/Stop
        self._div(p)
        self.kb_toggle_frame, self.kb_toggle_lbl = self._fancy_btn(
            p, "▶  START", self._toggle_kb,
            color=THEME["ACCENT"], textcolor="#000", padx=0, pady=11)
        self.kb_toggle_frame.pack(fill="x", padx=14, pady=(4,10))

        # Keyboard visualizer
        self._sec(p, "KEY VISUALIZER")
        self._kb_key_labels = {}
        vis = self._box(p, fill="x", pady=(2,8))
        ROWS = [
            ["esc","f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12"],
            ["`","1","2","3","4","5","6","7","8","9","0","-","=","backspace"],
            ["tab","q","w","e","r","t","y","u","i","o","p","[","]","backslash"],
            ["caps lock","a","s","d","f","g","h","j","k","l",";","apostrophe","enter"],
            ["shift","z","x","c","v","b","n","m",",",".","slash","right shift"],
            ["ctrl","windows","alt","space","right alt","right ctrl"],
        ]
        WIDE = {"backspace":2.0,"tab":1.5,"caps lock":1.8,"enter":2.0,
                "shift":2.2,"right shift":2.2,"space":5.5,"ctrl":1.4,
                "right ctrl":1.4,"windows":1.4,"alt":1.4,"right alt":1.4,
                "backslash":1.2}
        for row in ROWS:
            rf = tk.Frame(vis, bg=THEME["BTN_BG"])
            rf.pack(fill="x", padx=4, pady=1)
            for key in row:
                w = WIDE.get(key, 1.0)
                short = key[:3].upper() if len(key) > 4 else key.upper()
                lbl = tk.Label(rf, text=short, bg=_darken(THEME["BTN_BG"],4),
                               fg=THEME["SUBTEXT"], font=("Segoe UI", 5, "bold"),
                               width=max(2, int(w*4)), height=1, relief="flat",
                               padx=1, pady=2)
                lbl.pack(side="left", padx=1)
                for alias in self._kb_aliases(key):
                    self._kb_key_labels[alias] = lbl

        self._update_kb_interval()

    def _kb_aliases(self, key):
        k = key.lower()
        aliases = {k}
        maps = {"caps lock":["caps lock","capslock","caps"],
                "right shift":["right shift","shift"],
                "right ctrl":["right ctrl","ctrl"],
                "right alt":["right alt","alt"],
                "backspace":["backspace","back"],
                "enter":["enter","return"],
                "windows":["windows","win","left windows"],
                "esc":["esc","escape"],
                "backslash":["backslash","\\"],
                "apostrophe":["apostrophe","'"],
                "slash":["slash","/"],
                "space":["space","spacebar"," "]}
        for canon, variants in maps.items():
            if k in variants: aliases.update(variants)
        return aliases

    def _light_key(self, key_name, on):
        lbl = self._kb_key_labels.get(key_name.lower())
        if lbl:
            if on: lbl.config(bg=THEME["ACCENT"], fg="#000")
            else:  lbl.config(bg=_darken(THEME["BTN_BG"],4), fg=THEME["SUBTEXT"])

    def _start_kb_key_capture(self):
        if self._setting_hotkey: return
        self._setting_hotkey = True
        self.kb_key_lbl.config(text="Press key…", fg=THEME["ACCENT2"])
        threading.Thread(target=self._capture_kb_key, daemon=True).start()

    def _capture_kb_key(self):
        try:
            ev = keyboard.read_event(suppress=True)
            if ev.event_type == keyboard.KEY_DOWN:
                self.after(0, lambda: self._set_kb_key(ev.name))
        except Exception:
            self.after(0, self._cancel_kb_key)

    def _set_kb_key(self, key):
        self._kb_key = key
        self.kb_key_lbl.config(text=key.upper(), fg=THEME["ACCENT"])
        self._setting_hotkey = False

    def _cancel_kb_key(self):
        self.kb_key_lbl.config(
            text="—" if not self._kb_key else self._kb_key.upper(), fg=THEME["ACCENT"])
        self._setting_hotkey = False

    def _clear_kb_key(self):
        self._kb_key = None
        self.kb_key_lbl.config(text="—", fg=THEME["SUBTEXT"])

    def _update_kb_interval(self):
        if not hasattr(self, "kb_cps_var"): return
        try:
            n    = float(self.kb_cps_var.get())
            mult = {"sec":1,"min":60,"hr":3600}[self.kb_unit_var.get()]
            cps  = n / mult
            if cps <= 0: raise ValueError
            self._kb_interval_ms = max(1000.0/cps, self._kb_hold_ms)
        except (ValueError, ZeroDivisionError): pass

    def _update_kb_hold(self):
        if not hasattr(self, "kb_hold_ent"): return
        if self.kb_hold_on.get():
            try:    self._kb_hold_ms = max(0.0, float(self.kb_hold_var.get()))
            except: self._kb_hold_ms = 0.0
        else:
            self._kb_hold_ms = 0.0
        self._update_kb_interval()

    def _update_kb_limit(self):
        if not hasattr(self, "kb_limit_ent"): return
        if self.kb_limit_on.get():
            try:    self._kb_limit = int(self.kb_limit_var.get())
            except: self._kb_limit = 0
        else:
            self._kb_limit = 0

    def _reset_kb_count(self):
        self._kb_total = 0
        self.kb_count_lbl.config(text="0")

    def _toggle_kb(self):
        if self._kb_running:
            self._kb_running = False
        else:
            if not self._kb_key:
                messagebox.showwarning("No key set", "Please set a key to press first.")
                return
            self._update_kb_interval()
            self._update_kb_hold()
            self._update_kb_limit()
            self._kb_running = True
            threading.Thread(target=self._kb_loop, daemon=True).start()

    def _kb_loop(self):
        err = 0.0
        while self._kb_running:
            if self._kb_limit and self._kb_total >= self._kb_limit:
                self._kb_running = False; break
            t0 = time.perf_counter()
            key = self._kb_key
            if key:
                if self._kb_hold_ms > 0:
                    keyboard.press(key)
                    self.after(0, lambda k=key: self._light_key(k, True))
                    time.sleep(self._kb_hold_ms / 1000.0)
                    keyboard.release(key)
                    self.after(0, lambda k=key: self._light_key(k, False))
                else:
                    keyboard.press(key); keyboard.release(key)
            self._kb_total += 1
            elapsed = (time.perf_counter()-t0)*1000
            effective = max(self._kb_interval_ms, self._kb_hold_ms)
            wait = max(0.0, effective - elapsed - err)
            t1 = time.perf_counter()
            if wait > 0: time.sleep(wait/1000)
            err = (elapsed + (time.perf_counter()-t1)*1000) - effective

    def _toggle_kb_lock(self):
        if self._kb_lock_active:
            self._kb_unlock_all()
        else:
            candidates = ["shift","ctrl","alt","windows","tab","caps lock","space",
                "a","b","c","d","e","f","g","h","i","j","k","l","m",
                "n","o","p","q","r","s","t","u","v","w","x","y","z",
                "0","1","2","3","4","5","6","7","8","9",
                "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
                "enter","backspace","esc","delete","up","down","left","right"]
            held = {k for k in candidates
                    if k != self.kb_lock_key and keyboard.is_pressed(k)}
            if not held: return
            self._kb_locked_keys = held
            self._kb_lock_active = True
            for k in held:
                try: keyboard.press(k)
                except: pass
                self._light_key(k, True)
            self._kb_lock_hook = keyboard.hook(self._kb_lock_key_listener)
            self.after(0, self._refresh_lock_ui)

    def _kb_lock_key_listener(self, ev):
        if ev.event_type != keyboard.KEY_DOWN: return
        if ev.name in self._kb_locked_keys:
            self.after(0, self._kb_unlock_all)

    def _kb_unlock_all(self):
        self._kb_lock_active = False
        for k in self._kb_locked_keys:
            try: keyboard.release(k)
            except: pass
            self._light_key(k, False)
        self._kb_locked_keys = set()
        if self._kb_lock_hook:
            try: keyboard.unhook(self._kb_lock_hook)
            except: pass
            self._kb_lock_hook = None
        self._refresh_lock_ui()

    def _refresh_lock_ui(self):
        if not hasattr(self, "kb_lock_status"): return
        if self._kb_lock_active:
            keys_str = " + ".join(sorted(k.upper() for k in self._kb_locked_keys))
            self.kb_lock_status.config(text="🔒 LOCKED", fg=THEME["ACCENT2"])
            self.kb_locked_display.config(text=f"Holding: {keys_str}")
        else:
            self.kb_lock_status.config(text="UNLOCKED", fg=THEME["SUBTEXT"])
            self.kb_locked_display.config(text="")

    def _refresh_kb_ui(self):
        if not hasattr(self, "kb_status_dot"): return
        if self._kb_running:
            self.kb_status_dot.config(fg=THEME["SUCCESS"])
            self.kb_status_lbl.config(text="RUNNING", fg=THEME["SUCCESS"])
            self.kb_toggle_lbl.config(text="■  STOP")
            self.kb_toggle_lbl.config_color(THEME["ACCENT2"])
        else:
            self.kb_status_dot.config(fg=THEME["ACCENT2"])
            self.kb_status_lbl.config(text="STOPPED", fg=THEME["ACCENT2"])
            self.kb_toggle_lbl.config(text="▶  START")
            self.kb_toggle_lbl.config_color(THEME["ACCENT"])

    # ═══════════════════════════════════════════════════════════════════════
    # THEME TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_theme_tab(self, p):
        bg = THEME["BG"]
        hdr = tk.Frame(p, bg=bg)
        hdr.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(hdr, text="THEME",    bg=bg, fg=THEME["ACCENT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(hdr, text=" EDITOR",  bg=bg, fg=THEME["TEXT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self._div(p)

        # Built-in accents
        acc_box = self._box(p, pady=(2,2))
        ar = tk.Frame(acc_box, bg=THEME["BTN_BG"])
        ar.pack(anchor="center", pady=6)
        tk.Label(ar, text="ACCENTS:", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7, "bold")).pack(side="left", padx=(0,6))
        ACCENTS = [
            ("#1e6fff","Dark Blue"), ("#00e5ff","Cyan"), ("#a855f7","Purple"),
            ("#22c55e","Green"), ("#ff6b35","Orange"), ("#ff3c6e","Pink"),
        ]
        for hex_col, name in ACCENTS:
            swatch = tk.Canvas(ar, width=22, height=22, bg=THEME["BTN_BG"],
                                highlightthickness=0, cursor="hand2")
            swatch.pack(side="left", padx=2)
            swatch.create_oval(2,2,20,20, fill=hex_col, outline=_lighten(hex_col,20), width=1)
            swatch.bind("<ButtonRelease-1>", lambda e, c=hex_col: self._apply_accent(c))
            swatch.bind("<Enter>", lambda e, s=swatch, c=hex_col:
                s.create_oval(1,1,21,21,fill=c,outline="#fff",width=2,tags="hover"))
            swatch.bind("<Leave>", lambda e, s=swatch: s.delete("hover"))

        # Colour editors
        cc = self._box(p, fill="x", pady=(2,2))
        self._theme_entries = {}
        COLOUR_KEYS = [("BG","Background"),("BTN_BG","Button BG"),
                       ("ACCENT","Accent"),("ACCENT2","Danger"),
                       ("SUCCESS","Success"),("TEXT","Text"),
                       ("SUBTEXT","Dim text"),("BORDER","Border"),
                       ("SEL_BG","Selected BG")]
        for key, label in COLOUR_KEYS:
            row = tk.Frame(cc, bg=THEME["BTN_BG"])
            row.pack(fill="x", padx=6, pady=1)
            sw = tk.Canvas(row, width=18, height=18, bg=THEME["BTN_BG"],
                            highlightthickness=0)
            sw.pack(side="left", padx=(0,4))
            sw.create_oval(2,2,16,16, fill=THEME[key], outline=THEME["BORDER"])
            tk.Label(row, text=label, bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                     font=("Segoe UI", 8), width=13, anchor="w").pack(side="left")
            v = tk.StringVar(value=THEME[key])
            self._theme_entries[key] = (v, sw)
            ent = self._entry(row, v, width=8, font=("Segoe UI", 8, "bold"))
            ent.pack(side="left", padx=4)
            def on_change(e, k=key, var=v, swatch=sw):
                val = var.get().strip()
                if len(val) in (4,7) and val.startswith("#"):
                    try:
                        _hex_to_rgb(val)
                        THEME[k] = val
                        swatch.delete("all")
                        swatch.create_oval(2,2,16,16,fill=val,outline=THEME["BORDER"])
                    except Exception: pass
            ent.bind("<KeyRelease>", on_change)

        # Apply / Reset
        act = tk.Frame(p, bg=bg)
        act.pack(fill="x", padx=14, pady=6)
        ab, _ = self._fancy_btn(act, "APPLY", self._apply_and_refresh_theme,
                                 color=THEME["ACCENT"], textcolor="#000", padx=14, pady=8)
        ab.pack(side="left", padx=(0,6))
        rb, _ = self._small_btn(act, "RESET DEFAULT", lambda: (THEME.update(
            {"BG":"#0b0d14","BTN_BG":"#111827","ACCENT":"#1e6fff","ACCENT2":"#ff3c6e",
             "TEXT":"#dde4f5","SUBTEXT":"#4a5880","SUCCESS":"#00d48a","BORDER":"#1a2236",
             "SEL_BG":"#0d1f40","WARN":"#ffaa00"}), self._apply_and_refresh_theme()),
                                 color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
        rb.pack(side="left")

    def _apply_accent(self, color):
        """Apply a new accent colour and refresh."""
        THEME["ACCENT"] = color
        THEME["SEL_BG"] = _darken(color, 40)
        self._apply_and_refresh_theme()

    def _build_settings_tab(self, p):
        bg = THEME["BG"]
        hdr = tk.Frame(p, bg=bg)
        hdr.pack(fill="x", padx=16, pady=(10,0))
        tk.Label(hdr, text="⚙",         bg=bg, fg=THEME["ACCENT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(hdr, text=" SETTINGS",  bg=bg, fg=THEME["TEXT"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self._div(p)

        # Palettes
        pal_box = self._box(p, pady=(2,2))
        tk.Label(pal_box, text="PALETTES", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7, "bold")).pack(padx=10, pady=(6,2), anchor="w")
        tk.Label(pal_box, text="Save your current theme as a named palette or load a saved one.",
                 bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7), justify="left").pack(padx=10, anchor="w")
        save_row = tk.Frame(pal_box, bg=THEME["BTN_BG"])
        save_row.pack(anchor="center", pady=4)
        self._pal_name_var = tk.StringVar(value="My Palette")
        name_ent = self._entry(save_row, self._pal_name_var, width=100,
                                font=("Segoe UI", 9, "bold"))
        name_ent.pack(side="left", padx=(0,6))
        sb, _ = self._small_btn(save_row, "SAVE", self._save_palette,
                                  color=THEME["ACCENT"], fg="#000")
        sb.pack(side="left")

        # Saved palette list
        pf = tk.Frame(pal_box, bg=THEME["BORDER"], padx=1, pady=1)
        pf.pack(fill="x", padx=10, pady=4)
        self._pal_lb = tk.Listbox(pf, bg=THEME["BTN_BG"], fg=THEME["TEXT"],
                                    selectbackground=THEME["SEL_BG"],
                                    selectforeground=THEME["ACCENT"],
                                    font=("Segoe UI", 9), relief="flat",
                                    height=4, activestyle="none",
                                    highlightthickness=0)
        self._pal_lb.pack(fill="x")
        self._refresh_palette_list()

        pal_btns = tk.Frame(pal_box, bg=THEME["BTN_BG"])
        pal_btns.pack(anchor="center", pady=(0,6))
        for txt, cmd in [("LOAD", self._load_palette),
                          ("DELETE", self._delete_palette)]:
            b, _ = self._small_btn(pal_btns, txt, cmd,
                                    color=THEME["BTN_BG"], fg=THEME["SUBTEXT"])
            b.pack(side="left", padx=3)

        self._div(p)

        # Orb mode
        orb_box = self._box(p, pady=(2,2))
        tk.Label(orb_box, text="FLOATING ORB MODE", bg=THEME["BTN_BG"],
                 fg=THEME["SUBTEXT"], font=("Segoe UI", 7, "bold")).pack(
                     padx=10, pady=(6,2), anchor="w")
        tk.Label(orb_box,
                 text="Hover over it and hold the expand key to bring the app back.",
                 bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7), justify="left").pack(padx=10, anchor="w")
        orb_r = tk.Frame(orb_box, bg=THEME["BTN_BG"])
        orb_r.pack(anchor="center", pady=(4,6))
        ob, self.orb_btn_lbl = self._fancy_btn(orb_r,
            "DISABLE ORB MODE" if self._orb_mode else "ENABLE ORB MODE",
            self._toggle_orb_mode,
            color=THEME["BTN_BG"], textcolor=THEME["ACCENT"], padx=14, pady=8)
        ob.pack()

        self._div(p)

        # Misc settings
        misc_box = self._box(p, pady=(2,2))
        tk.Label(misc_box, text="MISC", bg=THEME["BTN_BG"], fg=THEME["SUBTEXT"],
                 font=("Segoe UI", 7, "bold")).pack(padx=10, pady=(6,4), anchor="w")
        # Always on top toggle
        self._always_top = tk.BooleanVar(value=False)
        top_row = tk.Frame(misc_box, bg=THEME["BTN_BG"])
        top_row.pack(anchor="center", pady=(0,6))
        RoundedCheckbox(top_row, variable=self._always_top,
                         text="Always on top",
                         command=self._toggle_always_top).pack(side="left")

    # ── Palette methods ───────────────────────────────────────────────────────
    def _save_palette(self):
        name = self._pal_name_var.get().strip()
        if not name: return
        palettes = self._load_palettes_file()
        palettes[name] = dict(THEME)
        self._save_palettes_file(palettes)
        self._refresh_palette_list()

    def _load_palette(self):
        sel = self._pal_lb.curselection()
        if not sel: return
        name = self._pal_lb.get(sel[0])
        palettes = self._load_palettes_file()
        if name in palettes:
            THEME.update(palettes[name])
            self._apply_and_refresh_theme()

    def _delete_palette(self):
        sel = self._pal_lb.curselection()
        if not sel: return
        name = self._pal_lb.get(sel[0])
        palettes = self._load_palettes_file()
        palettes.pop(name, None)
        self._save_palettes_file(palettes)
        self._refresh_palette_list()

    def _refresh_palette_list(self):
        if not hasattr(self, "_pal_lb"): return
        self._pal_lb.delete(0, tk.END)
        for name in sorted(self._load_palettes_file().keys()):
            self._pal_lb.insert(tk.END, name)

    def _load_palettes_file(self):
        pf = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "palettes.json")
        try:
            if os.path.exists(pf):
                with open(pf) as f: return json.load(f)
        except Exception: pass
        return {}

    def _save_palettes_file(self, data):
        pf = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "palettes.json")
        try:
            with open(pf,"w") as f: json.dump(data, f, indent=2)
        except Exception: pass

    def _toggle_always_top(self):
        self.attributes("-topmost", self._always_top.get())

    # ═══════════════════════════════════════════════════════════════════════
    # HOTKEY BINDING
    # ═══════════════════════════════════════════════════════════════════════
    def _bind_all_hotkeys(self):
        self._safe_bind("toggle",     self.hotkey_name,    self._toggle_clicker)
        self._safe_bind("quit",       self.quit_key,       self._quit_app)
        self._safe_bind("rec",        self.rec_key,        self._toggle_record)
        self._safe_bind("macro_play", self.macro_play_key, self._toggle_macro_play)
        self._safe_bind("kb_lock",    self.kb_lock_key,    self._toggle_kb_lock)

    def _safe_bind(self, name, key, fn):
        try:
            if name in self._hk_hooks: keyboard.remove_hotkey(self._hk_hooks[name])
        except: pass
        try:
            # Always dispatch to main thread via after() — avoids crashes from
            # background threads and survives keyboard.hook during recording
            def _cb(f=fn):
                try: self.after(0, f)
                except Exception: pass
            self._hk_hooks[name] = keyboard.add_hotkey(key, _cb, suppress=False)
        except: pass

    def _start_hk_capture(self, name, lbl, after_fn):
        if self._setting_hotkey: return
        self._setting_hotkey = True
        lbl.config(text="…", fg=THEME["ACCENT2"])
        threading.Thread(target=self._capture_hk, args=(lbl, after_fn), daemon=True).start()

    def _capture_hk(self, lbl, after_fn):
        try:
            ev = keyboard.read_event(suppress=True)
            if ev.event_type == keyboard.KEY_DOWN:
                self.after(0, lambda: after_fn(ev.name, lbl))
        except: self.after(0, lambda: self._cancel_hk(lbl))

    def _cancel_hk(self, lbl):
        lbl.config(fg=THEME["ACCENT"]); self._setting_hotkey = False

    def _apply_hk(self, name, key, lbl, *_):
        lbl.config(text=key.upper(), fg=THEME["ACCENT"])
        if name == "toggle":
            self.hotkey_name = key
            if hasattr(self,"footer_lbl"):
                self.footer_lbl.config(text=f"Toggle: {key}   Quit: {self.quit_key}")
        elif name == "quit":
            self.quit_key = key
            if hasattr(self,"footer_lbl"):
                self.footer_lbl.config(text=f"Toggle: {self.hotkey_name}   Quit: {key}")
        elif name == "rec":
            self.rec_key = key
        elif name == "macro_play":
            self.macro_play_key = key
        elif name == "kb_lock":
            self.kb_lock_key = key
        elif name == "orb_expand":
            self.orb_expand_key = key
            # Update FloatingOrb if active
            if self._orb: self._orb.EXPAND_KEY = key
        fn_map = {"toggle":self._toggle_clicker,"quit":self._quit_app,
                  "rec":self._toggle_record,"macro_play":self._toggle_macro_play,
                  "kb_lock":self._toggle_kb_lock}
        if name in fn_map: self._safe_bind(name, key, fn_map[name])
        self._setting_hotkey = False

    # ═══════════════════════════════════════════════════════════════════════
    # CLOSE / ORB / THEME
    # ═══════════════════════════════════════════════════════════════════════
    def _on_window_close(self):
        # The X button always quits the app outright — orb mode never
        # blocks closing. Collapsing to the orb only happens when the
        # user releases the expand key while the app is open.
        self._quit_app()

    def _set_app_icon(self):
        """Set window/taskbar icon if echo_icon.ico is next to the exe/script."""
        try:
            icon_path = os.path.join(
                os.path.dirname(os.path.abspath(sys.argv[0])), "echo_icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

    def _quit_app(self):
        if self._orb:
            try: self._orb.destroy()
            except: pass
        self.clicker.stop()
        self.macro.stop()
        self.destroy()
        os._exit(0)

    def _toggle_orb_mode(self):
        self._orb_mode = not self._orb_mode
        if self._orb_mode:
            # Destroy any old orb before creating a new one
            if self._orb:
                try: self._orb.destroy()
                except Exception: pass
            self._orb = FloatingOrb(self)
            # Position orb at centre of current window
            wx = self.winfo_x() + self.WIN_W // 2 - self._orb.ORB_R
            wy = self.winfo_y() + 40   # near top
            self._orb.geometry(f"+{wx}+{wy}")
            self._orb.update_idletasks()
            # Animate app collapsing into orb
            ox = wx + self._orb.ORB_R
            oy = wy + self._orb.ORB_R
            self._orb.start_collapse(ox, oy)
        else:
            # Destroy orb, show window
            if self._orb:
                try: self._orb.destroy()
                except Exception: pass
                self._orb = None
            self.deiconify()
            self.attributes("-alpha", 1.0)
        self._update_orb_btn_labels()

    def _update_orb_btn_labels(self):
        label = "DISABLE ORB MODE" if self._orb_mode else "ENABLE ORB MODE"
        for attr in ("orb_btn_lbl", "orb_toggle_btn"):
            w = getattr(self, attr, None)
            if w is None: continue
            try:
                # RoundedButton
                w.config_text(label); w._draw(w._expand)
            except AttributeError:
                try: w.config(text=label)
                except Exception: pass

    def _load_theme(self):
        try:
            if os.path.exists(THEMES_FILE):
                with open(THEMES_FILE) as f:
                    saved = json.load(f)
                THEME.update({k:v for k,v in saved.items() if k in THEME})
        except: pass

    def _save_theme(self):
        try:
            with open(THEMES_FILE,"w") as f: json.dump(THEME,f,indent=2)
        except: pass

    def _apply_and_refresh_theme(self):
        _apply_theme(); self._save_theme()
        # Destroy orb separately so it doesn't get re-created twice
        if self._orb:
            try: self._orb.destroy()
            except: pass
            self._orb = None
        for w in self.winfo_children():
            try: w.destroy()
            except: pass
        self.configure(bg=THEME["BG"])
        self._build_ui()
        self._update_orb_btn_labels()

    # ═══════════════════════════════════════════════════════════════════════
    # CLICKER ENGINE WRAPPERS
    # ═══════════════════════════════════════════════════════════════════════
    def _toggle_clicker(self):
        if self.clicker.running: self.clicker.stop()
        else:
            self._update_interval(); self._update_limit()
            # Wire click-at-position
            if hasattr(self, "_cap_enabled"):
                self.clicker.cap_enabled = self._cap_enabled.get()
                self.clicker.cap_x = self._cap_x
                self.clicker.cap_y = self._cap_y
            self.clicker.start()

    def _on_click_limit(self):
        self.after(0, self._refresh_clicker_ui)

    # ═══════════════════════════════════════════════════════════════════════
    # MACRO ENGINE WRAPPERS
    # ═══════════════════════════════════════════════════════════════════════
    def _toggle_record(self):
        if self.macro.playing: return
        if self.macro.recording:
            self.macro.stop_record()
            # Re-bind all hotkeys since the recording hook may have eaten them
            self.after(100, self._bind_all_hotkeys)
            evs = self.macro.get_events()
            if self._current_macro is None:
                name = simpledialog.askstring("Save Recording","Macro name:",parent=self)
                if not name or not name.strip():
                    self.rec_event_lbl.config(text="Recording discarded",fg=THEME["SUBTEXT"])
                    self._update_rec_ui(); return
                name = name.strip()
                self._macros[name] = evs; self._current_macro = name
            else:
                self._macros[self._current_macro] = evs
            self._macro_events = evs
            self._save_macros(); self._refresh_macro_list()
            self.rec_event_lbl.config(
                text=f"'{self._current_macro}' — {len(evs)} events", fg=THEME["SUCCESS"])
        else:
            self.macro.start_record()
            self.rec_event_lbl.config(text="● Recording…", fg=THEME["ACCENT2"])
        self._update_rec_ui()

    def _update_rec_ui(self):
        if self.macro.recording:
            self.rec_dot.config(fg=THEME["ACCENT2"])
            self.rec_status.config(text="RECORDING", fg=THEME["ACCENT2"])
            self.rec_lbl.config(text="⏹  STOP REC")
        else:
            self.rec_dot.config(fg=THEME["SUBTEXT"])
            self.rec_status.config(text="IDLE", fg=THEME["SUBTEXT"])
            self.rec_lbl.config(text="⏺  RECORD")

    def _toggle_macro_play(self):
        if self.macro.recording: return
        if self.macro.playing:
            self.macro.stop(); self._update_play_ui()
        else:
            if not self._macro_events:
                messagebox.showwarning("No macro","Select or record a macro first."); return
            try:    speed = float(self.speed_var.get())
            except: speed = 1.0
            try:    repeat = int(self.repeat_var.get())
            except: repeat = 1
            self.macro.play(self._macro_events, speed=speed, repeat=repeat,
                            infinite=self.infinite_var.get(),
                            on_done=lambda: self.after(0,self._update_play_ui))
            self._update_play_ui()

    def _update_play_ui(self):
        if self.macro.playing: self.play_lbl_btn.config(text="⏹  STOP")
        else:                  self.play_lbl_btn.config(text="▶  PLAY")

    def _refresh_macro_list(self):
        self._macro_lb.delete(0, tk.END)
        for name in sorted(self._macros.keys()):
            self._macro_lb.insert(tk.END, name)

    def _on_macro_select(self, e=None):
        sel = self._macro_lb.curselection()
        if not sel: return
        name = self._macro_lb.get(sel[0])
        self._current_macro = name
        self._macro_events  = self._macros[name]
        self.rec_event_lbl.config(
            text=f"Loaded: '{name}' — {len(self._macro_events)} events",
            fg=THEME["ACCENT"])

    def _new_macro(self):
        name = simpledialog.askstring("New Macro","Name:",parent=self)
        if not name or not name.strip(): return
        name = name.strip()
        if name in self._macros: messagebox.showerror("Error",f"'{name}' exists."); return
        self._macros[name] = []; self._save_macros(); self._refresh_macro_list()
        self._current_macro = name; self._macro_events = []
        self.rec_event_lbl.config(text=f"Created '{name}'", fg=THEME["SUBTEXT"])

    def _rename_macro(self):
        if not self._current_macro: return
        new = simpledialog.askstring("Rename",f"New name:",parent=self)
        if not new or not new.strip(): return
        new = new.strip()
        if new in self._macros: messagebox.showerror("Error",f"'{new}' exists."); return
        self._macros[new] = self._macros.pop(self._current_macro)
        self._current_macro = new; self._save_macros(); self._refresh_macro_list()

    def _delete_macro(self):
        if not self._current_macro: return
        if not messagebox.askyesno("Delete",f"Delete '{self._current_macro}'?"): return
        del self._macros[self._current_macro]
        self._current_macro = None; self._macro_events = []
        self._save_macros(); self._refresh_macro_list()
        self.rec_event_lbl.config(text="No macro selected", fg=THEME["SUBTEXT"])

    def _export_macro(self):
        if not self._current_macro: return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json")], initialfile=self._current_macro+".json")
        if not path: return
        with open(path,"w") as f:
            json.dump({"name":self._current_macro,"events":self._macros[self._current_macro]},f,indent=2)
        messagebox.showinfo("Exported",f"Saved to {path}")

    def _import_macro(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        try:
            with open(path) as f: data = json.load(f)
            name = data.get("name","imported"); events = data.get("events",[])
            base = name; i = 1
            while name in self._macros: name = f"{base}_{i}"; i+=1
            self._macros[name] = events; self._save_macros(); self._refresh_macro_list()
            self._current_macro = name; self._macro_events = events
            self.rec_event_lbl.config(
                text=f"Imported '{name}' — {len(events)} events", fg=THEME["ACCENT"])
        except Exception as ex: messagebox.showerror("Import failed",str(ex))

    def _load_macros(self):
        try:
            if os.path.exists(MACROS_FILE):
                with open(MACROS_FILE) as f: self._macros = json.load(f)
        except: self._macros = {}

    def _save_macros(self):
        try:
            with open(MACROS_FILE,"w") as f: json.dump(self._macros,f,indent=2)
        except: pass

    # ═══════════════════════════════════════════════════════════════════════
    # TICK / REFRESH
    # ═══════════════════════════════════════════════════════════════════════
    def _tick(self):
        self._refresh_clicker_ui()
        if hasattr(self, "kb_status_dot"): self._refresh_kb_ui()
        self.after(100, self._tick)

    def _refresh_clicker_ui(self):
        if not hasattr(self, "status_dot"): return
        running = self.clicker.running
        if hasattr(self,"count_lbl"): self.count_lbl.config(text=str(self.clicker.total))
        if running:
            self.status_dot.config(fg=THEME["SUCCESS"])
            self.status_lbl.config(text="RUNNING", fg=THEME["SUCCESS"])
        else:
            self.status_dot.config(fg=THEME["ACCENT2"])
            self.status_lbl.config(text="STOPPED", fg=THEME["ACCENT2"])


if __name__ == "__main__":
    app = App()
    app.mainloop()