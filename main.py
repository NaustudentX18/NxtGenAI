#!/usr/bin/env python3
# =============================================================================
# PentestGPT-lite — Main Entry Point
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Architecture overview:
#   1. Read config.ini
#   2. Play boot splash on OLED + voice greeting
#   3. Load LLM in background thread (non-blocking)
#   4. Voice-first UI: Button A=next, Button B=back, Button C=Push-to-Talk
#   5. On mode selection: invoke ai_core.py ReAct loop or tool directly
#   6. Power monitor (power.py) runs in daemon thread; shuts down on low battery
#
# State machine:
#   BOOT → MENU → MODE_SELECT → RUNNING → RESULT → REPORT_EXPORT
#
# Threading model:
#   - Main thread  : OLED draw loop (< 1 s refresh)
#   - llm_thread   : LLM initialisation (non-blocking startup)
#   - power_thread : PiSugar polling (daemon)
#   - tool_thread  : Pentest tool subprocess wrapper (daemon)
#   - ptt_thread   : Push-to-talk audio capture (daemon, started per press)
#
# Button layout (Whisplay Pi AI Hat — joystick removed):
#   Button A (GPIO 21) — Next / cycle menu item + announces it aloud
#   Button B (GPIO 20) — Back / previous menu item
#   Button C (GPIO 16) — Push-to-Talk walkie-talkie (hold=record, release=act)
# =============================================================================

import configparser
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import threading
import time
from enum import Enum, auto

# Local modules ----------------------------------------------------------------
from ai_core import AICore          # ReAct loop + risk scoring
from power import PowerMonitor      # PiSugar I2C battery management
from tools import ToolRunner        # Pentest tool wrappers
from ui import OLEDDisplay          # SSD1306 OLED + buttons
from voice_input import VoiceInput  # Push-to-talk offline STT

# =============================================================================
# Logging setup
# =============================================================================
_LOG_DIR = "/home/pi/reports"
_log_handlers: list = [logging.StreamHandler(sys.stdout)]
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
    _log_handlers.append(
        logging.handlers.RotatingFileHandler(
            os.path.join(_LOG_DIR, "pentestgpt.log"),
            maxBytes=1_048_576,  # 1 MB
            backupCount=2,
        )
    )
except OSError:
    pass  # Log to stdout only when running outside Pi environment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("main")


# =============================================================================
# Application state machine
# =============================================================================
class AppState(Enum):
    BOOT         = auto()   # Splash screen + LLM loading
    MENU         = auto()   # Main menu; waiting for button/voice input
    MODE_RUNNING = auto()   # Pentest mode executing
    RESULT       = auto()   # Displaying results / AI summary
    REPORT       = auto()   # Exporting report to USB
    ERROR        = auto()   # Recoverable error display
    SHUTDOWN     = auto()   # Graceful shutdown sequence


# Mode definitions shown in the menu
MODES = [
    ("WiFi Crack",    "wifi"),
    ("Web Pentest",   "web"),
    ("Network Recon", "recon"),
    ("Full Auto (AI)", "auto"),
]


