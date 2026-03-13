#!/usr/bin/env python3
# =============================================================================
# PentestGPT-lite — OLED Display Driver
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Manages:
#   - SSD1306 128×64 OLED via I2C (adafruit-circuitpython-ssd1306)
#   - Button inputs: A (GPIO 21), B (GPIO 20), C (GPIO 16) — Waveshare Play Hat
#   - Joystick: UP (GPIO 6), DOWN (GPIO 19), LEFT (GPIO 5), RIGHT (GPIO 26),
#               SELECT/push (GPIO 13) — Waveshare Play Hat pinout
#   - All draw calls are double-buffered (<1 s refresh, non-blocking)
#   - Animations: frame-by-frame splash, progress bar, scrolling text
#
# GPIO assignments (Waveshare Play Hat, BCM numbering):
#   Button A  → GPIO 21   Button B  → GPIO 20   Button C  → GPIO 16
#   Joystick Up   → GPIO 6    Down → GPIO 19   Left → GPIO 5
#   Joystick Right → GPIO 26  Select → GPIO 13
# =============================================================================

import configparser
import logging
import queue
import time
import threading
from typing import Optional

log = logging.getLogger(__name__)

# Optional hardware imports — gracefully degrade if not on Pi
try:
    import board
    import busio
    import adafruit_ssd1306
    from PIL import Image, ImageDraw
    _HW_AVAILABLE = True
except ImportError:
    log.warning("Adafruit SSD1306 libs not found — running in headless mode.")
    _HW_AVAILABLE = False

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    log.warning("RPi.GPIO not found — button/joystick input disabled.")
    _GPIO_AVAILABLE = False


# =============================================================================
# GPIO pin assignments (BCM numbering — Waveshare Play Hat)
# =============================================================================
PIN_BTN_A     = 21   # Button A (leftmost)
PIN_BTN_B     = 20   # Button B (middle)
PIN_BTN_C     = 16   # Button C (right)
PIN_JOY_UP    = 6    # Joystick Up
PIN_JOY_DOWN  = 19   # Joystick Down
PIN_JOY_LEFT  = 5    # Joystick Left
PIN_JOY_RIGHT = 26   # Joystick Right
PIN_JOY_SEL   = 13   # Joystick push (SELECT)

# Map GPIO pin → event name (used in event queue)
_PIN_TO_EVENT: dict[int, str] = {
    PIN_BTN_A:     "A",
    PIN_BTN_B:     "B",
    PIN_BTN_C:     "C",
    PIN_JOY_UP:    "UP",
    PIN_JOY_DOWN:  "DOWN",
    PIN_JOY_LEFT:  "LEFT",
    PIN_JOY_RIGHT: "RIGHT",
    PIN_JOY_SEL:   "SELECT",
}

# All input pins in one list for easy setup
_ALL_INPUT_PINS = list(_PIN_TO_EVENT.keys())

# Display dimensions (SSD1306 on Waveshare Play Hat)
OLED_WIDTH  = 128
OLED_HEIGHT = 64

# Font sizes — PIL default bitmap font (no TTF needed, works offline)
FONT_SMALL = None   # Loaded in __init__; default PIL font is 8px


