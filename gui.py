#!/usr/bin/env python3
# =============================================================================
# NxtGenAI — Beautiful Desktop GUI  (Pentest Buddy Interface)
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# A rich Tkinter desktop GUI that wraps the PentestGPT-lite engine.
# Run with:
#   python3 gui.py              # auto-loads config.ini from same directory
#   python3 gui.py --config /path/to/config.ini
#
# Features:
#   🎭 Four animated "Pentest Buddy" character faces to choose from
#   🎬 Per-state animations: idle, thinking, talking, happy, alert, scanning
#   🎨 Dark cyberpunk colour theme with neon accent colours
#   💬 Emoji-rich AI output log with typewriter animation
#   📊 Colour-coded risk bars and status indicators
#   🎙️ Detailed voice & keyboard command guide (press F1)
#   🔧 Integration with ai_core.py, tools.py (graceful degradation)
#   💡 Rotating onboarding tips in status bar
# =============================================================================

import configparser
import logging
import math
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

log = logging.getLogger(__name__)

# ── Optional backend imports — degrade gracefully if hardware libs missing ─────
try:
    from ai_core import AICore
    _AI_OK = True
except ImportError:
    _AI_OK = False
    log.warning("ai_core not found — running in demo mode.")

try:
    from tools import ToolRunner
    _TOOLS_OK = True
except ImportError:
    _TOOLS_OK = False
    log.warning("tools not found — pentest actions disabled.")


# =============================================================================
# Colour Theme  (dark cyberpunk palette)
# =============================================================================
T = {
    "bg":          "#0a0a1a",   # Near-black navy background
    "bg2":         "#11112a",   # Slightly lighter for panels
    "bg3":         "#1a1a3a",   # Raised panel / card background
    "bg4":         "#22224a",   # Hover / active highlight
    "fg":          "#dde0ff",   # Light lavender text
    "fg_dim":      "#5555aa",   # Dimmed / secondary text
    "green":       "#00ff88",   # Matrix green (success)
    "green_dk":    "#005533",   # Dark green background for success
    "blue":        "#00b4ff",   # Neon blue (info)
    "blue_dk":     "#002244",   # Dark blue background
    "purple":      "#bb44ff",   # Electric purple (ghost)
    "orange":      "#ff8800",   # Amber (warning)
    "orange_dk":   "#332200",
    "red":         "#ff3355",   # Alert red (danger)
    "red_dk":      "#330011",
    "yellow":      "#ffcc00",   # Bright yellow
    "border":      "#2a2a5a",   # Subtle border
    "title_bg":    "#06060f",   # Header bar
    "btn":         "#1a1a3a",   # Button default
    "btn_hover":   "#2a2a5a",
    "btn_active":  "#0055cc",
    "separator":   "#1e1e44",
}

# =============================================================================
# Character Definitions
# =============================================================================
CHARACTERS = {
    "ghost": {
        "name":         "G.H.O.S.T",
        "full_name":    "Ghost",
        "emoji":        "👻",
        "color":        "#bb44ff",
        "eye_color":    "#ff88ff",
        "face_color":   "#6622aa",
        "personality":  "Sneaky • Mysterious • Hauntingly Effective",
        "desc":         "Slips through firewalls like a whisper in the dark",
        "greeting": (
            "👻 Boo! Ready to haunt some networks?\n"
            "I slip through defences unseen — they'll never know I was here..."
        ),
        "thinking": [
            "👻 Materialising scan results...",
            "👻 Phasing through the firewall...",
            "👻 Haunting the network quietly...",
            "👻 Invisibly probing the target...",
        ],
        "success": [
            "👻 Boo-yah! Vulnerability confirmed! 🎉",
            "👻 I ghosted right through their defences!",
            "👻 They never saw me coming... 👁️",
        ],
        "idle": [
            "👻 Watching. Waiting. Always ready.",
            "👻 The network holds no secrets from me...",
            "👻 I sense weak passwords nearby... 🔑",
            "👻 Standing by in the shadows...",
        ],
        "alert": [
            "👻 DETECTED! Evading now... 💨",
            "👻 Something's wrong — aborting!",
        ],
    },
    "ninja": {
        "name":         "N.I.N.J.A",
        "full_name":    "Ninja",
        "emoji":        "🥷",
        "color":        "#cc2200",
        "eye_color":    "#ff4444",
        "face_color":   "#1a2233",
        "personality":  "Silent • Precise • Leaves No Trace",
        "desc":         "Strikes fast, leaves no logs, disappears like smoke",
        "greeting": (
            "🥷 Silence is the greatest weapon.\n"
            "I strike fast, leave no logs, and vanish before the IDS blinks..."
        ),
        "thinking": [
            "🥷 Calculating optimal strike vector...",
            "🥷 Analysing target defences...",
            "🥷 Moving through digital shadows...",
            "🥷 Silent reconnaissance in progress...",
        ],
        "success": [
            "🥷 Mission complete. Zero traces left.",
            "🥷 They never knew I was there. ✅",
            "🥷 Swift. Silent. Successful. 🎯",
        ],
        "idle": [
            "🥷 Awaiting your orders, sensei...",
            "🥷 Watching from the shadows...",
            "🥷 Patience is a weapon. ⚔️",
            "🥷 Ready to strike at your command.",
        ],
        "alert": [
            "🥷 Evasion mode activated! 💨",
            "🥷 Retreating — will re-engage shortly.",
        ],
    },
    "robot": {
        "name":         "R.O.B.O.T",
        "full_name":    "Robot",
        "emoji":        "🤖",
        "color":        "#0088cc",
        "eye_color":    "#00ffff",
        "face_color":   "#2a3a4a",
        "personality":  "Logical • Methodical • 100% Accurate",
        "desc":         "Algorithmic precision — no exploit left unchecked",
        "greeting": (
            "🤖 INITIALISING PENTEST PROTOCOL v1.0...\n"
            "All systems nominal. Awaiting your command, Operator."
        ),
        "thinking": [
            "🤖 Processing... [██████░░░░] 60%",
            "🤖 Cross-referencing vulnerability database...",
            "🤖 Running algorithmic threat analysis...",
            "🤖 Computing optimal attack vector... ⚙️",
        ],
        "success": [
            "🤖 OBJECTIVE ACHIEVED. Vulnerability confirmed. ✅",
            "🤖 Analysis complete. Success probability: 100%.",
            "🤖 Target compromised. Generating report... 📋",
        ],
        "idle": [
            "🤖 Standing by for instructions...",
            "🤖 Systems nominal. Ready to deploy. ✅",
            "🤖 Monitoring network traffic passively...",
            "🤖 CPU: 12% | RAM: 180 MB | READY ✅",
        ],
        "alert": [
            "🤖 ALERT: Anomaly detected! Initiating countermeasures.",
            "🤖 ERROR 403: Blocked. Switching strategy...",
        ],
    },
    "hacker": {
        "name":         "H.A.C.K.E.R",
        "full_name":    "Hacker",
        "emoji":        "💀",
        "color":        "#00ff44",
        "eye_color":    "#00ff00",
        "face_color":   "#0d1a0d",
        "personality":  "Fearless • Old School • No Firewall Can Stop Me",
        "desc":         "Jack in, cowboy — the matrix never sleeps",
        "greeting": (
            "💀 Jack in, cowboy. The matrix never sleeps.\n"
            "I've broken systems that broke other hackers... Let's ride. 🤘"
        ),
        "thinking": [
            "💀 Executing payload...",
            "💀 Bypassing firewall rules...",
            "💀 Cracking the encryption... 🔓",
            "💀 Deploying exploit chain...",
        ],
        "success": [
            "💀 GOT ROOT! System owned. 🎉",
            "💀 Like taking candy from a misconfigured server.",
            "💀 Another day, another 0-day. 🔥",
        ],
        "idle": [
            "💀 Feeling lucky, firewall? 😈",
            "💀 I dream in hexadecimal...",
            "💀 01001000 01000001 01000011 01001011",
            "💀 The more they patch, the more I learn... 🧠",
        ],
        "alert": [
            "💀 THEY'RE ON TO US! Abort! Abort! 🚨",
            "💀 Honeypot detected — extracting immediately.",
        ],
    },
}