# =============================================================================
# Application class
# =============================================================================
class PentestGPTApp:
    """
    Top-level application controller.
    Owns all subsystem references and coordinates between them.
    """

    def __init__(self):
        self.cfg = self._load_config()
        self.state = AppState.BOOT
        self.selected_mode_idx = 0    # Currently highlighted menu item
        self.mode_key = None          # Active mode key (e.g. "wifi")
        self.llm_ready = threading.Event()   # Set when AI core finishes loading
        self.result_lines: list[str] = []    # Lines to scroll on OLED result view
        self.report_path: str | None = None  # Path of last generated report

        # Subsystem objects (initialised in start())
        self.display: OLEDDisplay | None = None
        self.ai: AICore | None = None
        self.power: PowerMonitor | None = None
        self.tools: ToolRunner | None = None
        self.voice_input: VoiceInput | None = None

        # Speech management — track PID for interruptible announcements
        self._speak_pid: int | None = None
        self._speak_lock = threading.Lock()

    # ── Configuration ─────────────────────────────────────────────────────────
    @staticmethod
    def _load_config() -> configparser.ConfigParser:
        """Load config.ini; fall back to bundled defaults if file missing."""
        cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        if not os.path.exists(cfg_path):
            log.warning("config.ini not found — using built-in defaults.")
            return cfg  # All reads will use fallback values

        cfg.read(cfg_path)
        log.info("Loaded config from %s", cfg_path)
        return cfg

    def _cfg(self, section: str, key: str, fallback: str) -> str:
        """Safe config getter with fallback."""
        return self.cfg.get(section, key, fallback=fallback)

    # ── Voice helper ──────────────────────────────────────────────────────────
    def speak(self, text: str, interrupt: bool = False) -> None:
        """
        Non-blocking espeak-ng call.
        Runs in a daemon thread so it never blocks the draw loop.

        Args:
            text      : Text to speak aloud.
            interrupt : If True, stop any currently playing speech first.
                        Use when announcing rapidly changing menu items.
        """
        voice = self._cfg("voice", "voice", "en-gb")
        speed = self._cfg("voice", "speed", "130")
        amp   = self._cfg("voice", "amplitude", "100")

        def _say() -> None:
            with self._speak_lock:
                if interrupt and self._speak_pid is not None:
                    try:
                        os.kill(self._speak_pid, signal.SIGTERM)
                    except OSError:
                        pass
                    self._speak_pid = None

            cmd = [
                "espeak-ng",
                "-v", voice,
                "-s", speed,
                "-a", amp,
                text,
            ]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                with self._speak_lock:
                    self._speak_pid = proc.pid
                proc.wait()
                with self._speak_lock:
                    if self._speak_pid == proc.pid:
                        self._speak_pid = None
            except Exception as exc:
                log.debug("speak() error: %s", exc)

        t = threading.Thread(target=_say, daemon=True)
        t.start()

    # ── Subsystem init ────────────────────────────────────────────────────────
    def _init_display(self) -> None:
        """Initialise OLED. Fallback to headless (stdout) mode on error."""
        try:
            self.display = OLEDDisplay(self.cfg)
            log.info("OLED initialised.")
        except Exception as exc:
            log.warning("OLED init failed (%s) — running headless.", exc)
            self.display = None

    def _init_power(self) -> None:
        """Start PiSugar battery monitor in a daemon thread."""
        try:
            self.power = PowerMonitor(self.cfg, on_low=self._handle_low_battery)
            t = threading.Thread(target=self.power.run, daemon=True, name="power")
            t.start()
            log.info("Power monitor started.")
        except Exception as exc:
            log.warning("Power monitor init failed (%s) — skipping.", exc)

    def _init_llm(self) -> None:
        """
        Load LLM model in a background thread.
        Sets self.llm_ready event when done.
        Display shows "Loading AI..." while this runs.
        """
        model_path = self._cfg("paths", "model",
                               "/home/pi/models/tinyllama-1.1b-q4_0.gguf")
        n_ctx      = int(self._cfg("llm", "n_ctx", "512"))
        n_threads  = int(self._cfg("llm", "n_threads", "3"))

        def _load() -> None:
            try:
                self.ai = AICore(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    cfg=self.cfg,
                )
                log.info("LLM loaded successfully.")
            except Exception as exc:
                log.error("LLM load failed: %s", exc)
                self.ai = None
            finally:
                self.llm_ready.set()

        t = threading.Thread(target=_load, daemon=True, name="llm_loader")
        t.start()

    def _init_voice_input(self) -> None:
        """Initialise the push-to-talk voice input (Vosk + PyAudio)."""
        model_path = self._cfg(
            "audio", "vosk_model",
            "/home/pi/models/vosk-model-small-en-us",
        )
        try:
            self.voice_input = VoiceInput(model_path=model_path)
            if self.voice_input.available:
                log.info("Voice input (PTT) ready with Vosk model at %s.", model_path)
            else:
                log.warning(
                    "Voice input unavailable — Button C will act as SELECT. "
                    "Install vosk + pyaudio and download the Vosk small-en-us model."
                )
        except Exception as exc:
            log.warning("Voice input init failed (%s) — PTT disabled.", exc)
            self.voice_input = None

    def _init_tools(self) -> None:
        """Initialise pentest tool runner."""
        self.tools = ToolRunner(self.cfg)
        log.info("Tool runner initialised.")

    # ── Low-battery handler ───────────────────────────────────────────────────
    def _handle_low_battery(self, level: int) -> None:
        """
        Called by PowerMonitor when battery drops below threshold.
        Saves report and initiates graceful shutdown.
        """
        log.warning("Low battery: %d%% — initiating safe shutdown.", level)
        self.speak("Battery critical. Saving and shutting down.")
        if self.display:
            self.display.show_message("LOW BATTERY", f"{level}% — Shutting down")
        time.sleep(3)
        self.state = AppState.SHUTDOWN

    # ── Boot sequence ─────────────────────────────────────────────────────────
    def _boot_sequence(self) -> None:
        """
        Animated splash screen + voice greeting.
        Runs LLM loading in background so OLED stays responsive.
        """
        self.state = AppState.BOOT

        # Start subsystems (non-blocking)
        self._init_display()
        self._init_power()
        self._init_tools()
        self._init_voice_input()

        # Show animated boot splash on OLED
        if self.display:
            self.display.show_splash()

        # Voice greeting — no joystick; walkie-talkie interface
        self.speak(
            "Welcome to PentestGPT-lite. "
            "Press button A to cycle modes, button B to go back. "
            "Hold button C to speak a voice command."
        )
        log.info("Boot greeting spoken.")

        # Start LLM load (background thread)
        self._init_llm()

        # Show loading indicator while LLM loads (max 120 s before timeout)
        timeout = 120
        start   = time.monotonic()
        while not self.llm_ready.is_set():
            elapsed = int(time.monotonic() - start)
            if self.display:
                self.display.show_loading(f"Loading AI... {elapsed}s")
            time.sleep(0.2)  # 200 ms poll — keeps UI responsive
            if elapsed > timeout:
                log.error("LLM load timed out after %ds", timeout)
                self.speak("AI load failed. Pentest tools still available.")
                break

        if self.ai:
            log.info("AI core ready.")
        else:
            log.warning("AI core unavailable — tool-only mode.")

        # Transition to menu — announce first item
        self.state = AppState.MENU
        self._announce_current_item()

    # ── Menu handling ─────────────────────────────────────────────────────────
    def _draw_menu(self) -> None:
        """Render the main menu on OLED with the current selection highlighted."""
        if self.display:
            self.display.show_menu(
                title="PentestGPT-lite",
                items=[m[0] for m in MODES],
                selected=self.selected_mode_idx,
                battery_pct=self.power.battery_pct if self.power else None,
            )

    # ── Menu helpers ──────────────────────────────────────────────────────────
    def _announce_current_item(self) -> None:
        """Speak the name of the currently highlighted menu item (interruptible)."""
        name = MODES[self.selected_mode_idx][0]
        self.speak(name, interrupt=True)

    def _handle_menu_input(self) -> bool:
        """
        Poll button events and update the menu selection.

        Button layout:
          A         — Next item (cycle forward) + announce it aloud
          B         — Previous item (cycle backward) + announce it aloud
          C_PRESS   — Start voice recording (show Listening… on OLED)
          C_RELEASE — Stop recording; match voice command to action

        Fallback when voice input unavailable:
          C_PRESS / C_RELEASE — confirm current selection

        Returns True when a mode has been confirmed and should start running.
        """
        if not self.display:
            # Headless: auto-select first mode after short delay
            time.sleep(1)
            return True

        event = self.display.poll_event()
        if event is None:
            return False

        if event == "A":
            # Next item + announce
            self.selected_mode_idx = (self.selected_mode_idx + 1) % len(MODES)
            self._announce_current_item()

        elif event == "B":
            # Previous item + announce
            self.selected_mode_idx = (self.selected_mode_idx - 1) % len(MODES)
            self._announce_current_item()

        elif event == "C_PRESS":
            if self.voice_input and self.voice_input.available:
                # Start PTT recording — show listening indicator
                self.voice_input.start_recording()
                if self.display:
                    self.display.show_listening()
                log.debug("PTT started in menu state.")
            else:
                # No voice input — C acts as SELECT
                return True

        elif event == "C_RELEASE":
            if self.voice_input and self.voice_input.available:
                # Stop recording and process command
                text = self.voice_input.stop_and_recognise()
                return self._handle_voice_command(text)

        return False

    def _handle_voice_command(self, text: str | None) -> bool:
        """
        Match recognised voice text to a menu action.
        Returns True if a mode was selected and should start running.

        Supported commands:
          Mode names  : "wifi [crack]", "web [pentest]", "recon" / "network",
                        "auto" / "ai" / "full auto"
          Navigation  : "next", "back" / "previous"
          Confirmation: "select" / "yes" / "ok" / "confirm" / "go" / "start"
        """
        if not text:
            self.speak("I didn't catch that. Try again.")
            return False

        t = text.lower()
        log.info("Voice command received: '%s'", t)

        # ── Direct mode selection ──────────────────────────────────────────
        if "wifi" in t:
            idx = next((i for i, (_, k) in enumerate(MODES) if k == "wifi"), None)
            if idx is not None:
                self.selected_mode_idx = idx
                self.speak(f"Selected {MODES[idx][0]}. Starting now.")
                return True

        if "web" in t:
            idx = next((i for i, (_, k) in enumerate(MODES) if k == "web"), None)
            if idx is not None:
                self.selected_mode_idx = idx
                self.speak(f"Selected {MODES[idx][0]}. Starting now.")
                return True

        if "recon" in t or "network" in t:
            idx = next((i for i, (_, k) in enumerate(MODES) if k == "recon"), None)
            if idx is not None:
                self.selected_mode_idx = idx
                self.speak(f"Selected {MODES[idx][0]}. Starting now.")
                return True

        if "auto" in t or " ai" in t or t == "ai":
            idx = next((i for i, (_, k) in enumerate(MODES) if k == "auto"), None)
            if idx is not None:
                self.selected_mode_idx = idx
                self.speak(f"Selected {MODES[idx][0]}. Starting now.")
                return True

        # ── Navigation ────────────────────────────────────────────────────
        if "next" in t:
            self.selected_mode_idx = (self.selected_mode_idx + 1) % len(MODES)
            self._announce_current_item()
            return False

        if "back" in t or "previous" in t:
            self.selected_mode_idx = (self.selected_mode_idx - 1) % len(MODES)
            self._announce_current_item()
            return False

        if "cancel" in t:
            self._announce_current_item()
            return False

        # ── Confirm current item ───────────────────────────────────────────
        if any(w in t for w in ("select", "yes", "ok", "confirm", "go", "start")):
            name = MODES[self.selected_mode_idx][0]
            self.speak(f"Starting {name}.")
            return True

        # ── Unknown command ────────────────────────────────────────────────
        self.speak("Command not recognised. Say a mode name or next or select.")
        return False

    # ── Mode execution ────────────────────────────────────────────────────────
    def _run_mode(self, mode_key: str) -> None:
        """
        Execute the selected pentest mode.
        Dispatches to AI-driven Full Auto or direct tool calls.
        """
        self.state = AppState.MODE_RUNNING
        self.mode_key = mode_key
        mode_name = next(n for n, k in MODES if k == mode_key)

        log.info("Starting mode: %s", mode_name)
        self.speak(f"Starting {mode_name}. Please wait.")

        if self.display:
            self.display.show_message(mode_name, "Initialising...")

        # Collect results via a mutable list (populated by tool callbacks)
        results: list[dict] = []

        try:
            if mode_key == "auto" and self.ai:
                # Full Auto: AI orchestrates everything via ReAct loop
                results = self._run_full_auto()
            elif mode_key == "wifi":
                results = self._run_wifi_crack()
            elif mode_key == "web":
                results = self._run_web_pentest()
            elif mode_key == "recon":
                results = self._run_network_recon()
            else:
                log.warning("Unknown mode key: %s", mode_key)
        except Exception as exc:
            log.error("Mode %s crashed: %s", mode_key, exc, exc_info=True)
            self.speak("Tool down. Skipping.")
            results.append({"error": str(exc), "mode": mode_key})

        # Store results and transition to result display
        self.result_lines = self._format_results(results)
        self.state = AppState.RESULT

        # Generate reports
        self.report_path = self._save_report(mode_key, results)
        self.speak("Scan complete. Results ready.")

    def _run_full_auto(self) -> list[dict]:
        """Drive the AI ReAct loop: Thought → Action → Observation → repeat."""
        assert self.ai is not None, "AI core not loaded"
        return self.ai.react_loop(
            task="Perform a comprehensive security assessment of the local network.",
            tools=self.tools,
            on_step=self._on_react_step,
        )

    def _run_wifi_crack(self) -> list[dict]:
        """WiFi Crack mode: monitor → capture handshake → crack."""
        if not self.tools:
            return [{"error": "Tools not initialised"}]
        iface   = self._cfg("wifi", "interface", "wlan0")
        timeout = int(self._cfg("wifi", "capture_timeout", "60"))
        wl_path = self._cfg("paths", "rockyou", "/home/pi/wordlists/rockyou.txt")
        return self.tools.wifi_crack(iface, timeout, wl_path,
                                     status_cb=self._tool_status_cb)

    def _run_web_pentest(self) -> list[dict]:
        """Web Pentest mode: target URL → sqlmap + header checks."""
        # Target URL is obtained interactively if display allows, else default
        target = "http://127.0.0.1"  # Default; UI prompts override this
        if self.display:
            target = self.display.prompt_text("Target URL:") or target
        if not self.tools:
            return [{"error": "Tools not initialised"}]
        return self.tools.web_pentest(target, status_cb=self._tool_status_cb)

    def _run_network_recon(self) -> list[dict]:
        """Network Recon mode: ARP discovery → nmap sweep."""
        if not self.tools:
            return [{"error": "Tools not initialised"}]
        return self.tools.network_recon(status_cb=self._tool_status_cb)

    def _on_react_step(self, step: dict) -> None:
        """
        Callback invoked after each ReAct step.
        Updates OLED with current thought/action and checks risk score.
        """
        thought = step.get("thought", "")[:40]  # Trim for OLED 128-char width
        action  = step.get("action", "")[:40]
        risk    = step.get("risk", 0)

        log.info("ReAct step — thought: %s | action: %s | risk: %d",
                 thought, action, risk)

        if self.display:
            self.display.show_react_step(thought, action, risk)

    def _tool_status_cb(self, message: str) -> None:
        """Generic status callback from tool runner — updates OLED status line."""
        log.debug("Tool status: %s", message)
        if self.display:
            self.display.show_message("Running...", message[:20])

    # ── Result display ────────────────────────────────────────────────────────
    def _show_results(self) -> None:
        """
        Show scrollable result summary on OLED.

        Button layout:
          A         — Scroll down one line
          B         — Back to menu
          C_PRESS   — Start voice recording (listening for command)
          C_RELEASE — Stop recording; "export" / "usb" → export, "back" → menu
        """
        scroll_pos = 0
        self.speak("Results ready. Press A to scroll, B to go back, "
                   "or hold C to speak a command.")
        while self.state == AppState.RESULT:
            if self.display:
                visible = self.result_lines[scroll_pos: scroll_pos + 4]
                self.display.show_scroll(visible, scroll_pos,
                                         total=len(self.result_lines))
                event = self.display.poll_event()
                if event == "A":
                    # Scroll down
                    if scroll_pos < len(self.result_lines) - 4:
                        scroll_pos += 1
                elif event == "B":
                    self.state = AppState.MENU
                    break
                elif event == "C_PRESS":
                    if self.voice_input and self.voice_input.available:
                        self.voice_input.start_recording()
                        self.display.show_listening()
                    else:
                        # No voice — C acts as export
                        self._export_report()
                        break
                elif event == "C_RELEASE":
                    if self.voice_input and self.voice_input.available:
                        text = self.voice_input.stop_and_recognise() or ""
                        t = text.lower()
                        if any(w in t for w in ("export", "usb", "save")):
                            self._export_report()
                            break
                        elif any(w in t for w in ("back", "menu", "cancel")):
                            self.state = AppState.MENU
                            break
                        else:
                            self.speak(
                                "Say export to save to USB, or back to return."
                            )
            else:
                # Headless: print results and return to menu
                for line in self.result_lines:
                    print(line)
                self.state = AppState.MENU
                break
            time.sleep(0.1)  # 100 ms — within < 1 s refresh target

    def _export_report(self) -> None:
        """Copy report files to USB mount point (Button C handler)."""
        usb = self._cfg("paths", "usb_mount", "/media/pi/")
        if self.report_path and os.path.exists(self.report_path):
            try:
                import shutil
                # Find the first USB device under the mount point
                usb_targets = [
                    os.path.join(usb, d) for d in os.listdir(usb)
                    if os.path.isdir(os.path.join(usb, d))
                ]
                if usb_targets:
                    dest = shutil.copy(self.report_path, usb_targets[0])
                    log.info("Report exported to %s", dest)
                    self.speak("Report saved to USB.")
                    if self.display:
                        self.display.show_message("Exported!", usb_targets[0][-20:])
                else:
                    log.warning("No USB device found at %s", usb)
                    self.speak("No USB found.")
            except Exception as exc:
                log.error("USB export failed: %s", exc)
                self.speak("Export failed.")
        else:
            log.warning("No report to export.")
            self.speak("No report available.")
        time.sleep(2)
        self.state = AppState.MENU

    # ── Report generation ─────────────────────────────────────────────────────
    def _save_report(self, mode_key: str, results: list[dict]) -> str:
        """
        Save scan results as both JSON and single-file HTML (dark Bootstrap 5).
        Returns the path of the JSON report (HTML path is derived from it).
        """
        import json
        from datetime import datetime

        reports_dir = self._cfg("paths", "reports", "/home/pi/reports/")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name  = f"report_{mode_key}_{timestamp}"
        json_path  = os.path.join(reports_dir, base_name + ".json")
        html_path  = os.path.join(reports_dir, base_name + ".html")

        payload = {
            "tool":      "PentestGPT-lite",
            "version":   "1.0.0",
            "timestamp": timestamp,
            "mode":      mode_key,
            "results":   results,
        }

        # JSON report
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        log.info("JSON report saved: %s", json_path)

        # HTML report (dark Bootstrap 5, single file — no CDN dependency)
        html = self._build_html_report(payload)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        log.info("HTML report saved: %s", html_path)

        return json_path

    @staticmethod
    def _build_html_report(payload: dict) -> str:
        """
        Generate a self-contained HTML report with dark Bootstrap 5 CSS.
        All CSS is inline — no CDN required (fully offline).
        """
        import json as _json

        # Inline Bootstrap 5 dark theme (minified subset — no internet needed)
        # Full Bootstrap CDN would be: https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/...
        # We embed only the essential dark-mode styles to keep the file small.
        dark_css = """
body{background:#121212;color:#e0e0e0;font-family:'Segoe UI',sans-serif;margin:0;padding:20px}
h1{color:#00e676;border-bottom:1px solid #333;padding-bottom:8px}
h2{color:#40c4ff;margin-top:24px}
.badge-risk-low{background:#2e7d32;color:#fff;padding:2px 8px;border-radius:4px}
.badge-risk-med{background:#f57f17;color:#fff;padding:2px 8px;border-radius:4px}
.badge-risk-high{background:#b71c1c;color:#fff;padding:2px 8px;border-radius:4px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th{background:#1e1e1e;color:#90caf9;padding:8px;text-align:left;border-bottom:1px solid #333}
td{padding:6px 8px;border-bottom:1px solid #222}
tr:hover td{background:#1a1a2e}
pre{background:#1e1e1e;padding:12px;border-radius:4px;overflow-x:auto;color:#a5d6a7}
.meta{color:#757575;font-size:.85em}
        """.strip()

        results_html = ""
        for item in payload.get("results", []):
            if isinstance(item, dict):
                tool  = item.get("tool", "unknown")
                cmd   = item.get("command", "")
                out   = item.get("output", "")
                risk  = item.get("risk", 0)
                badge_cls = (
                    "badge-risk-high" if risk >= 7
                    else "badge-risk-med" if risk >= 4
                    else "badge-risk-low"
                )
                results_html += f"""
<h2>{tool} <span class="{badge_cls}">Risk: {risk}/10</span></h2>
<p class="meta">Command: <code>{cmd}</code></p>
<pre>{out[:4000]}</pre>
"""
        mode    = payload.get("mode", "unknown")
        ts      = payload.get("timestamp", "")
        json_dump = _json.dumps(payload, indent=2, default=str)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PentestGPT-lite Report — {ts}</title>
