"""
AutoClicker Pro — Windows autoclicker with macro recorder
Requirements: pip install keyboard mouse
"""

import tkinter as tk
from tkinter import simpledialog, messagebox
import threading
import time
import ctypes
import ctypes.wintypes
import keyboard
import mouse
import json
import os
import sys
import copy

# ── Win32 raw input ──────────────────────────────────────────────────────────
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

_send      = ctypes.windll.user32.SendInput
_screen_w  = ctypes.windll.user32.GetSystemMetrics(0)
_screen_h  = ctypes.windll.user32.GetSystemMetrics(1)

_BTN_FLAGS = {
    "left":   (MOUSEEVENTF_LEFTDOWN,   MOUSEEVENTF_LEFTUP),
    "right":  (MOUSEEVENTF_RIGHTDOWN,  MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

def _do_click(button="left"):
    d, u = _BTN_FLAGS[button]
    inp = (INPUT*2)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(dwFlags=d))),
                    INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(dwFlags=u))))
    _send(2, inp, ctypes.sizeof(INPUT))

def _move_to(x, y):
    ax = int(x * 65535 / _screen_w)
    ay = int(y * 65535 / _screen_h)
    inp = (INPUT*1)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(
        dx=ax, dy=ay, dwFlags=MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE))))
    _send(1, inp, ctypes.sizeof(INPUT))

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = "#0d0f14"
BORDER  = "#1e2330"
ACCENT  = "#00e5ff"
ACCENT2 = "#ff3c6e"
TEXT    = "#e8ecf4"
SUBTEXT = "#6b7394"
SUCCESS = "#00e5a0"
BTN_BG  = "#1a1e2e"
BTN_HOV = "#1e2540"
SEL_BG  = "#0a2a40"
WARN    = "#ffaa00"

MACROS_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "macros.json")

# ── Autoclicker engine ───────────────────────────────────────────────────────
class AutoClicker:
    def __init__(self):
        self.running     = False
        self.thread      = None
        self.total       = 0
        self.interval_ms = 100.0
        self.button      = "left"
        self.limit       = 0
        self.on_stop     = None

    def _loop(self):
        err = 0.0
        while self.running:
            if self.limit and self.total >= self.limit:
                self.running = False
                if self.on_stop: self.on_stop()
                break
            t0 = time.perf_counter()
            _do_click(self.button)
            self.total += 1
            elapsed = (time.perf_counter()-t0)*1000
            wait = max(0.0, self.interval_ms - elapsed - err)
            t1 = time.perf_counter()
            if wait > 0: time.sleep(wait/1000)
            err = (elapsed + (time.perf_counter()-t1)*1000) - self.interval_ms

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
                        if ev["event_type"] == "down":
                            btn = ev["button"]
                            flag = {"left":MOUSEEVENTF_LEFTDOWN,
                                    "right":MOUSEEVENTF_RIGHTDOWN,
                                    "middle":MOUSEEVENTF_MIDDLEDOWN}.get(btn, MOUSEEVENTF_LEFTDOWN)
                            inp = (INPUT*1)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(dwFlags=flag))))
                            _send(1,inp,ctypes.sizeof(INPUT))
                        elif ev["event_type"] == "up":
                            btn = ev["button"]
                            flag = {"left":MOUSEEVENTF_LEFTUP,
                                    "right":MOUSEEVENTF_RIGHTUP,
                                    "middle":MOUSEEVENTF_MIDDLEUP}.get(btn, MOUSEEVENTF_LEFTUP)
                            inp = (INPUT*1)(INPUT(INPUT_MOUSE,_IU(mi=MOUSEINPUT(dwFlags=flag))))
                            _send(1,inp,ctypes.sizeof(INPUT))
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

