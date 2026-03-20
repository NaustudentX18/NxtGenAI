#!/usr/bin/env python3
# =============================================================================
# NxtGenAI — Power Management (PiSugar 3)
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Polls the PiSugar 3 UPS HAT over I2C to read battery percentage.
# Triggers low-battery actions at configurable thresholds.
#
# PiSugar 3 I2C register map (I2C address 0x57, bus 1):
#   0x2A — Battery percentage (0–100, unsigned byte)
#   0x02 — Battery voltage high byte
#   0x03 — Battery voltage low byte
#   0x55 — Power status flags (bit 7 = charging, bit 6 = power good)
#
# References:
#   https://github.com/PiSugar/PiSugar/wiki/PiSugar-3-Series
#
# NOTE: If PiSugar is not detected (no I2C device at 0x57), the module
# silently stubs out and reports 100% battery — the app continues normally.
# =============================================================================

import configparser
import logging
import time
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Optional I2C import
try:
    import smbus2  # type: ignore[import]
    _SMBUS_AVAILABLE = True
except ImportError:
    try:
        import smbus as smbus2  # type: ignore[import]  # older systems
        _SMBUS_AVAILABLE = True
    except ImportError:
        log.warning("smbus2 not found — PiSugar monitoring disabled (stub mode).")
        _SMBUS_AVAILABLE = False


# =============================================================================
# PiSugar 3 register addresses
# =============================================================================
REG_BATTERY_PCT  = 0x2A   # Battery level 0–100 %
REG_VOLT_HIGH    = 0x02   # Voltage MSB (millivolts / 256)
REG_VOLT_LOW     = 0x03   # Voltage LSB
REG_STATUS       = 0x55   # Status flags

# Bit masks for status register
BIT_CHARGING     = 0x80   # Bit 7: 1 = charging
BIT_POWER_GOOD   = 0x40   # Bit 6: 1 = USB power present