<style>{dark_css}</style>
</head>
<body>
<h1>🛡️ PentestGPT-lite Report</h1>
<p class="meta">Mode: <strong>{mode}</strong> &nbsp;|&nbsp; Generated: {ts}</p>
{results_html or '<p>No results recorded.</p>'}
<h2>Raw JSON</h2>
<pre>{json_dump}</pre>
<p class="meta">Generated by PentestGPT-lite — MIT License — For authorised use only.</p>
</body>
</html>"""

    # ── Result formatting ─────────────────────────────────────────────────────
    @staticmethod
    def _format_results(results: list[dict]) -> list[str]:
        """
        Convert raw results dicts to short strings for OLED scrolling.
        Each string fits within ~20 chars (OLED character width at default font).
        """
        lines = []
        for item in results:
            if "error" in item:
                lines.append(f"ERR: {item['error'][:16]}")
            else:
                tool = item.get("tool", "tool")[:8]
                risk = item.get("risk", 0)
                status = "OK" if not item.get("error") else "FAIL"
                lines.append(f"{tool} R:{risk} {status}")
        return lines or ["No results."]

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        """
        Main application loop.
        Drives the state machine until AppState.SHUTDOWN.
        """
        log.info("PentestGPT-lite starting up.")

        # Boot sequence (blocking until LLM loaded or timeout)
        self._boot_sequence()

        while self.state != AppState.SHUTDOWN:
            if self.state == AppState.MENU:
                self._draw_menu()
                selected = self._handle_menu_input()
                if selected:
                    mode_key = MODES[self.selected_mode_idx][1]
                    # Run mode in a separate thread so OLED draw loop continues
                    t = threading.Thread(
                        target=self._run_mode,
                        args=(mode_key,),
                        daemon=True,
                        name="mode_runner",
                    )
                    t.start()
                    # Wait for mode to finish or user to cancel
                    while self.state == AppState.MODE_RUNNING:
                        if self.display:
                            self.display.refresh()
                        time.sleep(0.1)  # 100 ms — < 1 s refresh

            elif self.state == AppState.RESULT:
                self._show_results()
                # Announce menu on return
                if self.state == AppState.MENU:
                    self._announce_current_item()

            elif self.state == AppState.ERROR:
                # Errors are shown for 3 s then return to menu
                time.sleep(3)
                self.state = AppState.MENU
                self._announce_current_item()

            else:
                time.sleep(0.05)

        # ── Graceful shutdown ─────────────────────────────────────────────────
        log.info("Shutdown requested.")
        self.speak("Goodbye. Shutting down.")
        if self.display:
            self.display.show_message("Goodbye", "Shutting down...")
        if self.voice_input:
            self.voice_input.cleanup()
        time.sleep(2)
        os.system("sudo poweroff")


# =============================================================================
# Entry point
# =============================================================================
def main() -> None:
    """Parse CLI args (reserved for future flags) and start application."""
    app = PentestGPTApp()
    try:
        app.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user — exiting.")
        if app.display:
            app.display.clear()
        if app.voice_input:
            app.voice_input.cleanup()
    except Exception as exc:
        log.critical("Fatal error: %s", exc, exc_info=True)
        if app.display:
            app.display.show_message("FATAL ERROR", str(exc)[:20])
        if app.voice_input:
            app.voice_input.cleanup()
        time.sleep(5)
        raise


if __name__ == "__main__":
    main()