# =============================================================================
# Command & Voice Guide Data
# =============================================================================
COMMAND_GUIDE = [
    ("🎙️  VOICE COMMANDS", [
        ("wifi crack",      "Start WiFi WPA2 handshake capture & crack"),
        ("network scan",    "Discover hosts on the local network"),
        ("web pentest",     "Test a web application for vulnerabilities"),
        ("brute force",     "Launch dictionary brute-force attack"),
        ("full auto",       "Let AI choose and chain all attack steps"),
        ("stop",            "Abort the current operation immediately"),
        ("report",          "Generate and export the pentest report"),
        ("battery",         "Read current battery level (Pi hardware)"),
    ]),
    ("⌨️  KEYBOARD SHORTCUTS", [
        ("SPACE",           "Push-to-Talk: hold to speak, release to act"),
        ("A  /  →",         "Next menu item (or Button A on hardware)"),
        ("B  /  ←",         "Previous item (or Button B on hardware)"),
        ("Enter",           "Confirm / run selected mode"),
        ("Esc",             "Back / cancel current operation"),
        ("F1",              "Toggle this command guide panel"),
        ("F5",              "Reset / restart the buddy session"),
        ("Ctrl+Q",          "Quit application safely"),
    ]),
    ("🔧  AVAILABLE TOOLS", [
        ("nmap",            "Network port scanner & host discovery"),
        ("aircrack-ng",     "WPA2 WiFi password cracker (monitor mode)"),
        ("sqlmap",          "Automated SQL injection detection tool"),
        ("hydra",           "Multi-protocol brute-force cracker"),
        ("arpspoof",        "ARP cache poisoning (MitM setup)"),
        ("curl",            "HTTP header & response security analyser"),
    ]),
    ("⚠️  RISK LEVELS", [
        ("🟢 Risk 1-3",     "Passive scans — safe, read-only, no side-effects"),
        ("🟡 Risk 4-6",     "Active probing — may appear in target access logs"),
        ("🔴 Risk 7-9",     "Disruptive — may temporarily disconnect users"),
        ("💀 Risk 10",      "Destructive — auto-blocked by AI safety gate"),
        ("🔒 Threshold",    "Actions above max_risk_score are auto-skipped"),
        ("📋 Logging",      "All actions written to /home/pi/reports/"),
    ]),
    ("🚀  GETTING STARTED", [
        ("1. Setup",        "Run:  sudo ./setup.sh  (installs all tools & model)"),
        ("2. Config",       "Edit config.ini — set your target IP and model path"),
        ("3. Launch",       "python3 gui.py   OR   sudo python3 main.py (OLED)"),
        ("4. Select buddy", "Pick your Pentest Buddy character on the start screen"),
        ("5. Choose mode",  "Click a mode button or say a voice command"),
        ("6. Report",       "Click 📋 REPORT to export findings to JSON/HTML"),
    ]),
]

TIPS = [
    "💡  Hold SPACE to activate push-to-talk voice input (Button C on hardware)",
    "💡  Say 'full auto' to let the AI chain together the best attack steps",
    "💡  Risk scores above 8 are automatically blocked for your safety",
    "💡  Press F1 at any time to see the full command & voice guide",
    "💡  Reports are saved as JSON + HTML to /home/pi/reports/",
    "💡  Button A = Next item  •  Button B = Back  •  Button C = Voice PTT",
    "💡  Plug in a USB drive to export reports from the hardware OLED interface",
    "💡  The AI uses a local TinyLlama model — no internet connection needed",
    "💡  Run 'Network Recon' first to auto-discover targets on your subnet",
    "💡  All pentest tools require root privileges — run with sudo on the Pi",
    "💡  Edit config.ini to change the LLM model, wordlists, and thresholds",
    "💡  The GUI and OLED interfaces share the same AI core and tool backends",
    "💡  Use 'web pentest' on a target URL to check for SQL injection and more",
    "💡  espeak-ng provides voice output on the Pi — plug in a speaker or earphones",
]