# =============================================================================
# OLEDDisplay class
# =============================================================================
class OLEDDisplay:
    """
    Full OLED driver with double-buffering, button/joystick input queue,
    and pre-built UI primitives for PentestGPT-lite.

    If hardware is not available (non-Pi host), all draw calls are no-ops
    and poll_event() returns None — enabling headless testing.
    """

    def __init__(self, cfg: configparser.ConfigParser):
        self._cfg = cfg
        self._hw  = _HW_AVAILABLE and _GPIO_AVAILABLE

        # Shared event queue: GPIO callbacks push; poll_event() pops
        self._event_q: queue.Queue[str] = queue.Queue(maxsize=8)

        # PIL image buffer (drawn off-screen, pushed to OLED in refresh())
        self._image  = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)
        self._draw   = ImageDraw.Draw(self._image)

        # OLED device handle
        self._oled: Optional[object] = None

        # Brightness (0–255) — adjusted by power.py via set_brightness()
        self._brightness = int(cfg.get("oled", "brightness_normal", fallback="200"))

        # Thread lock to protect PIL image buffer from concurrent writes
        self._lock = threading.Lock()

        if self._hw:
            self._init_hardware()
        else:
            log.info("OLEDDisplay running in headless/stub mode.")

    # ── Hardware init ─────────────────────────────────────────────────────────
    def _init_hardware(self) -> None:
        """Initialise I2C bus, SSD1306 device, and GPIO inputs."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._oled = adafruit_ssd1306.SSD1306_I2C(
                OLED_WIDTH, OLED_HEIGHT, i2c,
                addr=int(self._cfg.get("oled", "i2c_address", fallback="0x3C"), 16),
            )
            self._oled.fill(0)
            self._oled.show()
            log.info("SSD1306 OLED ready at I2C 0x%02X.",
                     int(self._cfg.get("oled", "i2c_address", fallback="0x3C"), 16))
        except Exception as exc:
            log.error("SSD1306 init failed: %s", exc)
            self._oled = None

        # GPIO setup
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in _ALL_INPUT_PINS:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                # Falling edge = button pressed (active-low with pull-up)
                GPIO.add_event_detect(
                    pin, GPIO.FALLING,
                    callback=self._gpio_callback,
                    bouncetime=150,  # 150 ms debounce
                )
            log.info("GPIO inputs configured: %s", _ALL_INPUT_PINS)
        except Exception as exc:
            log.warning("GPIO setup failed: %s — input events disabled.", exc)

    def _gpio_callback(self, pin: int) -> None:
        """
        ISR called by RPi.GPIO on falling edge.
        Pushes event name to queue (non-blocking; drops if queue full).
        """
        event = _PIN_TO_EVENT.get(pin)
        if event:
            try:
                self._event_q.put_nowait(event)
            except queue.Full:
                pass  # Drop event rather than block the ISR

    # ── Event polling ─────────────────────────────────────────────────────────
    def poll_event(self) -> Optional[str]:
        """
        Non-blocking event poll.
        Returns event string ("UP", "A", "SELECT", …) or None if no event.
        """
        try:
            return self._event_q.get_nowait()
        except queue.Empty:
            return None

    # ── Internal draw helpers ─────────────────────────────────────────────────
    def _clear_buf(self) -> None:
        """Clear PIL image buffer to black."""
        self._draw.rectangle((0, 0, OLED_WIDTH, OLED_HEIGHT), fill=0)

    def _text(self, x: int, y: int, text: str, fill: int = 1) -> None:
        """Draw text to buffer. fill=1 = white, fill=0 = black."""
        self._draw.text((x, y), text, font=FONT_SMALL, fill=fill)

    def _hline(self, y: int) -> None:
        """Draw a full-width horizontal line."""
        self._draw.line((0, y, OLED_WIDTH - 1, y), fill=1)

    def _bar(self, x: int, y: int, w: int, h: int,
             filled_pct: float, fill: int = 1) -> None:
        """
        Draw a progress/battery bar.
        filled_pct: 0.0–1.0
        """
        # Outline
        self._draw.rectangle((x, y, x + w, y + h), outline=1, fill=0)
        # Filled portion
        filled_w = int(w * max(0.0, min(1.0, filled_pct)))
        if filled_w > 0:
            self._draw.rectangle((x + 1, y + 1, x + filled_w, y + h - 1), fill=fill)

    def refresh(self) -> None:
        """Push PIL image buffer to physical OLED (thread-safe)."""
        if self._oled is None:
            return
        with self._lock:
            self._oled.image(self._image)
            self._oled.show()

    def clear(self) -> None:
        """Clear display to black."""
        with self._lock:
            self._clear_buf()
        self.refresh()

    def set_brightness(self, level: int) -> None:
        """
        Adjust OLED contrast/brightness (0–255).
        Called by power.py when battery is low.
        """
        self._brightness = max(0, min(255, level))
        if self._oled:
            try:
                self._oled.contrast(self._brightness)
            except Exception as exc:
                log.debug("Brightness set failed: %s", exc)

    # ── Animated boot splash ──────────────────────────────────────────────────
    def show_splash(self) -> None:
        """
        Multi-frame animated boot splash.
        Frame 1: blank → Frame 2: border → Frame 3: title → Frame 4: tagline
        Each frame shown for ~200 ms to achieve smooth 5 fps animation.
        """
        frames = [
            self._splash_frame_1,
            self._splash_frame_2,
            self._splash_frame_3,
            self._splash_frame_4,
        ]
        for frame_fn in frames:
            with self._lock:
                self._clear_buf()
                frame_fn()
            self.refresh()
            time.sleep(0.25)

    def _splash_frame_1(self) -> None:
        """Frame 1: corners only."""
        self._draw.rectangle((0, 0, 3, 3), fill=1)
        self._draw.rectangle((OLED_WIDTH - 4, 0, OLED_WIDTH - 1, 3), fill=1)
        self._draw.rectangle((0, OLED_HEIGHT - 4, 3, OLED_HEIGHT - 1), fill=1)
        self._draw.rectangle((OLED_WIDTH - 4, OLED_HEIGHT - 4,
                               OLED_WIDTH - 1, OLED_HEIGHT - 1), fill=1)

    def _splash_frame_2(self) -> None:
        """Frame 2: full border."""
        self._draw.rectangle((0, 0, OLED_WIDTH - 1, OLED_HEIGHT - 1),
                              outline=1, fill=0)

    def _splash_frame_3(self) -> None:
        """Frame 3: border + title."""
        self._draw.rectangle((0, 0, OLED_WIDTH - 1, OLED_HEIGHT - 1),
                              outline=1, fill=0)
        self._text(14, 18, "PentestGPT-lite")

    def _splash_frame_4(self) -> None:
        """Frame 4: border + title + tagline + shield icon."""
        self._draw.rectangle((0, 0, OLED_WIDTH - 1, OLED_HEIGHT - 1),
                              outline=1, fill=0)
        self._text(14, 16, "PentestGPT-lite")
        self._hline(27)
        self._text(20, 30, "AI Pentester")
        self._text(28, 42, "v1.0.0")
        # Draw tiny shield (5×7 px) in top-left of content area
        self._draw.polygon([(4, 5), (11, 5), (11, 10), (7, 14), (4, 10)], fill=1)

    # ── Loading screen ────────────────────────────────────────────────────────
    def show_loading(self, message: str) -> None:
        """
        Show a loading screen with animated progress dots.
        Called every 200 ms during LLM init — non-blocking.
        """
        # Animate a spinner: cycle through |/-\ characters
        t    = int(time.monotonic() * 4) % 4
        spin = r"|/-\\"[t]
        with self._lock:
            self._clear_buf()
            self._draw.rectangle((0, 0, OLED_WIDTH - 1, OLED_HEIGHT - 1),
                                  outline=1, fill=0)
            self._text(4, 8, "Loading AI...")
            self._text(4, 20, message[:20])
            self._text(60, 44, spin)
            # Progress bar (fills over 120 s based on elapsed seconds in message)
            try:
                elapsed = int("".join(filter(str.isdigit, message.split()[-1])))
                pct     = min(1.0, elapsed / 120.0)
            except (ValueError, IndexError):
                pct = 0.1
            self._bar(4, 52, 120, 8, pct)
        self.refresh()

    # ── Main menu ─────────────────────────────────────────────────────────────
    def show_menu(self, title: str, items: list, selected: int,
                  battery_pct: Optional[int] = None) -> None:
        """
        Render the main menu.
        Selected item is inverted (black text on white background).
        Battery % shown in bottom-right corner.
        """
        with self._lock:
            self._clear_buf()
            # Title bar
            self._draw.rectangle((0, 0, OLED_WIDTH - 1, 10), fill=1)
            self._text(2, 1, title[:20], fill=0)  # Inverted text on title bar

            # Menu items (max 4 visible, 10 px each row)
            visible_start = max(0, selected - 3)
            for i, item in enumerate(items[visible_start: visible_start + 4]):
                real_idx  = visible_start + i
                y         = 12 + i * 12
                is_sel    = (real_idx == selected)
                if is_sel:
                    # Highlight: white background box
                    self._draw.rectangle((0, y - 1, OLED_WIDTH - 24, y + 9), fill=1)
                    self._text(2, y, f">{item[:17]}", fill=0)
                else:
                    self._text(2, y, f" {item[:17]}", fill=1)

            # Battery indicator (bottom-right corner)
            if battery_pct is not None:
                batt_str = f"{battery_pct}%"
                self._text(OLED_WIDTH - len(batt_str) * 6 - 2, OLED_HEIGHT - 9,
                           batt_str)
                # Tiny battery bar (20×5 px)
                self._bar(OLED_WIDTH - 22, OLED_HEIGHT - 9, 20, 7,
                          battery_pct / 100.0)

        self.refresh()

    # ── Status / message screen ───────────────────────────────────────────────
    def show_message(self, title: str, body: str) -> None:
        """Display a two-line status screen (title + body)."""
        with self._lock:
            self._clear_buf()
            self._draw.rectangle((0, 0, OLED_WIDTH - 1, 10), fill=1)
            self._text(2, 1, title[:20], fill=0)
            self._text(4, 16, body[:20])
        self.refresh()

    # ── ReAct step display ────────────────────────────────────────────────────
    def show_react_step(self, thought: str, action: str, risk: int) -> None:
        """
        Display current AI ReAct step.
        Risk score colour-coded:
          1–3 → white (safe)
          4–6 → bordered box (caution)
          7–10 → inverted (danger)
        """
        with self._lock:
            self._clear_buf()
            # Header
            self._draw.rectangle((0, 0, OLED_WIDTH - 1, 10), fill=1)
            self._text(2, 1, "AI ReAct", fill=0)

            self._text(0, 13, f"T:{thought[:20]}")
            self._text(0, 24, f"A:{action[:20]}")

            # Risk badge
            risk_str = f"Risk: {risk}/10"
            if risk >= 7:
                # High risk: inverted box
                self._draw.rectangle((0, 35, 70, 46), fill=1)
                self._text(2, 36, risk_str, fill=0)
            elif risk >= 4:
                # Medium risk: outlined box
                self._draw.rectangle((0, 35, 70, 46), outline=1, fill=0)
                self._text(2, 36, risk_str)
            else:
                # Low risk: plain text
                self._text(0, 36, risk_str)

        self.refresh()

    # ── Scrollable result view ────────────────────────────────────────────────
    def show_scroll(self, visible_lines: list, pos: int, total: int) -> None:
        """
        Display a scrollable text view.
        Shows up to 4 lines with a scroll indicator on the right edge.
        """
        with self._lock:
            self._clear_buf()
            # Header
            self._draw.rectangle((0, 0, OLED_WIDTH - 1, 10), fill=1)
            self._text(2, 1, "Results", fill=0)
            self._text(80, 1, f"{pos + 1}/{total}", fill=0)

            # Content lines
            for i, line in enumerate(visible_lines[:4]):
                self._text(0, 13 + i * 12, line[:20])

            # Scroll bar on right edge
            if total > 4:
                bar_h   = max(4, int(OLED_HEIGHT * 4 / total))
                bar_y   = 11 + int((OLED_HEIGHT - 11) * pos / max(1, total - 4))
                self._draw.rectangle((OLED_WIDTH - 3, bar_y,
                                      OLED_WIDTH - 1, bar_y + bar_h), fill=1)

        self.refresh()

    # ── Text prompt (for entering target URLs etc.) ───────────────────────────
    def prompt_text(self, label: str) -> Optional[str]:
        """
        Very simple text entry: cycles through chars with joystick.
        In practice, users set targets in config.ini or via SSH.
        Returns None if user cancels (Button B).
        """
        # On hardware without a keyboard, we just return None to use the default
        log.info("Text prompt ('%s') — no keyboard; returning None.", label)
        return None

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def __del__(self) -> None:
        """Clean up GPIO on object destruction."""
        if _GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except Exception:
                pass