# ═══════════════════════════════════════════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.clicker = AutoClicker()
        self.clicker.on_stop = self._on_click_limit

        self.macro   = MacroEngine()
        self._macros = {}          # name -> list of events
        self._load_macros()

        self.hotkey_name      = "F6"
        self.quit_key         = "F12"
        self.rec_key          = "F8"
        self.macro_play_key   = "F9"
        self._setting_hk      = None   # which hotkey is being set
        self._hk_hooks        = {}
        self._setting_hotkey  = False

        self._test_clicks     = []
        self._test_ripples    = []
        self._test_total      = 0
        self._peak_cps        = 0.0
        self._test_duration   = 5
        self._test_active     = False
        self._test_done       = False
        self._test_end_time   = 0.0
        self._test_timer_id   = None

        self.title("AutoClicker Pro")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._quit_app)

        self._build_ui()
        self._bind_all_hotkeys()
        self._tick()

    # ── Hotkey binding ────────────────────────────────────────────────────────
    def _bind_all_hotkeys(self):
        self._safe_bind("toggle",     self.hotkey_name,    self._toggle_clicker)
        self._safe_bind("quit",       self.quit_key,       self._quit_app)
        self._safe_bind("rec",        self.rec_key,        self._toggle_record)
        self._safe_bind("macro_play", self.macro_play_key, self._toggle_macro_play)

    def _safe_bind(self, name, key, fn):
        try:
            if name in self._hk_hooks:
                keyboard.remove_hotkey(self._hk_hooks[name])
        except Exception: pass
        try:
            self._hk_hooks[name] = keyboard.add_hotkey(key, fn, suppress=False)
        except Exception: pass

    def _start_hk_capture(self, name, label_widget, after_fn):
        if self._setting_hotkey: return
        self._setting_hotkey = True
        self._setting_hk = name
        label_widget.config(text="Press key…", fg=ACCENT2)
        threading.Thread(target=self._capture_hk,
                         args=(label_widget, after_fn), daemon=True).start()

    def _capture_hk(self, lbl, after_fn):
        try:
            ev = keyboard.read_event(suppress=True)
            if ev.event_type == keyboard.KEY_DOWN:
                self.after(0, lambda: after_fn(ev.name, lbl))
        except Exception:
            self.after(0, lambda: self._cancel_hk(lbl))

    def _cancel_hk(self, lbl):
        lbl.config(fg=ACCENT)
        self._setting_hotkey = False

    # ── Quit ─────────────────────────────────────────────────────────────────
    def _quit_app(self):
        self.clicker.stop()
        self.macro.stop()
        self.destroy()
        os._exit(0)

    # ── Tab shell ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        bar = tk.Frame(self, bg="#0a0c10", height=38)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self._tab_frames = {}
        self._tab_btns   = {}

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)

        tabs = [("clicker","CLICKER"), ("tester","CPS TEST"), ("macro","MACRO")]
        for name, label in tabs:
            frame = tk.Frame(container, bg=BG)
            self._tab_frames[name] = frame
            btn = self._tab_btn(bar, label, name)
            self._tab_btns[name] = btn

        self._build_clicker(self._tab_frames["clicker"])
        self._build_tester(self._tab_frames["tester"])
        self._build_macro(self._tab_frames["macro"])
        self._switch_tab("clicker")

    def _tab_btn(self, bar, label, name):
        btn = tk.Button(bar, text=label,
                        font=("Segoe UI", 9, "bold"),
                        bg="#0a0c10", fg=SUBTEXT, relief="flat",
                        padx=20, pady=0, cursor="hand2",
                        activebackground=BTN_HOV, activeforeground=ACCENT,
                        command=lambda n=name: self._switch_tab(n))
        btn.pack(side="left", fill="y")
        return btn

    def _switch_tab(self, name):
        for n,f in self._tab_frames.items(): f.pack_forget()
        self._tab_frames[name].pack(fill="both", expand=True)
        for n,b in self._tab_btns.items():
            b.configure(bg=SEL_BG if n==name else "#0a0c10",
                        fg=ACCENT  if n==name else SUBTEXT)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _div(self, parent):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=5)

    def _sec(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=SUBTEXT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=18, pady=(4,0))

    def _fancy_btn(self, parent, text, cmd, color=ACCENT, textcolor="#000", padx=14, pady=7):
        f = tk.Frame(parent, bg=color, padx=2, pady=2)
        inner = tk.Frame(f, bg=color)
        inner.pack(fill="both", expand=True)
        lbl = tk.Label(inner, text=text, bg=color, fg=textcolor,
                       font=("Segoe UI", 10, "bold"),
                       padx=int(padx), pady=int(pady), cursor="hand2")
        lbl.pack(fill="both")

        def on_enter(e):
            inner.config(bg=_lighten(color,20))
            lbl.config(bg=_lighten(color,20))
        def on_leave(e):
            inner.config(bg=color); lbl.config(bg=color)
        def on_press(e):
            inner.config(bg=_darken(color,30)); lbl.config(bg=_darken(color,30))
        def on_release(e):
            inner.config(bg=color); lbl.config(bg=color)
            cmd()

        for w in (inner, lbl):
            w.bind("<Enter>",   on_enter)
            w.bind("<Leave>",   on_leave)
            w.bind("<Button-1>",on_press)
            w.bind("<ButtonRelease-1>", on_release)
        return f, lbl

    def _small_btn(self, parent, text, cmd, color=BTN_BG, fg=TEXT):
        f, lbl = self._fancy_btn(parent, text, cmd, color=color, textcolor=fg,
                                  padx=10, pady=4)
        lbl.config(font=("Segoe UI", 8, "bold"))
        return f, lbl

    # ═══════════════════════════════════════════════════════════════════════
    # CLICKER TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_clicker(self, p):
        # Header
        hdr = tk.Frame(p, bg=BG, pady=10)
        hdr.pack(fill="x", padx=18)
        tk.Label(hdr, text="AUTO",    bg=BG, fg=ACCENT, font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(hdr, text="CLICKER", bg=BG, fg=TEXT,   font=("Segoe UI", 20, "bold")).pack(side="left")
        self.status_dot = tk.Label(hdr, text="●", bg=BG, fg=ACCENT2, font=("Segoe UI", 13))
        self.status_dot.pack(side="right", padx=(0,4))
        self.status_lbl = tk.Label(hdr, text="STOPPED", bg=BG, fg=ACCENT2,
                                   font=("Segoe UI", 9, "bold"))
        self.status_lbl.pack(side="right")

        self._div(p)

        # Mode selector
        self._sec(p, "CLICK MODE")
        mrow = tk.Frame(p, bg=BG)
        mrow.pack(padx=18, pady=(4,8), fill="x")
        mrow._choice_btns = []
        self.click_mode = tk.StringVar(value="cps")
        self._choice_btn(mrow, "Clicks Per",  "cps",      self.click_mode, self._on_mode_change)
        self._choice_btn(mrow, "Interval",    "interval", self.click_mode, self._on_mode_change)

        # CPS frame
        self.cps_frame = tk.Frame(p, bg=BG)
        row = self.cps_frame
        row._unit_btns = []
        tk.Label(row, text="Clicks:", bg=BG, fg=SUBTEXT, font=("Segoe UI", 10)).pack(side="left", padx=(18,4))
        self.cps_var = tk.StringVar(value="10")
        e = tk.Entry(row, textvariable=self.cps_var, width=7,
                     bg=BTN_BG, fg=TEXT, insertbackground=ACCENT,
                     relief="flat", font=("Segoe UI", 13, "bold"), justify="center",
                     highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda _: self._update_interval())
        tk.Label(row, text="per", bg=BG, fg=SUBTEXT, font=("Segoe UI", 10)).pack(side="left", padx=4)
        self.unit_var = tk.StringVar(value="sec")
        for unit in ("sec","min","hr"):
            self._unit_btn(row, unit)
        self.cps_frame.pack(pady=(0,10), fill="x")

        # Interval frame
        self.interval_frame = tk.Frame(p, bg=BG)
        irow = self.interval_frame
        tk.Label(irow, text="Every:", bg=BG, fg=SUBTEXT, font=("Segoe UI", 10)).pack(side="left", padx=(18,6))
        self._ivars = {}
        for label, default, w in [("hr","0",4),("min","0",4),("sec","0",4),("ms","100",5)]:
            sub = tk.Frame(irow, bg=BG)
            sub.pack(side="left", padx=3)
            v = tk.StringVar(value=default)
            self._ivars[label] = v
            ent = tk.Entry(sub, textvariable=v, width=w,
                           bg=BTN_BG, fg=TEXT, insertbackground=ACCENT,
                           relief="flat", font=("Segoe UI", 11, "bold"), justify="center",
                           highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)
            ent.pack()
            ent.bind("<KeyRelease>", lambda _: self._update_interval())
            tk.Label(sub, text=label, bg=BG, fg=SUBTEXT, font=("Segoe UI", 7)).pack()

        self._div(p)

        # Mouse button
        self._sec(p, "MOUSE BUTTON")
        brow = tk.Frame(p, bg=BG)
        brow.pack(padx=18, pady=(4,10), fill="x")
        brow._choice_btns = []
        self.btn_var = tk.StringVar(value="left")
        for b in ("left","middle","right"):
            self._choice_btn(brow, b.upper(), b, self.btn_var, lambda v=b: self._set_btn(v))

        self._div(p)

        # Click limit
        self._sec(p, "CLICK LIMIT")
        lrow = tk.Frame(p, bg=BG)
        lrow.pack(padx=18, pady=(4,10), fill="x")
        self.limit_on = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(lrow, variable=self.limit_on, text="Enable",
                            bg=BG, fg=TEXT, selectcolor=SEL_BG, activebackground=BG,
                            activeforeground=ACCENT, font=("Segoe UI", 10),
                            command=self._update_limit)
        cb.pack(side="left")
        self.limit_var = tk.StringVar(value="100")
        self.limit_ent = tk.Entry(lrow, textvariable=self.limit_var, width=9,
                                   bg=BTN_BG, fg=TEXT, insertbackground=ACCENT,
                                   relief="flat", font=("Segoe UI", 11, "bold"),
                                   justify="center", state="disabled",
                                   disabledbackground=BTN_BG, disabledforeground=SUBTEXT,
                                   highlightthickness=1, highlightbackground=BORDER)
        self.limit_ent.pack(side="left", padx=10)
        self.limit_ent.bind("<KeyRelease>", lambda _: self._update_limit())
        tk.Label(lrow, text="clicks", bg=BG, fg=SUBTEXT, font=("Segoe UI", 10)).pack(side="left")

        self._div(p)

        # Hotkeys
        self._sec(p, "HOTKEYS")
        hkf = tk.Frame(p, bg=BG)
        hkf.pack(padx=18, pady=(4,10), fill="x")
        self._build_hk_row(hkf, "Toggle:",     self.hotkey_name, "toggle_lbl",
                           lambda k,l: self._apply_hk("toggle",k,l,self.hotkey_name))
        self._build_hk_row(hkf, "Force Quit:", self.quit_key,    "quit_lbl",
                           lambda k,l: self._apply_hk("quit",k,l,self.quit_key))

        self._div(p)

        # Stats row
        srow = tk.Frame(p, bg=BG)
        srow.pack(padx=18, pady=6, fill="x")
        tk.Label(srow, text="CLICKS:", bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left")
        self.count_lbl = tk.Label(srow, text="0", bg=BG, fg=ACCENT, font=("Segoe UI", 16, "bold"))
        self.count_lbl.pack(side="left", padx=8)
        sb, _ = self._small_btn(srow, "RESET", self.clicker.reset, color=BTN_BG, fg=SUBTEXT)
        sb.pack(side="left")

        self._div(p)

        # Start/Stop button
        self.toggle_frame, self.toggle_lbl_btn = self._fancy_btn(
            p, "▶  START", self._toggle_clicker, color=ACCENT, textcolor="#000",
            padx=0, pady=14)
        self.toggle_frame.pack(fill="x", padx=18, pady=12)
        self.toggle_lbl_btn.config(font=("Segoe UI", 13, "bold"))

        self.footer_lbl = tk.Label(p, text=f"Toggle: {self.hotkey_name}   Quit: {self.quit_key}",
                                   bg=BG, fg=SUBTEXT, font=("Segoe UI", 8))
        self.footer_lbl.pack(pady=(0,10))

        self._on_mode_change()
        self._update_interval()

    def _build_hk_row(self, parent, title, default_key, attr, apply_fn):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=title, bg=BG, fg=SUBTEXT, font=("Segoe UI", 9), width=10, anchor="w").pack(side="left")
        lbl = tk.Label(row, text=default_key.upper(), bg=SEL_BG, fg=ACCENT,
                       font=("Segoe UI", 10, "bold"), width=9, pady=3)
        lbl.pack(side="left", padx=6)
        setattr(self, attr, lbl)
        sb, _ = self._small_btn(row, "SET", lambda fn=apply_fn, l=lbl: self._start_hk_capture("x", l, fn),
                                 color=BTN_BG, fg=SUBTEXT)
        sb.pack(side="left")

    def _apply_hk(self, name, key, lbl, old_attr_name):
        lbl.config(text=key.upper(), fg=ACCENT)
        if name == "toggle":
            self.hotkey_name = key
            self.footer_lbl.config(text=f"Toggle: {self.hotkey_name}   Quit: {self.quit_key}")
        elif name == "quit":
            self.quit_key = key
            self.footer_lbl.config(text=f"Toggle: {self.hotkey_name}   Quit: {self.quit_key}")
        elif name == "rec":
            self.rec_key = key
            if hasattr(self,"rec_lbl2"): self.rec_lbl2.config(text=key.upper())
        elif name == "macro_play":
            self.macro_play_key = key
            if hasattr(self,"mplay_lbl"): self.mplay_lbl.config(text=key.upper())
        self._safe_bind(name, key, {"toggle":self._toggle_clicker,
                                     "quit":self._quit_app,
                                     "rec":self._toggle_record,
                                     "macro_play":self._toggle_macro_play}[name])
        self._setting_hotkey = False

    def _on_mode_change(self):
        mode = self.click_mode.get()
        if mode == "cps":
            self.interval_frame.pack_forget()
            self.cps_frame.pack(pady=(0,10), fill="x")
        else:
            self.cps_frame.pack_forget()
            self.interval_frame.pack(pady=(0,10), fill="x")
        self._update_interval()

    def _update_interval(self):
        mode = self.click_mode.get()
        try:
            if mode == "cps":
                n    = float(self.cps_var.get())
                mult = {"sec":1,"min":60,"hr":3600}[self.unit_var.get()]
                cps  = n / mult
                if cps <= 0: raise ValueError
                self.clicker.interval_ms = 1000.0 / cps
            else:
                hr  = max(0, int(self._ivars["hr"].get()  or 0))
                mn  = max(0, int(self._ivars["min"].get() or 0))
                sc  = max(0, int(self._ivars["sec"].get() or 0))
                ms  = max(1, int(self._ivars["ms"].get()  or 1))
                total_ms = ((hr*3600 + mn*60 + sc)*1000 + ms)
                self.clicker.interval_ms = float(total_ms)
        except (ValueError, ZeroDivisionError):
            pass

    def _set_btn(self, b): self.clicker.button = b

    def _update_limit(self):
        if self.limit_on.get():
            self.limit_ent.config(state="normal")
            try:    self.clicker.limit = int(self.limit_var.get())
            except: self.clicker.limit = 0
        else:
            self.limit_ent.config(state="disabled")
            self.clicker.limit = 0

    def _toggle_clicker(self):
        if self.clicker.running:
            self.clicker.stop()
        else:
            self._update_interval()
            self._update_limit()
            self.clicker.start()

    def _on_click_limit(self):
        self.after(0, self._refresh_clicker_ui)

    # ═══════════════════════════════════════════════════════════════════════
    # CPS TESTER TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_tester(self, p):
        # Timer state
        self._test_active   = False
        self._test_done     = False
        self._test_end_time = 0.0
        self._test_timer_id = None

        # ── Top controls (compact) ───────────────────────────────────────────
        hdr = tk.Frame(p, bg=BG, pady=8)
        hdr.pack(fill="x", padx=18)
        tk.Label(hdr, text="CPS",     bg=BG, fg=ACCENT, font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(hdr, text=" TESTER", bg=BG, fg=TEXT,   font=("Segoe UI", 18, "bold")).pack(side="left")
        # Reset button lives in the header — far away from click zone
        rb, _ = self._small_btn(hdr, "RESET", self._reset_test, color=BTN_BG, fg=SUBTEXT)
        rb.pack(side="right")

        self._div(p)

        # Duration selector
        self._sec(p, "DURATION")
        drow = tk.Frame(p, bg=BG)
        drow.pack(padx=18, pady=(3,6), fill="x")
        drow._dur_btns = []
        self._dur_var = tk.IntVar(value=5)
        for secs in (1, 5, 10, 15, 30, 60):
            self._dur_btn(drow, secs)

        self._div(p)

        # Stats row (compact)
        stats = tk.Frame(p, bg=BG)
        stats.pack(fill="x", padx=18, pady=(0,6))

        for attr, label, color in [
            ("test_live_lbl",  "LIVE CPS",     SUCCESS),
            ("cps_display",    "RESULT",        SUCCESS),
            ("test_total_lbl", "TOTAL",         TEXT),
            ("test_peak_lbl",  "BEST CPS",      ACCENT),
        ]:
            box = tk.Frame(stats, bg=BTN_BG, padx=10, pady=6)
            box.pack(side="left", fill="both", expand=True, padx=(0,4))
            tk.Label(box, text=label, bg=BTN_BG, fg=SUBTEXT,
                     font=("Segoe UI", 6, "bold")).pack()
            lbl = tk.Label(box, text="—", bg=BTN_BG, fg=color,
                           font=("Segoe UI", 14, "bold"))
            lbl.pack()
            setattr(self, attr, lbl)

        # Status label (sits just above click zone)
        self.cps_label_top = tk.Label(p, text="CLICK THE ZONE TO START",
                                       bg=BG, fg=SUBTEXT, font=("Segoe UI", 8, "bold"))
        self.cps_label_top.pack(pady=(4,2))
        self.cps_label_bot = tk.Label(p, text="", bg=BG, fg=SUBTEXT, font=("Segoe UI", 8))
        self.cps_label_bot.pack()

        # ── BIG click zone — takes all remaining space ───────────────────────
        self._canvas = tk.Canvas(p, bg=BTN_BG, highlightthickness=0, cursor="hand2")
        self._canvas.pack(fill="both", expand=True, padx=18, pady=(4,18))
        self._canvas.bind("<ButtonPress-1>", self._on_test_click)
        self._canvas.bind("<Configure>",     self._draw_hint)

        # Cooldown overlay label (shown for 2s after test ends)
        self._cooldown_lbl = tk.Label(p, text="", bg=BG, fg=ACCENT2,
                                       font=("Segoe UI", 8, "bold"))
        self._cooldown_lbl.pack(pady=(0,4))

    def _dur_btn(self, parent, secs):
        var = self._dur_var
        def select():
            if self._test_active: return   # can't change duration mid-test
            var.set(secs)
            self._test_duration = secs
            for b in parent._dur_btns:
                s = b._secs == var.get()
                b.configure(bg=SEL_BG if s else BTN_BG,
                            fg=ACCENT  if s else SUBTEXT,
                            relief="solid" if s else "flat")
        b = tk.Button(parent, text=f"{secs}s", command=select,
                      bg=SEL_BG if secs==5 else BTN_BG,
                      fg=ACCENT  if secs==5 else SUBTEXT,
                      font=("Segoe UI", 9, "bold"),
                      relief="solid" if secs==5 else "flat",
                      bd=1 if secs==5 else 0,
                      padx=8, pady=4, cursor="hand2",
                      activebackground=BTN_HOV, activeforeground=ACCENT)
        b._secs = secs
        b.pack(side="left", padx=3)
        parent._dur_btns.append(b)

    def _draw_hint(self, e=None):
        self._canvas.delete("hint")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 2 or h < 2: return
        import time as _t
        if self._test_done and (_t.perf_counter() - self._test_end_time) < 2.0:
            msg = "Wait..."
            col = ACCENT2
        elif not self._test_active and not self._test_done:
            msg = "Click anywhere here to start"
            col = SUBTEXT
        elif self._test_active:
            msg = "Keep clicking!"
            col = SUCCESS
        else:
            msg = "Click to test again"
            col = SUBTEXT
        self._canvas.create_text(w//2, h//2, text=msg,
                                  fill=col, font=("Segoe UI", 13), tags="hint")

    def _on_test_click(self, ev):
        now = time.perf_counter()

        if self._test_done:
            # Enforce 2s cooldown so accidental clicks don't restart
            if now - self._test_end_time < 2.0:
                return
            # Start a fresh test
            self._reset_test()
            self._start_test()
            self._test_clicks.append(now)
            self._test_total = 1
            self.test_total_lbl.config(text="1")
            self.test_live_lbl.config(text="—")
            self._spawn_ripple(ev.x, ev.y)
            return

        if not self._test_active:
            # First click — start the timer
            self._start_test()

        self._test_clicks.append(now)
        self._test_total += 1
        self.test_total_lbl.config(text=str(self._test_total))

        # Live CPS: from last 2 clicks (instant speed, no averaging)
        if len(self._test_clicks) >= 2:
            gap = self._test_clicks[-1] - self._test_clicks[-2]
            live_cps = 1.0 / gap if gap > 0 else 0.0
            self.test_live_lbl.config(text=f"{live_cps:.1f}")

        # Live countdown in big display
        remaining = max(0.0, self._test_end_time - now)
        self.cps_display.config(text=f"{remaining:.1f}s", fg=ACCENT)
        self.cps_label_top.config(text="TIME REMAINING")
        self.cps_label_bot.config(text=f"{self._test_total} clicks so far")

        self._spawn_ripple(ev.x, ev.y)

    def _start_test(self):
        self._test_active   = True
        self._test_done     = False
        self._test_end_time = time.perf_counter() + self._test_duration
        self._canvas.delete("hint")
        # Schedule end
        if self._test_timer_id:
            self.after_cancel(self._test_timer_id)
        self._test_timer_id = self.after(self._test_duration * 1000, self._end_test)
        # Live countdown tick
        self._countdown_tick()

    def _countdown_tick(self):
        if not self._test_active: return
        remaining = max(0.0, self._test_end_time - time.perf_counter())
        self.cps_display.config(text=f"{remaining:.1f}s", fg=ACCENT)
        self.cps_label_top.config(text="TIME REMAINING")
        if remaining > 0:
            self.after(50, self._countdown_tick)

    def _end_test(self):
        self._test_active = False
        self._test_done   = True
        self._test_end_time = time.perf_counter()  # used for 2s cooldown
        n = self._test_total
        dur = self._test_duration
        if n >= 2:
            cps = n / dur
        else:
            cps = 0.0

        # Update best
        if cps > self._peak_cps:
            self._peak_cps = cps
            self.test_peak_lbl.config(text=f"{self._peak_cps:.2f}")

        # Show result
        if n >= 2:
            self.cps_display.config(text=f"{cps:.2f}", fg=SUCCESS)
            self.cps_label_top.config(text="YOUR CPS")
            self.cps_label_bot.config(text=f"{n} clicks in {dur}s — click zone to try again")
        else:
            self.cps_display.config(text="—", fg=SUBTEXT)
            self.cps_label_top.config(text="NOT ENOUGH CLICKS")
            self.cps_label_bot.config(text="Need at least 2 clicks — click zone to try again")

        self.test_total_lbl.config(text=str(n) if n > 0 else "—")
        self._cooldown_lbl.config(text="⏳  Wait 2 seconds before clicking again")
        self._draw_hint()
        self.after(2000, self._clear_cooldown)

    def _clear_cooldown(self):
        self._cooldown_lbl.config(text="")
        self.cps_label_top.config(text="Click to test again")
        self._draw_hint()

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
        fg=(0x00,0xe5,0xa0); bgc=(0x1a,0x1e,0x2e)
        color = "#{:02x}{:02x}{:02x}".format(
            lerp(fg[0],bgc[0],prog), lerp(fg[1],bgc[1],prog), lerp(fg[2],bgc[2],prog))
        x,y,rv = r["x"],r["y"],r["r"]
        oid = self._canvas.create_oval(x-rv,y-rv,x+rv,y+rv,
                                        outline=color, width=max(1,int(4*alpha)), fill="")
        r["ids"].append(oid)
        rv2=max(1,int(rv*0.55)); prog2=max(0,prog-0.2); a2=max(0.0,1.0-prog2*1.5)
        if a2>0:
            c2="#{:02x}{:02x}{:02x}".format(lerp(fg[0],bgc[0],prog2),lerp(fg[1],bgc[1],prog2),lerp(fg[2],bgc[2],prog2))
            r["ids"].append(self._canvas.create_oval(x-rv2,y-rv2,x+rv2,y+rv2,outline=c2,width=max(1,int(3*a2)),fill=""))
        if prog<0.25:
            dr=max(1,int(7*(1-prog/0.25)))
            r["ids"].append(self._canvas.create_oval(x-dr,y-dr,x+dr,y+dr,fill=SUCCESS,outline=""))
        r["r"] += 4
        if r["r"] < r["max_r"]:
            self.after(14, lambda: self._anim_ripple(r))
        else:
            for oid in r["ids"]:
                try: self._canvas.delete(oid)
                except: pass
            if r in self._test_ripples: self._test_ripples.remove(r)

    def _reset_test(self):
        self._test_active = False
        self._test_done   = False
        if self._test_timer_id:
            self.after_cancel(self._test_timer_id)
            self._test_timer_id = None
        self._test_clicks = []; self._test_total = 0; self._peak_cps = 0.0
        self.cps_display.config(text="—", fg=SUCCESS)
        self.cps_label_top.config(text="CLICK THE ZONE BELOW TO START")
        self.cps_label_bot.config(text="")
        self.test_total_lbl.config(text="—")
        self.test_peak_lbl.config(text="—")
        self.test_live_lbl.config(text="—")
        self._cooldown_lbl.config(text="")
        self.cps_label_top.config(text="CLICK THE ZONE TO START")
        for r in self._test_ripples:
            for oid in r["ids"]:
                try: self._canvas.delete(oid)
                except: pass
        self._test_ripples = []
        self._draw_hint()

    # ═══════════════════════════════════════════════════════════════════════
    # MACRO TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_macro(self, p):
        self._current_macro   = None   # name of selected macro
        self._macro_events    = []     # events of selected macro
        self._rec_events_live = []     # events during recording

        hdr = tk.Frame(p, bg=BG, pady=10)
        hdr.pack(fill="x", padx=18)
        tk.Label(hdr, text="MACRO",    bg=BG, fg=ACCENT, font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(hdr, text=" RECORDER",bg=BG, fg=TEXT,   font=("Segoe UI", 20, "bold")).pack(side="left")
        self.rec_dot = tk.Label(hdr, text="●", bg=BG, fg=SUBTEXT, font=("Segoe UI", 13))
        self.rec_dot.pack(side="right", padx=(0,4))
        self.rec_status = tk.Label(hdr, text="IDLE", bg=BG, fg=SUBTEXT,
                                   font=("Segoe UI", 9, "bold"))
        self.rec_status.pack(side="right")

        self._div(p)

        # Macro list + controls
        self._sec(p, "SAVED MACROS")
        list_area = tk.Frame(p, bg=BG)
        list_area.pack(fill="x", padx=18, pady=(4,0))

        # Listbox
        lb_frame = tk.Frame(list_area, bg=BORDER, padx=1, pady=1)
        lb_frame.pack(side="left", fill="both", expand=True)
        self._macro_lb = tk.Listbox(lb_frame, bg=BTN_BG, fg=TEXT,
                                     selectbackground=SEL_BG, selectforeground=ACCENT,
                                     font=("Segoe UI", 10), relief="flat",
                                     height=5, activestyle="none",
                                     highlightthickness=0)
        self._macro_lb.pack(fill="both", expand=True)
        self._macro_lb.bind("<<ListboxSelect>>", self._on_macro_select)

        # Side buttons
        side = tk.Frame(list_area, bg=BG)
        side.pack(side="left", padx=(8,0), fill="y")
        for txt, cmd in [("NEW",    self._new_macro),
                          ("RENAME", self._rename_macro),
                          ("DELETE", self._delete_macro),
                          ("EXPORT", self._export_macro),
                          ("IMPORT", self._import_macro)]:
            sb, _ = self._small_btn(side, txt, cmd, color=BTN_BG, fg=SUBTEXT)
            sb.pack(fill="x", pady=2)

        self._div(p)

        # Recording controls
        self._sec(p, "RECORDING")
        rec_row = tk.Frame(p, bg=BG)
        rec_row.pack(padx=18, pady=(4,8), fill="x")

        self.rec_frame, self.rec_lbl = self._fancy_btn(
            rec_row, "⏺  RECORD", self._toggle_record, color=ACCENT2, textcolor="#fff",
            padx=0, pady=8)
        self.rec_frame.pack(side="left", padx=(0,8))
        self.rec_lbl.config(font=("Segoe UI", 10, "bold"))

        # Rec hotkey
        hk2_row = tk.Frame(rec_row, bg=BG)
        hk2_row.pack(side="left", fill="y")
        tk.Label(hk2_row, text="Record key:", bg=BG, fg=SUBTEXT,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self.rec_lbl2 = tk.Label(hk2_row, text=self.rec_key.upper(),
                                  bg=SEL_BG, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                                  width=7, pady=2)
        self.rec_lbl2.pack(side="left")
        sb2, _ = self._small_btn(hk2_row, "SET",
                                  lambda: self._start_hk_capture("x", self.rec_lbl2,
                                      lambda k,l: self._apply_hk("rec",k,l,"")),
                                  color=BTN_BG, fg=SUBTEXT)
        sb2.pack(side="left", padx=4)

        self.rec_event_lbl = tk.Label(p, text="No events recorded", bg=BG, fg=SUBTEXT,
                                       font=("Segoe UI", 8))
        self.rec_event_lbl.pack(anchor="w", padx=18)

        self._div(p)

        # Playback controls
        self._sec(p, "PLAYBACK")
        pb_row = tk.Frame(p, bg=BG)
        pb_row.pack(padx=18, pady=(4,8), fill="x")

        self.play_frame, self.play_lbl_btn = self._fancy_btn(
            pb_row, "▶  PLAY", self._toggle_macro_play, color=SUCCESS, textcolor="#000",
            padx=0, pady=8)
        self.play_frame.pack(side="left", padx=(0,10))
        self.play_lbl_btn.config(font=("Segoe UI", 10, "bold"))

        # Speed
        sp_col = tk.Frame(pb_row, bg=BG)
        sp_col.pack(side="left", padx=(0,12))
        tk.Label(sp_col, text="Speed:", bg=BG, fg=SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w")
        self.speed_var = tk.StringVar(value="1.0")
        sp_ent = tk.Entry(sp_col, textvariable=self.speed_var, width=6,
                          bg=BTN_BG, fg=TEXT, insertbackground=ACCENT,
                          relief="flat", font=("Segoe UI", 11, "bold"), justify="center",
                          highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)
        sp_ent.pack()
        tk.Label(sp_col, text="×", bg=BG, fg=SUBTEXT, font=("Segoe UI", 7)).pack()

        # Repeat
        rp_col = tk.Frame(pb_row, bg=BG)
        rp_col.pack(side="left", padx=(0,12))
        tk.Label(rp_col, text="Repeat:", bg=BG, fg=SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w")
        self.repeat_var = tk.StringVar(value="1")
        self.repeat_ent = tk.Entry(rp_col, textvariable=self.repeat_var, width=6,
                                    bg=BTN_BG, fg=TEXT, insertbackground=ACCENT,
                                    relief="flat", font=("Segoe UI", 11, "bold"), justify="center",
                                    highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)
        self.repeat_ent.pack()
        tk.Label(rp_col, text="times", bg=BG, fg=SUBTEXT, font=("Segoe UI", 7)).pack()

        # Infinite toggle
        inf_col = tk.Frame(pb_row, bg=BG)
        inf_col.pack(side="left")
        tk.Label(inf_col, text="Infinite:", bg=BG, fg=SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w")
        self.infinite_var = tk.BooleanVar(value=False)
        tk.Checkbutton(inf_col, variable=self.infinite_var,
                       bg=BG, fg=TEXT, selectcolor=SEL_BG,
                       activebackground=BG, activeforeground=ACCENT).pack()

        # Play hotkey
        pk_row = tk.Frame(p, bg=BG)
        pk_row.pack(padx=18, pady=(0,8), fill="x")
        tk.Label(pk_row, text="Play key:", bg=BG, fg=SUBTEXT,
                 font=("Segoe UI", 8)).pack(side="left")
        self.mplay_lbl = tk.Label(pk_row, text=self.macro_play_key.upper(),
                                   bg=SEL_BG, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                                   width=7, pady=2)
        self.mplay_lbl.pack(side="left", padx=6)
        spb, _ = self._small_btn(pk_row, "SET",
                                  lambda: self._start_hk_capture("x", self.mplay_lbl,
                                      lambda k,l: self._apply_hk("macro_play",k,l,"")),
                                  color=BTN_BG, fg=SUBTEXT)
        spb.pack(side="left")

        self._refresh_macro_list()

    # ── Macro list ops ────────────────────────────────────────────────────────
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
        n = len(self._macro_events)
        self.rec_event_lbl.config(text=f"Loaded: '{name}' — {n} events", fg=ACCENT)

    def _new_macro(self):
        name = simpledialog.askstring("New Macro", "Macro name:", parent=self)
        if not name or not name.strip(): return
        name = name.strip()
        if name in self._macros:
            messagebox.showerror("Error", f"'{name}' already exists."); return
        self._macros[name] = []
        self._save_macros()
        self._refresh_macro_list()
        self._current_macro = name
        self._macro_events  = []
        self.rec_event_lbl.config(text=f"Created '{name}' — ready to record", fg=SUBTEXT)

    def _rename_macro(self):
        if not self._current_macro:
            messagebox.showwarning("No macro selected","Select a macro first."); return
        new = simpledialog.askstring("Rename", f"New name for '{self._current_macro}':", parent=self)
        if not new or not new.strip(): return
        new = new.strip()
        if new in self._macros:
            messagebox.showerror("Error", f"'{new}' already exists."); return
        self._macros[new] = self._macros.pop(self._current_macro)
        self._current_macro = new
        self._save_macros()
        self._refresh_macro_list()

    def _delete_macro(self):
        if not self._current_macro: return
        if not messagebox.askyesno("Delete", f"Delete '{self._current_macro}'?"): return
        del self._macros[self._current_macro]
        self._current_macro = None
        self._macro_events  = []
        self._save_macros()
        self._refresh_macro_list()
        self.rec_event_lbl.config(text="No macro selected", fg=SUBTEXT)

    def _export_macro(self):
        if not self._current_macro:
            messagebox.showwarning("No macro","Select a macro first."); return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON","*.json")],
            initialfile=self._current_macro+".json")
        if not path: return
        with open(path,"w") as f:
            json.dump({"name":self._current_macro,"events":self._macros[self._current_macro]},f,indent=2)
        messagebox.showinfo("Exported", f"Saved to {path}")

    def _import_macro(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        try:
            with open(path) as f: data = json.load(f)
            name   = data.get("name","imported")
            events = data.get("events",[])
            base = name
            i = 1
            while name in self._macros:
                name = f"{base}_{i}"; i+=1
            self._macros[name] = events
            self._save_macros()
            self._refresh_macro_list()
            self._current_macro = name
            self._macro_events  = events
            self.rec_event_lbl.config(text=f"Imported '{name}' — {len(events)} events", fg=ACCENT)
        except Exception as ex:
            messagebox.showerror("Import failed", str(ex))

    def _load_macros(self):
        try:
            if os.path.exists(MACROS_FILE):
                with open(MACROS_FILE) as f:
                    self._macros = json.load(f)
        except Exception:
            self._macros = {}

    def _save_macros(self):
        try:
            with open(MACROS_FILE,"w") as f:
                json.dump(self._macros, f, indent=2)
        except Exception: pass

    # ── Recording ─────────────────────────────────────────────────────────────
    def _toggle_record(self):
        if self.macro.playing: return
        if self.macro.recording:
            self.macro.stop_record()
            evs = self.macro.get_events()
            if self._current_macro is None:
                name = simpledialog.askstring("Save Recording","Macro name:",parent=self)
                if not name or not name.strip():
                    self.rec_event_lbl.config(text="Recording discarded",fg=SUBTEXT)
                    self._update_rec_ui(); return
                name = name.strip()
                self._macros[name] = evs
                self._current_macro = name
            else:
                self._macros[self._current_macro] = evs
            self._macro_events = evs
            self._save_macros()
            self._refresh_macro_list()
            self.rec_event_lbl.config(
                text=f"Saved to '{self._current_macro}' — {len(evs)} events", fg=SUCCESS)
        else:
            if self._current_macro is None:
                pass   # will ask on stop
            self.macro.start_record()
            self.rec_event_lbl.config(text="● Recording…", fg=ACCENT2)
        self._update_rec_ui()

    def _update_rec_ui(self):
        if self.macro.recording:
            self.rec_dot.config(fg=ACCENT2)
            self.rec_status.config(text="RECORDING", fg=ACCENT2)
            self.rec_lbl.config(text="⏹  STOP REC")
        else:
            self.rec_dot.config(fg=SUBTEXT)
            self.rec_status.config(text="IDLE", fg=SUBTEXT)
            self.rec_lbl.config(text="⏺  RECORD")

    # ── Playback ──────────────────────────────────────────────────────────────
    def _toggle_macro_play(self):
        if self.macro.recording: return
        if self.macro.playing:
            self.macro.stop()
            self._update_play_ui()
        else:
            if not self._macro_events:
                messagebox.showwarning("No macro","Select or record a macro first."); return
            try:    speed = float(self.speed_var.get())
            except: speed = 1.0
            try:    repeat = int(self.repeat_var.get())
            except: repeat = 1
            infinite = self.infinite_var.get()
            self.macro.play(self._macro_events, speed=speed, repeat=repeat,
                            infinite=infinite, on_done=lambda: self.after(0,self._update_play_ui))
            self._update_play_ui()

    def _update_play_ui(self):
        if self.macro.playing:
            self.play_lbl_btn.config(text="⏹  STOP")
        else:
            self.play_lbl_btn.config(text="▶  PLAY")

    # ── Shared widget helpers ─────────────────────────────────────────────────
    def _unit_btn(self, parent, unit):
        var = self.unit_var
        def select():
            var.set(unit)
            self._update_interval()
            for b in parent._unit_btns:
                sel = b._unit == var.get()
                b.configure(bg=SEL_BG if sel else BTN_BG,
                            fg=ACCENT  if sel else SUBTEXT,
                            relief="solid" if sel else "flat")
        b = tk.Button(parent, text=unit.upper(), command=select,
                      bg=SEL_BG if unit=="sec" else BTN_BG,
                      fg=ACCENT  if unit=="sec" else SUBTEXT,
                      font=("Segoe UI", 9, "bold"),
                      relief="solid" if unit=="sec" else "flat",
                      bd=1 if unit=="sec" else 0,
                      padx=10, pady=5, cursor="hand2",
                      activebackground=BTN_HOV, activeforeground=ACCENT)
        b._unit = unit
        b.pack(side="left", padx=3)
        parent._unit_btns.append(b)

    def _choice_btn(self, parent, label, val, var, cmd):
        def select():
            var.set(val)
            if callable(cmd): cmd(val) if cmd.__code__.co_argcount > 0 else cmd()
            for b in parent._choice_btns:
                sel = b._val == var.get()
                b.configure(bg=SEL_BG if sel else BTN_BG,
                            fg=ACCENT  if sel else SUBTEXT,
                            relief="solid" if sel else "flat")
        b = tk.Button(parent, text=label, command=select,
                      bg=SEL_BG if val==var.get() else BTN_BG,
                      fg=ACCENT  if val==var.get() else SUBTEXT,
                      font=("Segoe UI", 9, "bold"),
                      relief="solid" if val==var.get() else "flat",
                      bd=1, padx=14, pady=5, cursor="hand2",
                      activebackground=BTN_HOV, activeforeground=ACCENT)
        b._val = val
        b.pack(side="left", padx=3)
        parent._choice_btns.append(b)

    # ── Tick / refresh ────────────────────────────────────────────────────────
    def _tick(self):
        self._refresh_clicker_ui()
        self.after(100, self._tick)

    def _refresh_clicker_ui(self):
        running = self.clicker.running
        self.count_lbl.config(text=str(self.clicker.total))
        if running:
            self.status_dot.config(fg=SUCCESS)
            self.status_lbl.config(text="RUNNING", fg=SUCCESS)
            self.toggle_lbl_btn.config(text="■  STOP",  bg=ACCENT2)
            self.toggle_frame.config(bg=ACCENT2)
        else:
            self.status_dot.config(fg=ACCENT2)
            self.status_lbl.config(text="STOPPED", fg=ACCENT2)
            self.toggle_lbl_btn.config(text="▶  START", bg=ACCENT)
            self.toggle_frame.config(bg=ACCENT)


# ── Colour helpers ────────────────────────────────────────────────────────────
def _clamp(v): return max(0, min(255, v))

def _lighten(hex_color, amount):
    h = hex_color.lstrip("#")
    r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return "#{:02x}{:02x}{:02x}".format(_clamp(r+amount),_clamp(g+amount),_clamp(b+amount))

def _darken(hex_color, amount):
    return _lighten(hex_color, -amount)


if __name__ == "__main__":
    app = App()
    app.mainloop()