# =============================================================================
# PowerMonitor class
# =============================================================================
class PowerMonitor:
    """
    Continuously polls PiSugar 3 battery level and invokes threshold callbacks.

    Designed to run in a daemon thread (main.py does `t.daemon = True`).

    Attributes:
        battery_pct  : Latest battery percentage (0–100). Thread-safe read.
        is_charging  : True if USB power is connected.
        voltage_mv   : Latest battery voltage in millivolts.
    """

    def __init__(
        self,
        cfg: configparser.ConfigParser,
        on_low: Optional[Callable[[int], None]] = None,
    ):
        """
        Args:
            cfg    : ConfigParser with [power] section.
            on_low : Callback invoked when battery drops below threshold_sleep.
                     Receives current battery_pct as argument.
        """
        self.cfg = cfg
        self.on_low = on_low

        # Read thresholds from config
        self.threshold_warn  = int(cfg.get("power", "threshold_warn",  fallback="20"))
        self.threshold_sleep = int(cfg.get("power", "threshold_sleep", fallback="10"))
        self.poll_interval   = float(cfg.get("power", "poll_interval", fallback="30"))
        self.i2c_addr        = int(cfg.get("power", "pisugar_address", fallback="0x57"), 16)
        self.i2c_bus_num     = int(cfg.get("power", "pisugar_bus",     fallback="1"))

        # Public state (read by main loop / OLED)
        self.battery_pct: int   = 100    # Start optimistic until first read
        self.is_charging:  bool = False
        self.voltage_mv:   int  = 0

        # Internal flags
        self._warned   = False           # Prevent repeated warning calls
        self._shutdown = threading.Event()
        self._bus: Optional[object] = None

        # Try to open I2C bus
        self._bus = self._open_bus()

    # ── I2C bus management ────────────────────────────────────────────────────
    def _open_bus(self) -> Optional[object]:
        """Open smbus connection; return None on failure."""
        if not _SMBUS_AVAILABLE:
            return None
        try:
            bus = smbus2.SMBus(self.i2c_bus_num)
            log.info("Opened I2C bus %d for PiSugar 3 at 0x%02X.",
                     self.i2c_bus_num, self.i2c_addr)
            return bus
        except Exception as exc:
            log.warning("Cannot open I2C bus %d: %s — using stub.",
                        self.i2c_bus_num, exc)
            return None

    # ── Register reads ─────────────────────────────────────────────────────────
    def _read_byte(self, register: int) -> Optional[int]:
        """
        Read a single byte from PiSugar I2C register.
        Returns None on error (device absent or I2C fault).
        """
        if self._bus is None:
            return None
        try:
            return self._bus.read_byte_data(self.i2c_addr, register)
        except Exception as exc:
            log.debug("I2C read error (reg 0x%02X): %s", register, exc)
            return None

    def _read_battery_pct(self) -> int:
        """
        Read battery percentage from PiSugar 3.
        Returns last known value on read error (fail-safe).
        """
        raw = self._read_byte(REG_BATTERY_PCT)
        if raw is None:
            return self.battery_pct  # Return cached value on error
        # PiSugar 3 reports raw percentage directly (0–100)
        return max(0, min(100, int(raw)))

    def _read_voltage(self) -> int:
        """
        Read battery voltage in millivolts.
        PiSugar 3: voltage = (high_byte << 8 | low_byte) in mV units.
        """
        hi = self._read_byte(REG_VOLT_HIGH)
        lo = self._read_byte(REG_VOLT_LOW)
        if hi is None or lo is None:
            return self.voltage_mv
        return (hi << 8) | lo

    def _read_status(self) -> tuple[bool, bool]:
        """
        Read status flags from PiSugar 3.
        Returns (is_charging, power_good).
        """
        raw = self._read_byte(REG_STATUS)
        if raw is None:
            return False, False
        charging   = bool(raw & BIT_CHARGING)
        power_good = bool(raw & BIT_POWER_GOOD)
        return charging, power_good

    # ── Main polling loop ─────────────────────────────────────────────────────
    def run(self) -> None:
        """
        Blocking poll loop — run in a daemon thread.
        Reads battery every poll_interval seconds.
        Triggers callbacks when thresholds are crossed.
        """
        log.info("Power monitor started (interval=%.0fs, warn=%d%%, sleep=%d%%).",
                 self.poll_interval, self.threshold_warn, self.threshold_sleep)

        while not self._shutdown.is_set():
            self._poll()
            # Sleep in 1-second increments so we respond to shutdown quickly
            for _ in range(int(self.poll_interval)):
                if self._shutdown.is_set():
                    break
                time.sleep(1)

        log.info("Power monitor stopped.")

    def _poll(self) -> None:
        """Single poll cycle: read registers, update state, check thresholds."""
        pct                = self._read_battery_pct()
        voltage            = self._read_voltage()
        charging, pwr_good = self._read_status()

        self.battery_pct  = pct
        self.voltage_mv   = voltage
        self.is_charging  = charging

        log.debug("Battery: %d%%, %d mV, charging=%s", pct, voltage, charging)

        # ── Threshold actions ────────────────────────────────────────────────
        if pct <= self.threshold_sleep:
            # Critical: save & shutdown
            log.warning("Battery critical (%d%%) — triggering shutdown callback.", pct)
            if self.on_low:
                try:
                    self.on_low(pct)
                except Exception as exc:
                    log.error("on_low callback error: %s", exc)
            self._shutdown.set()  # Stop polling after shutdown initiated

        elif pct <= self.threshold_warn and not self._warned:
            # Warning: dim OLED, voice alert (handled by main loop via battery_pct)
            log.warning("Battery low (%d%%) — warning threshold reached.", pct)
            self._warned = True
            # Reset warning flag if battery recovers (e.g. charger plugged in)
        elif pct > self.threshold_warn and self._warned:
            self._warned = False  # Charger connected; reset flag

    # ── Diagnostic ────────────────────────────────────────────────────────────
    def status_dict(self) -> dict:
        """Return current power state as a serialisable dict for reports."""
        return {
            "battery_pct":  self.battery_pct,
            "voltage_mv":   self.voltage_mv,
            "is_charging":  self.is_charging,
            "warn_pct":     self.threshold_warn,
            "sleep_pct":    self.threshold_sleep,
        }

    # ── Graceful stop ─────────────────────────────────────────────────────────
    def stop(self) -> None:
        """Signal the polling loop to stop cleanly."""
        self._shutdown.set()
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