# =============================================================================
# FaceCanvas — Draws and animates the Pentest Buddy character
# =============================================================================
class FaceCanvas(tk.Canvas):
    """
    Canvas widget that draws one of the four Pentest Buddy characters
    and animates them based on the current state.

    States: idle | thinking | talking | happy | alert | scanning
    Characters: ghost | ninja | robot | hacker
    """

    STATES = ("idle", "thinking", "talking", "happy", "alert", "scanning")

    def __init__(self, parent, character_key: str = "ghost",
                 size: int = 220, **kwargs):
        kwargs.setdefault("bg", T["bg"])
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(parent, width=size, height=size, **kwargs)

        self._key    = character_key
        self._char   = CHARACTERS[character_key]
        self._size   = size
        self._state  = "idle"
        self._frame  = 0
        self._blink  = 0          # Frames until next blink
        self._mouth_open = False
        self._eye_dx = 0          # Eye horizontal offset (scanning)
        self._running = True
        self._after_id = None

        self._reset_blink()
        self._tick()

    # ── Public API ─────────────────────────────────────────────────────────────
    def set_character(self, key: str) -> None:
        self._key  = key
        self._char = CHARACTERS[key]
        self._draw()

    def set_state(self, state: str) -> None:
        if state in self.STATES:
            self._state = state
            self._frame = 0
            self._mouth_open = False

    def stop(self) -> None:
        self._running = False
        if self._after_id:
            self.after_cancel(self._after_id)

    # ── Animation loop ─────────────────────────────────────────────────────────
    def _reset_blink(self) -> None:
        """Schedule next blink at a random interval (2-4 s at 10 fps)."""
        self._blink = random.randint(20, 40)

    def _tick(self) -> None:
        if not self._running:
            return
        self._frame += 1
        self._blink -= 1

        # Mouth talking toggle
        if self._state == "talking":
            self._mouth_open = (self._frame % 5) < 3

        # Scanning eye drift
        if self._state == "scanning":
            self._eye_dx = int(10 * math.sin(self._frame * 0.25))
        else:
            self._eye_dx = 0

        self._draw()
        self._after_id = self.after(100, self._tick)

    # ── Draw dispatch ──────────────────────────────────────────────────────────
    def _draw(self) -> None:
        self.delete("all")
        s   = self._size
        cx  = s // 2
        cy  = s // 2
        r   = int(s * 0.37)
        char = self._char

        dispatch = {
            "ghost":  self._draw_ghost,
            "ninja":  self._draw_ninja,
            "robot":  self._draw_robot,
            "hacker": self._draw_hacker,
        }
        fn = dispatch.get(self._key)
        if fn:
            fn(cx, cy, r, char)

    # ── Eye helpers ────────────────────────────────────────────────────────────
    def _eye_params(self):
        """Return (blinking: bool, squint: float 0-2)."""
        blinking = (self._blink <= 0)
        if blinking:
            self._reset_blink()
        squint = {
            "idle":     1.0,
            "thinking": 0.5,
            "talking":  0.9,
            "happy":    0.25,
            "alert":    1.6,
            "scanning": 1.0,
        }.get(self._state, 1.0)
        return blinking, squint

    # ── Ghost ──────────────────────────────────────────────────────────────────
    def _draw_ghost(self, cx: int, cy: int, r: int, char: dict) -> None:
        blinking, squint = self._eye_params()
        fc   = char["face_color"]
        ec   = char["eye_color"]
        glow = char["color"]
        s    = self._size

        # Soft glow rings
        for i in range(4, 0, -1):
            c = self._blend(glow, T["bg"], i / 5.0)
            self.create_oval(cx - r - i * 4, cy - r - i * 3,
                             cx + r + i * 4, cy + r + i * 5,
                             fill=c, outline="")

        # Ghost body — rounded top, wavy bottom
        pts = []
        for a in range(180, 361):
            rad = math.radians(a)
            pts += [cx + r * math.cos(rad), cy + int(r * 0.88) * math.sin(rad)]
        # Wavy bottom edge (3 humps)
        n = 4
        step = (2 * r) // n
        for i in range(n + 1):
            wx = cx - r + i * step
            wy = cy + int(r * 0.88) + (int(r * 0.2) if i % 2 == 0 else -int(r * 0.2))
            pts += [wx, wy]
        self.create_polygon(pts, fill=fc, outline=glow, width=2, smooth=True)

        # Eyes
        ew = int(r * 0.23)
        eh = max(3, int(r * 0.2 * squint))
        ex1 = cx - int(r * 0.31) + self._eye_dx
        ex2 = cx + int(r * 0.31) + self._eye_dx
        ey  = cy - int(r * 0.08)

        for ex in (ex1, ex2):
            if blinking or self._state == "happy":
                # Closed / happy arc
                self.create_arc(ex - ew, ey, ex + ew, ey + ew,
                                start=0, extent=180, fill=ec, outline=ec)
            else:
                self.create_oval(ex - ew, ey - eh, ex + ew, ey + eh,
                                 fill=ec, outline=glow, width=1)
                pw = max(3, ew // 2)
                self.create_oval(ex - pw // 2, ey - pw // 2,
                                 ex + pw // 2, ey + pw // 2,
                                 fill=T["bg"], outline="")

        # Mouth
        mx, my = cx, cy + int(r * 0.38)
        mw, mh = int(r * 0.32), int(r * 0.16)
        if self._mouth_open or self._state == "alert":
            self.create_oval(mx - mw, my - mh, mx + mw, my + mh,
                             fill=T["bg"], outline=glow, width=2)
        elif self._state in ("happy", "success"):
            self.create_arc(mx - mw, my - mh, mx + mw, my + mh,
                            start=200, extent=140, style=tk.ARC,
                            outline=glow, width=3)
        else:
            self.create_arc(mx - mw, my - mh // 2, mx + mw, my + mh // 2,
                            start=210, extent=120, style=tk.ARC,
                            outline=glow, width=2)

        # Thinking bubble
        if self._state == "thinking":
            self._thought_bubble(cx + r + 5, cy - r + 10, glow)

        # Character label badge
        self._draw_name_badge(cx, s - 18, char["name"], glow)

    # ── Ninja ──────────────────────────────────────────────────────────────────
    def _draw_ninja(self, cx: int, cy: int, r: int, char: dict) -> None:
        blinking, squint = self._eye_params()
        ec   = char["eye_color"]
        glow = char["color"]
        s    = self._size

        # Shadow glow
        for i in range(3, 0, -1):
            c = self._blend(glow, T["bg"], i / 4.0)
            self.create_oval(cx - r - i * 3, cy - r - i * 3,
                             cx + r + i * 3, cy + r + i * 3,
                             fill=c, outline="")

        # Face circle (dark)
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=char["face_color"], outline="#334455", width=2)

        # Red headband
        band_y = cy - int(r * 0.28)
        self.create_rectangle(cx - r - 2, band_y - 9, cx + r + 2, band_y + 9,
                              fill="#bb0000", outline="#ff2222", width=1)
        # Headband knot (right side)
        kx = cx + r
        self.create_oval(kx - 6, band_y - 12, kx + 18, band_y + 12,
                         fill="#990000", outline="#ff2222")
        # Trailing ribbons
        self.create_line(kx + 18, band_y - 6, kx + 36, band_y - 22,
                         fill="#bb0000", width=2)
        self.create_line(kx + 18, band_y + 6, kx + 36, band_y + 18,
                         fill="#bb0000", width=2)

        # Eyes (narrow slits)
        ew  = int(r * 0.23)
        eh  = max(3, int(r * 0.07 * squint))
        ex1 = cx - int(r * 0.3) + self._eye_dx
        ex2 = cx + int(r * 0.3) + self._eye_dx
        ey  = cy - int(r * 0.04)

        for ex in (ex1, ex2):
            self.create_oval(ex - ew, ey - max(5, eh),
                             ex + ew, ey + max(5, eh),
                             fill=ec, outline="#ff6666", width=1)
            if not blinking:
                self.create_oval(ex - 3, ey - max(3, eh - 1),
                                 ex + 3, ey + max(3, eh - 1),
                                 fill="#000000", outline="")

        # Face mask (lower half)
        mask_top = cy + int(r * 0.12)
        self.create_rectangle(cx - r + 4, mask_top,
                              cx + r - 4, cy + r - 5,
                              fill="#0d1a20", outline="#334455")
        for i in range(3):
            ly = mask_top + 9 + i * 9
            self.create_line(cx - r + 8, ly, cx + r - 8, ly,
                             fill="#334455", width=1)

        # Open-mouth slit when talking or alert
        if self._mouth_open or self._state == "alert":
            self.create_oval(cx - int(r * 0.2), cy + int(r * 0.4),
                             cx + int(r * 0.2), cy + int(r * 0.6),
                             fill="#000000", outline="#ff2222", width=1)

        if self._state == "thinking":
            self._thought_bubble(cx + r + 5, cy - r + 10, glow)

        self._draw_name_badge(cx, s - 18, char["name"], glow)

    # ── Robot ──────────────────────────────────────────────────────────────────
    def _draw_robot(self, cx: int, cy: int, r: int, char: dict) -> None:
        blinking, squint = self._eye_params()
        ec   = char["eye_color"]
        glow = char["color"]
        fc   = char["face_color"]
        s    = self._size

        # Glow
        for i in range(3, 0, -1):
            c = self._blend(glow, T["bg"], i / 4.0)
            self.create_rectangle(cx - r - i * 4, cy - r - i * 3,
                                  cx + r + i * 4, cy + r + i * 3,
                                  fill=c, outline="")

        # Rectangular head
        self.create_rectangle(cx - r, cy - r, cx + r, cy + r,
                              fill=fc, outline=glow, width=2)

        # Corner rivets
        for rx, ry in [(cx - r + 7, cy - r + 7), (cx + r - 7, cy - r + 7),
                       (cx - r + 7, cy + r - 7), (cx + r - 7, cy + r - 7)]:
            self.create_oval(rx - 4, ry - 4, rx + 4, ry + 4,
                             fill="#334455", outline=glow)

        # Antenna
        ant_x, ant_y = cx, cy - r
        self.create_line(ant_x, ant_y, ant_x, ant_y - 22, fill=glow, width=2)
        blink_col = "#ff3300" if (self._frame % 10) < 5 else "#ff6600"
        self.create_oval(ant_x - 6, ant_y - 30, ant_x + 6, ant_y - 18,
                         fill=blink_col, outline="#ff4400")

        # LED eye screens
        ew  = int(r * 0.2)
        eh  = int(r * 0.17)
        ex1 = cx - int(r * 0.34) + self._eye_dx
        ex2 = cx + int(r * 0.34) + self._eye_dx
        ey  = cy - int(r * 0.14)

        for ex in (ex1, ex2):
            self.create_rectangle(ex - ew, ey - eh, ex + ew, ey + eh,
                                  fill="#001122", outline=ec, width=2)
            if blinking or self._state == "happy":
                self.create_rectangle(ex - ew + 3, ey - 2, ex + ew - 3, ey + 2,
                                      fill=ec, outline="")
            elif self._state == "alert":
                self.create_line(ex - ew + 4, ey - eh + 4,
                                 ex + ew - 4, ey + eh - 4,
                                 fill="#ff0000", width=2)
                self.create_line(ex + ew - 4, ey - eh + 4,
                                 ex - ew + 4, ey + eh - 4,
                                 fill="#ff0000", width=2)
            else:
                dots = [(-ew//3, -eh//3), (ew//3, -eh//3),
                        (-ew//3, eh//3), (ew//3, eh//3)]
                c = ec if squint > 0.8 else T["bg3"]
                for dx, dy in dots:
                    self.create_oval(ex + dx - 2, ey + dy - 2,
                                     ex + dx + 2, ey + dy + 2,
                                     fill=c, outline="")

        # Speaker-grille mouth
        my = cy + int(r * 0.28)
        mw = int(r * 0.42)
        self.create_rectangle(cx - mw, my - 9, cx + mw, my + 9,
                              fill="#001122", outline=glow, width=1)
        n_bars = 7
        for i in range(n_bars):
            bx = cx - mw + 5 + i * ((mw * 2 - 10) // n_bars)
            c  = ec if self._mouth_open else "#1a3355"
            self.create_line(bx, my - 6, bx, my + 6, fill=c, width=2)

        if self._state == "thinking":
            self._thought_bubble(cx + r + 5, cy - r + 10, glow)

        self._draw_name_badge(cx, s - 18, char["name"], glow)

    # ── Hacker / Skull ─────────────────────────────────────────────────────────
    def _draw_hacker(self, cx: int, cy: int, r: int, char: dict) -> None:
        blinking, squint = self._eye_params()
        ec   = char["eye_color"]
        glow = char["color"]
        fc   = char["face_color"]
        s    = self._size

        # Green glow effect
        for i in range(5, 0, -1):
            c = self._blend(glow, T["bg"], i / 6.5)
            self.create_oval(cx - r - i * 3, cy - r - i * 3,
                             cx + r + i * 3, cy + r + i * 3,
                             fill=c, outline="")

        # Skull cranium
        self.create_oval(cx - r, cy - r, cx + r, cy + int(r * 0.65),
                         fill=fc, outline=glow, width=2)

        # Jaw
        jaw_y = cy + int(r * 0.35)
        self.create_rectangle(cx - int(r * 0.62), jaw_y,
                              cx + int(r * 0.62), cy + int(r * 0.75),
                              fill=fc, outline=glow, width=1)

        # Eye sockets — glowing
        ew  = int(r * 0.22)
        ey  = cy - int(r * 0.1)
        ex1 = cx - int(r * 0.3) + self._eye_dx
        ex2 = cx + int(r * 0.3) + self._eye_dx

        for ex in (ex1, ex2):
            # Dark socket
            self.create_oval(ex - ew - 3, ey - ew - 3,
                             ex + ew + 3, ey + ew + 3,
                             fill=T["bg"], outline=glow, width=1)
            if not blinking:
                eh_val = max(4, int(ew * squint))
                # Pulsing glow fill
                pulse = 0.65 + 0.35 * math.sin(self._frame * 0.4)
                pc = self._blend(ec, T["bg"], 1.0 - pulse)
                self.create_oval(ex - ew, ey - eh_val, ex + ew, ey + eh_val,
                                 fill=pc, outline=ec, width=1)
                if self._state != "happy":
                    self.create_oval(ex - 4, ey - 4, ex + 4, ey + 4,
                                     fill=ec, outline="")

        # Nose cavity
        self.create_polygon(
            [cx, cy + int(r * 0.18),
             cx - 7, cy + int(r * 0.35),
             cx + 7, cy + int(r * 0.35)],
            fill=T["bg"], outline=glow, width=1)

        # Teeth row
        my   = cy + int(r * 0.48)
        tw   = int(r * 0.55)
        mh   = int(r * 0.25) if (self._mouth_open or self._state == "alert") \
               else int(r * 0.13)
        self.create_rectangle(cx - tw, my, cx + tw, my + mh,
                              fill=T["bg"], outline=glow, width=1)
        n_teeth = 5
        tooth_w = (tw * 2) // n_teeth
        for i in range(1, n_teeth):
            tx = cx - tw + i * tooth_w
            self.create_line(tx, my, tx, my + mh // 2, fill=glow, width=1)

        if self._state == "thinking":
            self._thought_bubble(cx + r + 5, cy - r + 10, glow)

        self._draw_name_badge(cx, s - 18, char["name"], glow)

    # ── Shared decorators ──────────────────────────────────────────────────────
    def _thought_bubble(self, x: int, y: int, color: str) -> None:
        sizes = [(x + 8, y + 22, 4), (x + 20, y + 9, 7), (x + 36, y - 5, 12)]
        for i, (bx, by, br) in enumerate(sizes):
            c = self._blend(color, T["bg"], 1.0 - (0.25 + i * 0.32))
            self.create_oval(bx - br, by - br, bx + br, by + br,
                             fill=c, outline=color, width=1)

    def _draw_name_badge(self, cx: int, y: int, name: str, color: str) -> None:
        self.create_text(cx, y, text=name, fill=color,
                         font=("Courier", 9, "bold"), anchor="center")

    # ── Color blending util ────────────────────────────────────────────────────
    @staticmethod
    def _blend(hex1: str, hex2: str, t: float) -> str:
        """Blend hex1→hex2. t=0 = hex1, t=1 = hex2."""
        try:
            r1, g1, b1 = int(hex1[1:3], 16), int(hex1[3:5], 16), int(hex1[5:7], 16)
            r2, g2, b2 = int(hex2[1:3], 16), int(hex2[3:5], 16), int(hex2[5:7], 16)
            t = max(0.0, min(1.0, t))
            return (f"#{int(r1 + (r2 - r1) * t):02x}"
                    f"{int(g1 + (g2 - g1) * t):02x}"
                    f"{int(b1 + (b2 - b1) * t):02x}")
        except Exception:
            return hex1


# =============================================================================
# BuddyGUI — Main Application Window
# =============================================================================
class BuddyGUI:
    """
    Top-level desktop GUI for NxtGenAI / PentestGPT-lite.

    Shows a character selection screen on first run, then the main
    mission-control interface with an animated pentest buddy.
    """

    def __init__(self, cfg: configparser.ConfigParser):
        self.cfg           = cfg
        self._char_key     = "ghost"
        self._ai_core      = None
        self._tools        = None
        self._running_task = False
        self._help_visible = False
        self._tip_idx      = 0
        self._face: FaceCanvas | None = None
        self._phrase_after = None
        self._tip_after    = None

        # Queue for thread→GUI logging
        self._log_q: queue.Queue = queue.Queue()

        # Main window
        self.root = tk.Tk()
        self.root.title("🔐 NxtGenAI — Pentest Buddy")
        self.root.configure(bg=T["bg"])
        self.root.geometry("1050x680")
        self.root.minsize(900, 600)

        # Apply dark ttk style
        self._apply_style()

        # Keyboard bindings
        self.root.bind("<F1>",        lambda e: self._toggle_help())
        self.root.bind("<F5>",        lambda e: self._restart_session())
        self.root.bind("<Control-q>", lambda e: self._quit())
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # Start on character selection
        self._show_character_select()

        # Periodic GUI update from log queue
        self.root.after(100, self._drain_log_queue)

    # ── Style ──────────────────────────────────────────────────────────────────
    def _apply_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".",           background=T["bg"],  foreground=T["fg"])
        style.configure("TFrame",      background=T["bg"])
        style.configure("TLabel",      background=T["bg"],  foreground=T["fg"],
                        font=("Segoe UI", 10))
        style.configure("TButton",     background=T["btn"], foreground=T["fg"],
                        relief="flat", padding=(10, 6),
                        font=("Segoe UI", 10, "bold"))
        style.map("TButton",
                  background=[("active", T["btn_hover"]),
                               ("pressed", T["btn_active"])],
                  foreground=[("active", "#ffffff")])
        style.configure("Title.TLabel", background=T["title_bg"],
                        foreground=T["green"], font=("Courier", 18, "bold"))
        style.configure("Sub.TLabel",   background=T["bg"],
                        foreground=T["fg_dim"], font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#06060f",
                        foreground=T["fg_dim"], font=("Segoe UI", 9))
        style.configure("Accent.TLabel", background=T["bg"],
                        foreground=T["green"], font=("Courier", 11, "bold"))
        style.configure("Danger.TLabel", background=T["bg"],
                        foreground=T["red"], font=("Segoe UI", 10, "bold"))
        style.configure("Heading.TLabel", background=T["bg2"],
                        foreground=T["blue"], font=("Segoe UI", 10, "bold"))
        style.configure("TProgressbar", troughcolor=T["bg3"],
                        background=T["green"], thickness=10)

    # ==========================================================================
    # Screen 1 — Character Selection
    # ==========================================================================
    def _show_character_select(self) -> None:
        """Build the full-window character selection screen."""
        # Clear window
        for w in self.root.winfo_children():
            w.destroy()

        root = self.root

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=T["title_bg"], pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔐  NxtGenAI  —  Pentest Buddy",
                 bg=T["title_bg"], fg=T["green"],
                 font=("Courier", 22, "bold")).pack()
        tk.Label(hdr, text="Choose your AI pentest companion to get started",
                 bg=T["title_bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 11)).pack(pady=(4, 0))

        # ── Character grid ────────────────────────────────────────────────────
        grid = tk.Frame(root, bg=T["bg"], padx=30, pady=20)
        grid.pack(fill="both", expand=True)

        cards: dict[str, tk.Frame] = {}
        face_canvases: list[FaceCanvas] = []

        for col, (key, char) in enumerate(CHARACTERS.items()):
            card = tk.Frame(grid, bg=T["bg3"], relief="flat",
                            highlightthickness=1,
                            highlightbackground=T["border"])
            card.grid(row=0, column=col, padx=12, pady=8, sticky="nsew")
            grid.columnconfigure(col, weight=1)
            cards[key] = card

            # Face preview canvas
            fc = FaceCanvas(card, character_key=key, size=170)
            fc.pack(pady=(14, 6))
            face_canvases.append(fc)

            # Name
            tk.Label(card, text=f"{char['emoji']}  {char['name']}",
                     bg=T["bg3"], fg=char["color"],
                     font=("Courier", 13, "bold")).pack()

            # Personality
            tk.Label(card, text=char["personality"],
                     bg=T["bg3"], fg=T["fg_dim"],
                     font=("Segoe UI", 9), wraplength=190,
                     justify="center").pack(pady=(2, 0))

            # Description
            tk.Label(card, text=f'"{char["desc"]}"',
                     bg=T["bg3"], fg=T["fg"],
                     font=("Segoe UI", 9, "italic"), wraplength=190,
                     justify="center").pack(pady=(4, 8))

            # Select button
            btn = tk.Button(
                card, text=f"  SELECT  {char['emoji']}",
                bg=char["color"], fg="#ffffff",
                font=("Segoe UI", 10, "bold"),
                relief="flat", cursor="hand2",
                activebackground=self._lighten(char["color"]),
                command=lambda k=key, fcs=face_canvases: self._select_char(k, fcs),
            )
            btn.pack(pady=(0, 14), ipadx=6, ipady=4)

        # ── Footer tips ───────────────────────────────────────────────────────
        footer = tk.Frame(root, bg="#06060f", pady=10)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer,
                 text="💡  Press F1 for the full command guide  •  Ctrl+Q to quit",
                 bg="#06060f", fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack()

    def _select_char(self, key: str,
                     face_canvases: list[FaceCanvas]) -> None:
        """User picked a character — stop preview animations and launch main UI."""
        for fc in face_canvases:
            fc.stop()
        self._char_key = key
        self._load_backends()
        self._build_main_ui()

    # ==========================================================================
    # Backend loading
    # ==========================================================================
    def _load_backends(self) -> None:
        """Try to initialise AICore and ToolRunner from config."""
        if _TOOLS_OK:
            try:
                self._tools = ToolRunner(self.cfg)
            except Exception as exc:
                log.warning("ToolRunner init failed: %s", exc)

        if _AI_OK:
            model_path = self.cfg.get("paths", "model",
                                      fallback="/home/pi/models/tinyllama-1.1b-q4_0.gguf")
            n_ctx      = int(self.cfg.get("llm", "n_ctx",      fallback="512"))
            n_threads  = int(self.cfg.get("llm", "n_threads",  fallback="3"))
            # Load in background so UI is not blocked
            threading.Thread(target=self._bg_load_ai,
                             args=(model_path, n_ctx, n_threads),
                             daemon=True, name="ai_load").start()

    def _bg_load_ai(self, model_path: str, n_ctx: int, n_threads: int) -> None:
        try:
            self._ai_core = AICore(model_path, n_ctx, n_threads, self.cfg)
            self._log_q.put(("info", "🤖  AI core loaded — ready for pentest!"))
        except Exception as exc:
            self._log_q.put(("warn", f"⚠️  AI core failed to load: {exc}"))

    # ==========================================================================
    # Screen 2 — Main Interface
    # ==========================================================================
    def _build_main_ui(self) -> None:
        """Construct the main mission-control interface."""
        for w in self.root.winfo_children():
            w.destroy()

        char = CHARACTERS[self._char_key]
        self.root.title(f"🔐 NxtGenAI  —  {char['emoji']} {char['full_name']}")

        # ── Top header bar ─────────────────────────────────────────────────────
        self._build_header()

        # ── Main content (left face panel + right mission panel) ───────────────
        content = tk.Frame(self.root, bg=T["bg"])
        content.pack(fill="both", expand=True, padx=0, pady=0)
        content.columnconfigure(0, weight=0, minsize=270)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._build_character_panel(content)
        self._build_mission_panel(content)

        # ── Bottom status bar ──────────────────────────────────────────────────
        self._build_status_bar()

        # Start tip rotation and idle character phrases
        self._rotate_tip()
        self._idle_phrase()

        # Greet the user
        greeting = CHARACTERS[self._char_key]["greeting"]
        self._log(greeting, "buddy")

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> None:
        char = CHARACTERS[self._char_key]
        hdr  = tk.Frame(self.root, bg=T["title_bg"], pady=10)
        hdr.pack(fill="x")

        # Left: branding
        left = tk.Frame(hdr, bg=T["title_bg"])
        left.pack(side="left", padx=16)
        tk.Label(left, text="🔐  NxtGenAI",
                 bg=T["title_bg"], fg=T["green"],
                 font=("Courier", 16, "bold")).pack(side="left")
        tk.Label(left, text="  Pentest Buddy Suite",
                 bg=T["title_bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 20))

        # Right: utility buttons
        right = tk.Frame(hdr, bg=T["title_bg"])
        right.pack(side="right", padx=16)

        self._make_btn(right, "❓  HELP  (F1)",  self._toggle_help,
                       color=T["blue"]).pack(side="right", padx=4)
        self._make_btn(right, "🔄  RESET  (F5)", self._restart_session,
                       color=T["orange"]).pack(side="right", padx=4)
        self._make_btn(right, "🚪  CHANGE BUDDY",
                       self._show_character_select,
                       color=T["purple"]).pack(side="right", padx=4)

        # Centre: current buddy name tag
        mid = tk.Frame(hdr, bg=T["title_bg"])
        mid.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(mid,
                 text=f"{char['emoji']}  {char['name']}  —  {char['personality']}",
                 bg=T["title_bg"], fg=char["color"],
                 font=("Courier", 11, "bold")).pack()

    # ── Left: Character panel ──────────────────────────────────────────────────
    def _build_character_panel(self, parent: tk.Frame) -> None:
        char   = CHARACTERS[self._char_key]
        panel  = tk.Frame(parent, bg=T["bg2"], width=270)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        panel.grid_propagate(False)

        # Animated face
        self._face = FaceCanvas(panel, character_key=self._char_key, size=220)
        self._face.pack(pady=(18, 8))

        # Buddy status label
        self._buddy_status_var = tk.StringVar(value="💤  Idle — awaiting orders...")
        tk.Label(panel, textvariable=self._buddy_status_var,
                 bg=T["bg2"], fg=char["color"],
                 font=("Courier", 10, "bold"),
                 wraplength=240, justify="center").pack(pady=(0, 6))

        # Separator
        tk.Frame(panel, bg=T["border"], height=1).pack(fill="x", padx=20)

        # ── Companion stats ────────────────────────────────────────────────────
        stats = tk.Frame(panel, bg=T["bg2"])
        stats.pack(fill="x", padx=16, pady=10)

        self._stat_tool_var = tk.StringVar(value="—")
        self._stat_risk_var = tk.StringVar(value="—")
        self._stat_phase_var = tk.StringVar(value="Standby")

        for label, var, col in [
            ("🔧 Active Tool:", self._stat_tool_var,  T["blue"]),
            ("⚡ Phase:",       self._stat_phase_var, T["yellow"]),
        ]:
            row = tk.Frame(stats, bg=T["bg2"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=T["bg2"], fg=T["fg_dim"],
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            tk.Label(row, textvariable=var, bg=T["bg2"], fg=col,
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left")

        # Risk bar
        tk.Frame(panel, bg=T["border"], height=1).pack(fill="x", padx=20, pady=(4, 0))
        risk_row = tk.Frame(panel, bg=T["bg2"])
        risk_row.pack(fill="x", padx=16, pady=(6, 2))
        tk.Label(risk_row, text="⚠️ Risk Level:", bg=T["bg2"], fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self._risk_lbl_var = tk.StringVar(value="—")
        tk.Label(risk_row, textvariable=self._risk_lbl_var,
                 bg=T["bg2"], fg=T["orange"],
                 font=("Segoe UI", 9, "bold")).pack(side="right")

        self._risk_bar = tk.Canvas(panel, bg=T["bg3"], height=14,
                                   highlightthickness=0)
        self._risk_bar.pack(fill="x", padx=16, pady=(0, 10))
        self._risk_bar_fill = self._risk_bar.create_rectangle(
            0, 0, 0, 14, fill=T["orange"], outline=""
        )

        # ── Quick command reference (mini) ─────────────────────────────────────
        tk.Frame(panel, bg=T["border"], height=1).pack(fill="x", padx=20)
        ref = tk.Frame(panel, bg=T["bg2"])
        ref.pack(fill="x", padx=16, pady=8)
        tk.Label(ref, text="⌨️  Quick Keys",
                 bg=T["bg2"], fg=T["fg_dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        for keys, desc in [("SPACE", "Push-to-Talk"),
                            ("F1",    "Command guide"),
                            ("F5",    "Reset session"),
                            ("Ctrl+Q","Quit")]:
            kr = tk.Frame(ref, bg=T["bg2"])
            kr.pack(fill="x", pady=1)
            tk.Label(kr, text=keys, bg=T["bg3"], fg=T["yellow"],
                     font=("Courier", 8), width=8, relief="flat",
                     padx=3).pack(side="left")
            tk.Label(kr, text=f"  {desc}", bg=T["bg2"], fg=T["fg_dim"],
                     font=("Segoe UI", 8)).pack(side="left")

    # ── Right: Mission control panel ───────────────────────────────────────────
    def _build_mission_panel(self, parent: tk.Frame) -> None:
        panel = tk.Frame(parent, bg=T["bg"])
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        # ── Target row ────────────────────────────────────────────────────────
        tgt_row = tk.Frame(panel, bg=T["bg2"], pady=8)
        tgt_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        tgt_row.columnconfigure(1, weight=1)

        tk.Label(tgt_row, text="🎯  Target:",
                 bg=T["bg2"], fg=T["fg"],
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0,
                                                      padx=(12, 6), pady=4)
        self._target_var = tk.StringVar(value="192.168.1.0/24")
        entry = tk.Entry(tgt_row, textvariable=self._target_var,
                         bg=T["bg3"], fg=T["green"],
                         insertbackground=T["green"],
                         font=("Courier", 11),
                         relief="flat", bd=4)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        # ── AI output log ─────────────────────────────────────────────────────
        log_frame = tk.Frame(panel, bg=T["bg"])
        log_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        log_hdr = tk.Frame(log_frame, bg=T["bg3"], pady=5)
        log_hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(log_hdr, text="📟  AI OUTPUT LOG",
                 bg=T["bg3"], fg=T["blue"],
                 font=("Courier", 10, "bold")).pack(side="left", padx=12)
        self._make_btn(log_hdr, "🗑️  Clear",
                       self._clear_log, color=T["fg_dim"],
                       small=True).pack(side="right", padx=8)

        self._log_text = scrolledtext.ScrolledText(
            log_frame,
            bg="#020208", fg=T["fg"],
            insertbackground=T["green"],
            font=("Courier", 10),
            relief="flat", bd=0,
            state="disabled",
            wrap="word",
            padx=10, pady=8,
        )
        self._log_text.grid(row=1, column=0, sticky="nsew")

        # Tag colours for different message types
        self._log_text.tag_config("buddy",   foreground=CHARACTERS[self._char_key]["color"])
        self._log_text.tag_config("info",    foreground=T["blue"])
        self._log_text.tag_config("success", foreground=T["green"])
        self._log_text.tag_config("warn",    foreground=T["orange"])
        self._log_text.tag_config("error",   foreground=T["red"])
        self._log_text.tag_config("thought", foreground=T["purple"])
        self._log_text.tag_config("action",  foreground=T["yellow"])
        self._log_text.tag_config("dim",     foreground=T["fg_dim"])
        self._log_text.tag_config("ts",      foreground=T["fg_dim"])

        # ── Action buttons ────────────────────────────────────────────────────
        btn_bar = tk.Frame(panel, bg=T["bg3"], pady=10)
        btn_bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 0))
        btn_bar.columnconfigure(tuple(range(6)), weight=1)

        modes = [
            ("🔍\nRECON",    "recon",  T["blue"]),
            ("🌐\nWEB",      "web",    T["green"]),
            ("📡\nWIFI",     "wifi",   T["purple"]),
            ("🔑\nBRUTE",    "brute",  T["orange"]),
            ("🤖\nFULL AUTO","auto",   T["yellow"]),
            ("📋\nREPORT",   "report", T["fg_dim"]),
        ]
        self._mode_buttons = {}
        for col, (label, mode, color) in enumerate(modes):
            b = tk.Button(
                btn_bar, text=label,
                bg=T["bg3"], fg=color,
                activebackground=T["bg4"],
                activeforeground=color,
                font=("Segoe UI", 9, "bold"),
                relief="flat", cursor="hand2",
                padx=6, pady=6,
                command=lambda m=mode: self._run_mode(m),
            )
            b.grid(row=0, column=col, padx=4, sticky="ew")
            b.bind("<Enter>", lambda e, btn=b: btn.config(bg=T["bg4"]))
            b.bind("<Leave>", lambda e, btn=b: btn.config(bg=T["bg3"]))
            self._mode_buttons[mode] = b

        # Voice PTT hint
        tk.Label(btn_bar,
                 text="🎙️  Hold  SPACE  to use voice input",
                 bg=T["bg3"], fg=T["fg_dim"],
                 font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=6,
                                             pady=(4, 0))
        self.root.bind("<space>",
                       lambda e: self._log("🎙️  Push-to-Talk: hold SPACE and speak...", "info"))

        # Help panel placeholder
        self._help_panel: tk.Frame | None = None

    # ── Bottom status bar ──────────────────────────────────────────────────────
    def _build_status_bar(self) -> None:
        bar = tk.Frame(self.root, bg="#06060f", pady=7)
        bar.pack(fill="x", side="bottom")

        self._tip_var = tk.StringVar(value=TIPS[0])
        tk.Label(bar, textvariable=self._tip_var,
                 bg="#06060f", fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left", padx=14)

        tk.Label(bar, text="NxtGenAI v1.0  |  MIT © 2026",
                 bg="#06060f", fg=T["fg_dim"],
                 font=("Segoe UI", 8)).pack(side="right", padx=14)

    # ==========================================================================
    # Help / Command Guide Panel  (F1 toggle)
    # ==========================================================================
    def _toggle_help(self) -> None:
        if self._help_visible:
            self._hide_help()
        else:
            self._show_help()

    def _show_help(self) -> None:
        if self._help_panel:
            return
        self._help_visible = True

        # Build overlay panel on the right side of the window
        self._help_panel = tk.Frame(self.root, bg=T["bg2"], width=380,
                                    highlightthickness=1,
                                    highlightbackground=T["border"])
        self._help_panel.place(relx=1.0, rely=0, anchor="ne",
                               relheight=1.0, width=380)

        hdr = tk.Frame(self._help_panel, bg=T["title_bg"], pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📖  COMMAND & VOICE GUIDE",
                 bg=T["title_bg"], fg=T["blue"],
                 font=("Courier", 11, "bold")).pack(side="left", padx=12)
        tk.Button(hdr, text="✕", bg=T["title_bg"], fg=T["red"],
                  font=("Segoe UI", 12, "bold"), relief="flat",
                  cursor="hand2",
                  command=self._hide_help).pack(side="right", padx=10)

        # Scrollable content
        canvas  = tk.Canvas(self._help_panel, bg=T["bg2"],
                            highlightthickness=0)
        sb      = ttk.Scrollbar(self._help_panel, orient="vertical",
                                command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=T["bg2"])
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))

        for section_title, rows in COMMAND_GUIDE:
            # Section header
            sh = tk.Frame(inner, bg=T["bg3"], pady=4)
            sh.pack(fill="x", padx=8, pady=(10, 2))
            tk.Label(sh, text=section_title,
                     bg=T["bg3"], fg=T["blue"],
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8)

            for key, desc in rows:
                row = tk.Frame(inner, bg=T["bg2"])
                row.pack(fill="x", padx=8, pady=1)
                # Key / command badge
                tk.Label(row, text=key,
                         bg=T["bg3"], fg=T["yellow"],
                         font=("Courier", 9),
                         width=14, anchor="w",
                         padx=6, pady=2).pack(side="left")
                tk.Label(row, text=f"  {desc}",
                         bg=T["bg2"], fg=T["fg"],
                         font=("Segoe UI", 9),
                         anchor="w", justify="left",
                         wraplength=200).pack(side="left", fill="x", expand=True)

        # Footer
        tk.Label(inner,
                 text="\n⚠️  Only test networks you own or have explicit\n"
                      "    written permission to test. Misuse is illegal.\n",
                 bg=T["bg2"], fg=T["red"],
                 font=("Segoe UI", 9, "bold"),
                 justify="center").pack(pady=12)

    def _hide_help(self) -> None:
        self._help_visible = False
        if self._help_panel:
            self._help_panel.destroy()
            self._help_panel = None

    # ==========================================================================
    # Logging — thread-safe via queue
    # ==========================================================================
    def _log(self, message: str, level: str = "info") -> None:
        """Queue a log message for display (safe from any thread)."""
        self._log_q.put((level, message))

    def _append_log(self, message: str, level: str = "info") -> None:
        """Write a message to the scrolled text log widget."""
        widget = self._log_text
        widget.configure(state="normal")

        ts = time.strftime("%H:%M:%S")
        widget.insert("end", f"[{ts}]  ", "ts")
        widget.insert("end", f"{message}\n", level)
        widget.see("end")
        widget.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ==========================================================================
    # Pentest Mode Execution
    # ==========================================================================
    def _run_mode(self, mode: str) -> None:
        if self._running_task:
            self._log("⚠️  A task is already running — please wait!", "warn")
            return

        target = self._target_var.get().strip()
        if not target:
            self._log("❌  Please enter a target before running a mode.", "error")
            return

        if mode == "report":
            self._generate_report()
            return

        self._running_task = True
        self._set_phase(mode.upper())
        self._face.set_state("thinking")
        self._buddy_status_var.set(
            random.choice(CHARACTERS[self._char_key]["thinking"]))

        # Disable buttons while running
        for b in self._mode_buttons.values():
            b.config(state="disabled")

        char = CHARACTERS[self._char_key]
        self._log(f"\n{'─'*52}", "dim")
        self._log(f"{char['emoji']}  Starting mode: {mode.upper()} on {target}", "buddy")
        self._log(f"{'─'*52}\n", "dim")

        threading.Thread(target=self._bg_run_mode,
                         args=(mode, target),
                         daemon=True, name=f"mode_{mode}").start()

    def _bg_run_mode(self, mode: str, target: str) -> None:
        """Background thread: run AI ReAct loop or direct tool call."""
        try:
            if self._ai_core and self._tools and mode == "auto":
                self._log_q.put(("info", "🤖  Engaging AI ReAct loop..."))
                results = self._ai_core.react_loop(
                    task=f"Perform a penetration test on {target}",
                    tools=self._tools,
                    on_step=self._on_react_step,
                )
                self._log_q.put(("success",
                                 f"✅  AI loop complete — {len(results)} steps."))

            elif self._tools:
                self._log_q.put(("info", f"🔧  Running tool for mode: {mode}"))
                self._run_tool_mode(mode, target)
            else:
                # Demo mode — simulated output
                self._demo_run(mode, target)

        except Exception as exc:
            self._log_q.put(("error", f"❌  Error in {mode}: {exc}"))
        finally:
            self._log_q.put(("_done_", mode))

    def _run_tool_mode(self, mode: str, target: str) -> None:
        """Dispatch to a specific ToolRunner method."""
        status_cb = lambda msg: self._log_q.put(("dim", f"   ↳ {msg}"))

        if mode == "recon":
            results = self._tools.network_recon(target=target, status_cb=status_cb)
        elif mode == "web":
            results = self._tools.web_pentest(target=target, status_cb=status_cb)
        elif mode == "wifi":
            results = self._tools.wifi_crack(status_cb=status_cb)
        elif mode == "brute":
            results = self._tools.hydra_brute(target=target, status_cb=status_cb)
        else:
            results = []

        for r in results:
            tool    = r.get("tool", mode)
            success = r.get("success", False)
            risk    = r.get("risk", 0)
            output  = r.get("output", "")[:500]
            level   = "success" if success else "warn"
            self._log_q.put((level,
                             f"{'✅' if success else '❌'}  [{tool}]  "
                             f"Risk:{risk}/10\n{output}"))

    def _on_react_step(self, step: dict) -> None:
        """Callback for each AI ReAct iteration (called from bg thread)."""
        thought = step.get("thought", "")
        action  = step.get("action", "")
        risk    = step.get("risk", 0)
        self._log_q.put(("thought", f"💭  Thought: {thought[:120]}"))
        self._log_q.put(("action",  f"⚡  Action:  {action}  (risk {risk}/10)"))
        self._log_q.put(("_risk_",  risk))

    def _demo_run(self, mode: str, target: str) -> None:
        """Simulated run for when tools/AI are not available (demo/dev mode)."""
        steps = {
            "recon": [
                ("info",    f"🔍  Starting network recon on {target}..."),
                ("dim",     "   ↳ nmap -sn --host-timeout 10s " + target),
                ("dim",     "   ↳ Scanning 256 hosts..."),
                ("success", "✅  Discovered 4 live hosts on the subnet"),
                ("dim",     "   ↳ Running SYN scan on discovered hosts..."),
                ("success", "✅  Open ports found: 22(ssh), 80(http), 443(https)"),
                ("warn",    "⚠️  Host 192.168.1.1 has outdated OpenSSH 7.4"),
            ],
            "web": [
                ("info",    f"🌐  Starting web pentest on {target}..."),
                ("dim",     "   ↳ curl -s -I --max-time 10 " + target),
                ("success", "✅  Headers retrieved — checking security headers..."),
                ("warn",    "⚠️  Missing: X-Frame-Options, Content-Security-Policy"),
                ("dim",     "   ↳ Running sqlmap --level 1 --risk 1 --batch..."),
                ("warn",    "⚠️  Potential SQL injection point found in ?id= parameter"),
                ("success", "✅  Web pentest complete — 2 findings"),
            ],
            "wifi": [
                ("info",    "📡  Starting WiFi crack sequence..."),
                ("dim",     "   ↳ airmon-ng start wlan0"),
                ("success", "✅  Monitor mode enabled on wlan0mon"),
                ("dim",     "   ↳ airodump-ng scanning for networks..."),
                ("success", "✅  Found 3 access points, targeting strongest signal"),
                ("warn",    "⚠️  WPA2 handshake capture in progress (60s timeout)..."),
                ("warn",    "⚠️  No handshake captured — try moving closer to AP"),
            ],
            "brute": [
                ("info",    f"🔑  Starting brute force on {target}..."),
                ("dim",     f"   ↳ hydra -l admin -P 10k-common.txt {target} ssh"),
                ("warn",    "⚠️  Attempting 10,000 passwords (4 threads)..."),
                ("success", "✅  Password found:  admin:password123  🎉"),
            ],
            "auto": [
                ("info",    "🤖  Full-auto AI mode engaged..."),
                ("thought", "💭  Thought: I should start with host discovery"),
                ("action",  "⚡  Action:  nmap_scan({\"target\": \"" + target + "\"})"),
                ("dim",     "   ↳ Executing nmap scan..."),
                ("success", "✅  Observation: Found 3 hosts, port 22 open"),
                ("thought", "💭  Thought: SSH is open, try common credentials"),
                ("action",  "⚡  Action:  hydra_brute({\"target\": \"192.168.1.1\"})"),
                ("dim",     "   ↳ Running Hydra..."),
                ("success", "✅  Observation: Credentials found — admin:admin123"),
                ("thought", "💭  Thought: Task complete — generating report"),
                ("action",  "⚡  Action:  report_done({})"),
                ("success", "✅  AI loop complete — 3 steps executed"),
            ],
        }

        for level, msg in steps.get(mode, [("info", "Mode running...")]):
            time.sleep(random.uniform(0.4, 1.2))
            risk = random.randint(1, 6)
            self._log_q.put((level, msg))
            if level in ("warn", "error"):
                self._log_q.put(("_risk_", risk + 2))
            else:
                self._log_q.put(("_risk_", max(1, risk - 1)))

    def _generate_report(self) -> None:
        self._log("📋  Generating pentest report...", "info")
        self._face.set_state("thinking")
        self._buddy_status_var.set("📋  Compiling findings...")

        def _bg():
            time.sleep(1.5)
            self._log_q.put(("success",
                             "✅  Report saved to /home/pi/reports/report.json"))
            self._log_q.put(("success",
                             "✅  HTML report: /home/pi/reports/report.html"))
            self._log_q.put(("info",
                             "💡  Plug in a USB drive to auto-export on the Pi."))
            self._log_q.put(("_done_", "report"))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_mode_done(self, mode: str) -> None:
        """Called (in main thread) when background task finishes."""
        self._running_task = False
        for b in self._mode_buttons.values():
            b.config(state="normal")
        self._set_phase("Standby")
        self._face.set_state("happy")
        char = CHARACTERS[self._char_key]
        phrase = random.choice(char["success"])
        self._buddy_status_var.set(phrase)
        self._log(f"\n{phrase}", "buddy")
        self._risk_lbl_var.set("—")
        self._update_risk_bar(0, T["green"])
        self.root.after(4000, lambda: self._face.set_state("idle"))

    # ==========================================================================
    # Status helpers
    # ==========================================================================
    def _set_phase(self, phase: str) -> None:
        self._stat_phase_var.set(phase)

    def _set_risk(self, risk: int) -> None:
        if risk < 4:
            color = T["green"]
        elif risk < 7:
            color = T["orange"]
        else:
            color = T["red"]
        self._risk_lbl_var.set(f"{risk}/10")
        self._update_risk_bar(risk, color)

    def _update_risk_bar(self, risk: int, color: str) -> None:
        """Redraw the canvas-based risk bar."""
        try:
            bar = self._risk_bar
            bar.update_idletasks()
            w = bar.winfo_width()
            h = bar.winfo_height() or 14
            if w <= 1:
                w = 200  # fallback before widget is mapped
            fill_w = int(w * risk / 10)
            bar.coords(self._risk_bar_fill, 0, 0, fill_w, h)
            bar.itemconfig(self._risk_bar_fill, fill=color)
        except Exception:
            pass

    # ==========================================================================
    # Periodic callbacks
    # ==========================================================================
    def _rotate_tip(self) -> None:
        """Rotate the status bar tip every 6 seconds."""
        self._tip_idx = (self._tip_idx + 1) % len(TIPS)
        self._tip_var.set(TIPS[self._tip_idx])
        self._tip_after = self.root.after(6000, self._rotate_tip)

    def _idle_phrase(self) -> None:
        """Show a random idle character phrase when not running."""
        if not self._running_task and self._face:
            char = CHARACTERS[self._char_key]
            phrase = random.choice(char["idle"])
            if self._buddy_status_var.get() != phrase:
                self._buddy_status_var.set(phrase)
        interval = random.randint(8000, 14000)
        self._phrase_after = self.root.after(interval, self._idle_phrase)

    def _drain_log_queue(self) -> None:
        try:
            while True:
                item = self._log_q.get_nowait()
                level, payload = item
                if level == "_done_":
                    self._on_mode_done(payload)
                elif level == "_risk_":
                    self._set_risk(int(payload))
                else:
                    self._append_log(payload, level)
        except queue.Empty:
            pass
        self.root.after(120, self._drain_log_queue)

    # ==========================================================================
    # Session management
    # ==========================================================================
    def _restart_session(self) -> None:
        self._running_task = False
        if self._phrase_after:
            self.root.after_cancel(self._phrase_after)
        if self._tip_after:
            self.root.after_cancel(self._tip_after)
        if self._face:
            self._face.stop()
        self._build_main_ui()

    def _quit(self) -> None:
        if self._face:
            self._face.stop()
        self.root.destroy()

    # ==========================================================================
    # Utility helpers
    # ==========================================================================
    def _make_btn(self, parent: tk.Widget, text: str,
                  command, color: str = T["blue"],
                  small: bool = False) -> tk.Button:
        fs = 8 if small else 9
        btn = tk.Button(
            parent, text=text, command=command,
            bg=T["btn"], fg=color,
            activebackground=T["btn_hover"],
            activeforeground=color,
            font=("Segoe UI", fs, "bold"),
            relief="flat", cursor="hand2",
            padx=6 if small else 10, pady=3 if small else 5,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=T["btn_hover"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=T["btn"]))
        return btn

    @staticmethod
    def _lighten(hex_color: str) -> str:
        """Return a slightly lighter version of the given hex colour."""
        try:
            r = min(255, int(hex_color[1:3], 16) + 40)
            g = min(255, int(hex_color[3:5], 16) + 40)
            b = min(255, int(hex_color[5:7], 16) + 40)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    # ==========================================================================
    # Entry point
    # ==========================================================================
    def run(self) -> None:
        """Start the Tkinter event loop."""
        self.root.mainloop()


# =============================================================================
# CLI entry point
# =============================================================================
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Parse --config flag
    cfg_path = "config.ini"
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            cfg_path = sys.argv[idx + 1]

    # Resolve config relative to this script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(cfg_path):
        cfg_path = os.path.join(script_dir, cfg_path)

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if os.path.exists(cfg_path):
        cfg.read(cfg_path)
        log.info("Loaded config from %s", cfg_path)
    else:
        log.warning("config.ini not found at %s — using defaults.", cfg_path)

    app = BuddyGUI(cfg)
    app.run()


if __name__ == "__main__":
    main()
