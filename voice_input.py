#!/usr/bin/env python3
# =============================================================================
# PentestGPT-lite — Voice Input (Push-to-Talk / Walkie-Talkie)
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Provides offline speech recognition for the walkie-talkie interface.
# Hardware: USB or 3.5 mm microphone connected to the Raspberry Pi.
#
# Flow:
#   1. Button C pressed  → start_recording()     — captures audio via PyAudio
#   2. Button C released → stop_and_recognise()  — runs Vosk STT offline
#   3. Returns recognised text string (lower-cased) or None on failure
#
# Offline STT engine: Vosk (vosk-model-small-en-us, ~40 MB)
#   https://alphacephei.com/vosk/models
#
# Graceful degradation:
#   If vosk or pyaudio are not installed the class still instantiates and
#   all methods return None / False — the rest of the app is unaffected.
#
# GPIO mapping (Whisplay Pi AI Hat, BCM):
#   Button C (GPIO 16) — Push-to-Talk  (hold = record, release = recognise)
# =============================================================================

import json
import logging
import os
import threading
from typing import Optional

log = logging.getLogger(__name__)

# ── Optional imports — degrade gracefully if not present ─────────────────────
try:
    import vosk  # type: ignore[import]
    _VOSK_OK = True
except ImportError:
    log.warning(
        "vosk not installed — voice input disabled. "
        "Run: pip install vosk"
    )
    _VOSK_OK = False

try:
    import pyaudio  # type: ignore[import]
    _PYAUDIO_OK = True
except ImportError:
    log.warning(
        "pyaudio not installed — voice input disabled. "
        "Run: sudo apt install portaudio19-dev && pip install pyaudio"
    )
    _PYAUDIO_OK = False

# ── Audio constants ───────────────────────────────────────────────────────────
_RATE     = 16000  # Hz — Vosk small-en-us model requires 16 kHz
_CHANNELS = 1      # Mono
_CHUNK    = 1024   # Frames per buffer (~64 ms at 16 kHz)


# =============================================================================
# VoiceInput class
# =============================================================================
class VoiceInput:
    """
    Push-to-talk audio recorder + offline speech recogniser.

    Usage::

        vi = VoiceInput(model_path="/home/pi/models/vosk-model-small-en-us")
        if vi.available:
            vi.start_recording()           # call when PTT button is pressed
            text = vi.stop_and_recognise() # call when PTT button is released
            if text:
                print(text)                # e.g. "wifi crack"

    Gracefully degrades: if vosk/pyaudio are missing, ``available`` is False
    and both methods are safe no-ops that return ``None``.
    """

    def __init__(self, model_path: str = "/home/pi/models/vosk-model-small-en-us"):
        self._model_path = model_path
        self._model      = None
        self._pa         = None          # PyAudio instance
        self._frames: list[bytes] = []
        self._recording  = False
        self._lock       = threading.Lock()

        self._available  = self._init()

    # ── Initialisation ─────────────────────────────────────────────────────────
    def _init(self) -> bool:
        """
        Try to initialise Vosk model and PyAudio.
        Returns True on success; False if any dependency is missing.
        """
        if not _VOSK_OK or not _PYAUDIO_OK:
            return False

        # Load Vosk model from disk
        if not os.path.isdir(self._model_path):
            log.warning(
                "Vosk model directory not found: %s\n"
                "Download & extract the small English model:\n"
                "  wget https://alphacephei.com/vosk/models/"
                "vosk-model-small-en-us-0.15.zip\n"
                "  unzip vosk-model-small-en-us-0.15.zip -d "
                "/home/pi/models/",
                self._model_path,
            )
            return False

        try:
            vosk.SetLogLevel(-1)  # Suppress Vosk's verbose C++ output
            self._model = vosk.Model(self._model_path)
            log.info("Vosk model loaded from %s", self._model_path)
        except Exception as exc:
            log.error("Vosk model load failed: %s", exc)
            return False

        # Initialise PyAudio
        try:
            self._pa = pyaudio.PyAudio()
            log.info("PyAudio ready (default input device).")
        except Exception as exc:
            log.error("PyAudio init failed: %s", exc)
            return False

        return True

    # ── Public interface ───────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        """True if both Vosk and PyAudio initialised successfully."""
        return self._available

    def start_recording(self) -> None:
        """
        Begin capturing microphone audio in a background thread.
        Call this when the PTT button is *pressed* (falling edge).

        Safe to call repeatedly — subsequent calls while already recording
        are no-ops.
        """
        if not self._available:
            return
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._recording = True

        t = threading.Thread(target=self._record_loop, daemon=True,
                             name="ptt_record")
        t.start()
        log.debug("PTT recording started.")

    def stop_and_recognise(self) -> Optional[str]:
        """
        Stop recording and run Vosk STT on the captured audio.
        Call this when the PTT button is *released* (rising edge).

        Blocks briefly (~100–500 ms) while recognition completes.
        Returns lower-cased recognised text, or ``None`` on failure or silence.
        """
        if not self._available:
            return None

        with self._lock:
            self._recording = False
            frames = list(self._frames)

        if not frames:
            log.debug("PTT stop: no audio frames captured.")
            return None

        return self._recognise(frames)

    # ── Internal helpers ───────────────────────────────────────────────────────
    def _record_loop(self) -> None:
        """Background thread: open input stream and capture PCM until stopped."""
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=_CHANNELS,
                rate=_RATE,
                input=True,
                frames_per_buffer=_CHUNK,
            )
            while True:
                with self._lock:
                    if not self._recording:
                        break
                data = stream.read(_CHUNK, exception_on_overflow=False)
                with self._lock:
                    self._frames.append(data)
            stream.stop_stream()
            stream.close()
        except Exception as exc:
            log.error("PTT audio capture error: %s", exc)
            with self._lock:
                self._recording = False

    def _recognise(self, frames: list[bytes]) -> Optional[str]:
        """
        Run Vosk KaldiRecognizer on the PCM frames collected by _record_loop.
        Returns lower-cased text or None.
        """
        try:
            rec = vosk.KaldiRecognizer(self._model, _RATE)
            for frame in frames:
                rec.AcceptWaveform(frame)
            result = json.loads(rec.FinalResult())
            text   = result.get("text", "").strip().lower()
            log.info("Voice recognised: '%s'", text if text else "(empty)")
            return text if text else None
        except Exception as exc:
            log.error("Vosk recognition error: %s", exc)
            return None

    # ── Cleanup ────────────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        """Release PyAudio resources. Call on app exit."""
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
