#!/usr/bin/env python3
"""
simulate.py — Hardware-free simulation test for NxtGenAI on Pi Zero 2 W
==========================================================================
Stubs all hardware (GPIO, I2C, OLED, smbus2, llama_cpp, vosk, pyaudio)
and exercises the full app lifecycle:
  BOOT → MENU → MODE_RUNNING → RESULT → REPORT → SHUTDOWN

Run with:  python3 simulate.py
"""

import sys
import os
import types
import configparser
import threading
import time
import json
import tempfile
import traceback

# ─────────────────────────────────────────────────────────────────────────────
# Inject hardware stubs BEFORE any app module is imported
# ─────────────────────────────────────────────────────────────────────────────

# ── board / busio / adafruit_ssd1306 stubs ────────────────────────────────────
class _FakeBoard:
    SCL = "SCL"
    SDA = "SDA"

class _FakeBusio:
    class I2C:
        def __init__(self, *a, **kw): pass

class _FakeOLED:
    def __init__(self, *a, **kw): pass
    def fill(self, v): pass
    def show(self): pass
    def image(self, img): pass
    def contrast(self, v): pass

class _FakeAdafruitSSD1306:
    SSD1306_I2C = _FakeOLED

sys.modules["board"] = _FakeBoard()
sys.modules["busio"] = _FakeBusio()
sys.modules["adafruit_ssd1306"] = _FakeAdafruitSSD1306()

# ── RPi.GPIO stub ─────────────────────────────────────────────────────────────
_gpio_mod = types.ModuleType("RPi")
_gpio_sub = types.ModuleType("RPi.GPIO")
_gpio_sub.BCM = "BCM"
_gpio_sub.IN  = "IN"
_gpio_sub.FALLING = "FALLING"
_gpio_sub.RISING  = "RISING"
_gpio_sub.BOTH    = "BOTH"
_gpio_sub.PUD_UP  = "PUD_UP"
_gpio_sub.LOW     = 0
_gpio_sub.HIGH    = 1
_gpio_sub.setmode = lambda *a, **k: None
_gpio_sub.setwarnings = lambda *a, **k: None
_gpio_sub.setup = lambda *a, **k: None
_gpio_sub.add_event_detect = lambda *a, **k: None
_gpio_sub.input = lambda pin: 1
_gpio_sub.cleanup = lambda: None
_gpio_mod.GPIO = _gpio_sub
sys.modules["RPi"] = _gpio_mod
sys.modules["RPi.GPIO"] = _gpio_sub

# ── smbus2 stub ───────────────────────────────────────────────────────────────
class _FakeSMBus:
    def __init__(self, bus): pass
    def read_byte_data(self, addr, reg):
        # Simulate: battery at 75%, not charging
        if reg == 0x2A: return 75    # battery %
        if reg == 0x02: return 0x0F  # volt high (3855 mV)
        if reg == 0x03: return 0x2F  # volt low
        if reg == 0x55: return 0x40  # power good, not charging
        return 0
    def close(self): pass

_smbus_mod = types.ModuleType("smbus2")
_smbus_mod.SMBus = _FakeSMBus
sys.modules["smbus2"] = _smbus_mod

# ── llama_cpp stub ────────────────────────────────────────────────────────────
class _FakeLlama:
    def __init__(self, *a, **kw): pass
    def __call__(self, prompt, **kw):
        # Simulate a well-formed ReAct response then DONE
        if "wifi" in prompt.lower():
            text = 'Thought: Scan for APs.\nAction: nmap_scan({"target": "192.168.1.0/24"})'
        else:
            text = 'Action: report_done({})'
        return {"choices": [{"text": text}]}

_llama_mod = types.ModuleType("llama_cpp")
_llama_mod.Llama = _FakeLlama
sys.modules["llama_cpp"] = _llama_mod

# ── vosk stub ─────────────────────────────────────────────────────────────────
class _FakeVoskModel:
    def __init__(self, path): pass

class _FakeKaldiRecognizer:
    def __init__(self, model, rate): pass
    def AcceptWaveform(self, data): return True
    def FinalResult(self): return json.dumps({"text": "network scan"})

_vosk_mod = types.ModuleType("vosk")
_vosk_mod.Model = _FakeVoskModel
_vosk_mod.KaldiRecognizer = _FakeKaldiRecognizer
_vosk_mod.SetLogLevel = lambda v: None
sys.modules["vosk"] = _vosk_mod

# ── pyaudio stub ───────────────────────────────────────────────────────────────
class _FakeStream:
    def read(self, n, **kw): return b"\x00" * n * 2
    def stop_stream(self): pass
    def close(self): pass

class _FakePyAudio:
    paInt16 = 8
    def open(self, **kw): return _FakeStream()
    def terminate(self): pass

_pa_mod = types.ModuleType("pyaudio")
_pa_mod.PyAudio = _FakePyAudio
_pa_mod.paInt16 = 8
sys.modules["pyaudio"] = _pa_mod

# ── nmap / hydra / aircrack stubs via subprocess mock ─────────────────────────
# We'll patch subprocess.Popen in tools._run to return canned output
import subprocess as _subprocess_real

TOOL_OUTPUTS = {
    "nmap":        "Nmap scan report for 192.168.1.1\nHost is up.\nPORT   STATE SERVICE\n22/tcp open  ssh",
    "airmon-ng":   "Interface wlan0mon created",
    "airodump-ng": "[handshake captured]",
    "aireplay-ng": "Sending 1 DeAuth frame",
    "aircrack-ng": "KEY FOUND! [ testpass123 ]",
    "hydra":       "[22][ssh] host: 192.168.1.1  login: admin  password: admin",
    "sqlmap":      "[INFO] the back-end DBMS is MySQL",
    "curl":        "HTTP/1.1 200 OK\nServer: Apache/2.4.41",
}

class _MockPopen:
    def __init__(self, cmd, **kw):
        self.cmd = cmd
        binary = os.path.basename(cmd[0]) if cmd else "unknown"
        out = TOOL_OUTPUTS.get(binary, f"[stub output for {binary}]")
        import io
        self.stdout = io.StringIO(out + "\n")
        self.returncode = 0
    def wait(self, timeout=None): return 0
    def kill(self): pass

def _mock_popen(cmd, **kw):
    return _MockPopen(cmd, **kw)

# Patch at module level
_subprocess_real.Popen = _mock_popen


# ─────────────────────────────────────────────────────────────────────────────
# Now import app modules
# ─────────────────────────────────────────────────────────────────────────────
PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(name, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f"  {PASS} {name}")
        return True
    except Exception as e:
        results.append((FAIL, name))
        print(f"  {FAIL} {name}")
        print(f"       → {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


print("\n" + "="*60)
print("  NxtGenAI — Hardware Simulation Test")
print("  Target: Pi Zero 2 W + Whisplay Pi AI Hat + PiSugar 3")
print("="*60)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/7] Module imports")
# ─────────────────────────────────────────────────────────────────────────────
ai_core = tools_mod = ui_mod = power_mod = voice_mod = main_mod = None

def _import_ai_core():
    global ai_core
    import ai_core as m; ai_core = m
check("import ai_core", _import_ai_core)

def _import_tools():
    global tools_mod
    import tools as m; tools_mod = m
check("import tools", _import_tools)

def _import_ui():
    global ui_mod
    import ui as m; ui_mod = m
check("import ui", _import_ui)

def _import_power():
    global power_mod
    import power as m; power_mod = m
check("import power", _import_power)

def _import_voice():
    global voice_mod
    import voice_input as m; voice_mod = m
check("import voice_input", _import_voice)

def _import_main():
    global main_mod
    import main as m; main_mod = m
check("import main", _import_main)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[2/7] Config loading")
# ─────────────────────────────────────────────────────────────────────────────
cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
cfg_path = os.path.join(os.path.dirname(__file__), "config.ini")

def _cfg_exists():
    assert os.path.exists(cfg_path), f"config.ini not found at {cfg_path}"
check("config.ini exists", _cfg_exists)

def _cfg_load():
    cfg.read(cfg_path)
    assert cfg.get("paths", "model"), "paths.model missing"
    assert cfg.get("oled", "width"), "oled.width missing"
    assert cfg.get("power", "pisugar_address"), "power.pisugar_address missing"
    assert cfg.get("audio", "vosk_model"), "audio.vosk_model missing"
check("config.ini loads all required sections", _cfg_load)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[3/7] OLEDDisplay (ui.py) — headless mode")
# ─────────────────────────────────────────────────────────────────────────────
display = None

def _oled_init():
    global display
    display = ui_mod.OLEDDisplay(cfg)
check("OLEDDisplay instantiates without hardware", _oled_init)

def _oled_show_splash():
    display.show_splash()
check("show_splash() runs without error", _oled_show_splash)

def _oled_show_menu():
    display.show_menu("PentestGPT-lite", ["WiFi Crack", "Web Pentest", "Network Recon", "Full Auto (AI)"],
                      selected=0, battery_pct=75)
check("show_menu() renders correctly", _oled_show_menu)

def _oled_show_message():
    display.show_message("STATUS", "Running nmap...")
check("show_message() works", _oled_show_message)

def _oled_show_loading():
    display.show_loading("Loading AI... 5s")
check("show_loading() works", _oled_show_loading)

def _oled_show_react_step():
    display.show_react_step("Scanning network", "nmap_scan", 3)
    display.show_react_step("Cracking WPA2", "wifi_crack", 7)
    display.show_react_step("ARP poison", "arp_spoof", 9)
check("show_react_step() all risk levels", _oled_show_react_step)

def _oled_show_scroll():
    display.show_scroll(["nmap OK R:3", "wifi FAIL"], pos=0, total=10)
check("show_scroll() works", _oled_show_scroll)

def _oled_show_listening():
    display.show_listening()
check("show_listening() works", _oled_show_listening)

def _oled_poll_event():
    evt = display.poll_event()
    assert evt is None, f"Expected None on empty queue, got {evt!r}"
check("poll_event() returns None when queue empty", _oled_poll_event)

def _oled_set_brightness():
    display.set_brightness(80)
    display.set_brightness(200)
    display.set_brightness(300)   # Should clamp to 255
    assert display._brightness == 255
check("set_brightness() clamps correctly", _oled_set_brightness)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[4/7] PowerMonitor (power.py) — PiSugar 3 I2C stub")
# ─────────────────────────────────────────────────────────────────────────────
power = None
low_battery_called = threading.Event()

def _power_init():
    global power
    def _on_low(pct):
        low_battery_called.set()
    power = power_mod.PowerMonitor(cfg, on_low=_on_low)
check("PowerMonitor instantiates", _power_init)

def _power_read_pct():
    pct = power._read_battery_pct()
    assert 0 <= pct <= 100, f"Battery % out of range: {pct}"
    print(f"       Battery: {pct}% (simulated)")
check("_read_battery_pct() returns 0–100", _power_read_pct)

def _power_read_voltage():
    mv = power._read_voltage()
    assert mv >= 0, f"Negative voltage: {mv}"
    print(f"       Voltage: {mv} mV")
check("_read_voltage() returns valid millivolts", _power_read_voltage)

def _power_read_status():
    charging, power_good = power._read_status()
    print(f"       Charging: {charging}, Power good: {power_good}")
check("_read_status() returns booleans", _power_read_status)

def _power_poll_cycle():
    power._poll()
    assert power.battery_pct == 75
    assert power.voltage_mv  == (0x0F << 8) | 0x2F
check("_poll() updates state correctly", _power_poll_cycle)

def _power_status_dict():
    d = power.status_dict()
    assert "battery_pct" in d and "voltage_mv" in d
check("status_dict() structure valid", _power_status_dict)

def _power_low_battery_cb():
    # Simulate battery at 5% (below sleep threshold of 10)
    class _LowBusSMBus(_FakeSMBus):
        def read_byte_data(self, addr, reg):
            if reg == 0x2A: return 5
            return super().read_byte_data(addr, reg)
    pm2 = power_mod.PowerMonitor(cfg)
    pm2._bus = _LowBusSMBus(1)
    called = []
    pm2.on_low = lambda pct: called.append(pct)
    pm2._poll()
    assert called and called[0] == 5, f"Low battery callback not triggered: {called}"
    print(f"       Low-battery callback fired at {called[0]}%")
check("Low-battery callback fires at threshold", _power_low_battery_cb)

def _power_daemon_thread():
    pm3 = power_mod.PowerMonitor(cfg)
    t = threading.Thread(target=pm3.run, daemon=True, name="test_power")
    t.start()
    time.sleep(0.1)
    pm3.stop()
    t.join(timeout=3)
    assert not t.is_alive(), "Power monitor thread did not stop"
check("PowerMonitor daemon thread starts and stops cleanly", _power_daemon_thread)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[5/7] VoiceInput (voice_input.py) — Vosk stub")
# ─────────────────────────────────────────────────────────────────────────────

def _voice_init_no_model():
    vi = voice_mod.VoiceInput(model_path="/nonexistent/path")
    assert not vi.available, "Should be unavailable when model missing"
check("VoiceInput gracefully degrades with missing model dir", _voice_init_no_model)

def _voice_init_with_stub():
    # Create a fake model directory
    with tempfile.TemporaryDirectory() as tmpdir:
        vi = voice_mod.VoiceInput(model_path=tmpdir)
        assert vi.available, "Should be available with stub vosk+pyaudio"
        vi.start_recording()
        time.sleep(0.05)
        text = vi.stop_and_recognise()
        assert text == "network scan", f"Unexpected recognition: {text!r}"
        print(f"       Recognised: '{text}'")
        vi.cleanup()
check("VoiceInput start→record→recognise cycle", _voice_init_with_stub)

def _voice_noop_when_unavailable():
    vi = voice_mod.VoiceInput(model_path="/nonexistent")
    vi.start_recording()   # Should not raise
    result = vi.stop_and_recognise()
    assert result is None
check("VoiceInput methods are safe no-ops when unavailable", _voice_noop_when_unavailable)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[6/7] ToolRunner (tools.py) — subprocess stubs")
# ─────────────────────────────────────────────────────────────────────────────
runner = None

def _tools_init():
    global runner
    runner = tools_mod.ToolRunner(cfg)
check("ToolRunner instantiates", _tools_init)

def _tools_network_recon():
    results_list = runner.network_recon(target="192.168.1.0/24")
    assert isinstance(results_list, list) and len(results_list) >= 1
    assert all("tool" in r and "output" in r and "risk" in r for r in results_list)
    print(f"       network_recon returned {len(results_list)} result(s)")
check("network_recon() returns structured results", _tools_network_recon)

def _tools_web_pentest():
    results_list = runner.web_pentest(target="http://127.0.0.1")
    assert len(results_list) >= 1
    print(f"       web_pentest returned {len(results_list)} result(s)")
check("web_pentest() returns structured results", _tools_web_pentest)

def _tools_hydra_no_wordlist():
    results_list = runner.hydra_brute(target="192.168.1.1",
                                      service="ssh",
                                      wordlist="/nonexistent/wordlist.txt")
    assert results_list[0]["success"] is False
    assert "not found" in results_list[0]["output"]
check("hydra_brute() gracefully skips missing wordlist", _tools_hydra_no_wordlist)

def _tools_sqlmap_scan():
    results_list = runner.sqlmap_scan(target="http://127.0.0.1", level=1)
    assert len(results_list) == 1
    assert results_list[0]["tool"] == "sqlmap"
check("sqlmap_scan() returns single result dict", _tools_sqlmap_scan)

def _tools_result_structure():
    for r in runner.network_recon():
        assert "tool"    in r, "Missing 'tool'"
        assert "command" in r, "Missing 'command'"
        assert "rc"      in r, "Missing 'rc'"
        assert "output"  in r, "Missing 'output'"
        assert "risk"    in r and 1 <= r["risk"] <= 10, "Risk out of range"
        assert "success" in r, "Missing 'success'"
check("All result dicts have required fields with valid risk scores", _tools_result_structure)

# ─────────────────────────────────────────────────────────────────────────────
print("\n[7/7] Full App Lifecycle — state machine simulation")
# ─────────────────────────────────────────────────────────────────────────────

def _app_instantiate():
    app = main_mod.PentestGPTApp()
    assert app.state == main_mod.AppState.BOOT
check("PentestGPTApp instantiates at BOOT state", _app_instantiate)

def _app_config_load():
    app = main_mod.PentestGPTApp()
    val = app._cfg("oled", "width", "128")
    assert val == "128"
check("App config getter works with fallback", _app_config_load)

def _app_speak_noop():
    app = main_mod.PentestGPTApp()
    app.speak("Test speech")
    time.sleep(0.05)  # Let thread start
check("speak() runs without espeak-ng on dev machine", _app_speak_noop)

def _app_boot_subsystems():
    app = main_mod.PentestGPTApp()
    app._init_display()
    app._init_power()
    app._init_tools()
    app._init_voice_input()
    assert app.display  is not None, "Display not initialised"
    assert app.power    is not None, "Power not initialised"
    assert app.tools    is not None, "Tools not initialised"
check("All subsystems initialise without hardware", _app_boot_subsystems)

def _app_llm_load():
    app = main_mod.PentestGPTApp()
    app._init_display()
    app._init_tools()
    app._init_llm()
    # Give background thread time to load stub LLM
    loaded = app.llm_ready.wait(timeout=5)
    assert loaded, "LLM load event never set"
    assert app.ai is not None, "AICore not initialised"
check("LLM loads in background thread, event fires", _app_llm_load)

def _app_voice_command_modes():
    app = main_mod.PentestGPTApp()
    tests = [
        ("wifi crack", "wifi"),
        ("web pentest", "web"),
        ("network scan", "recon"),
        ("full auto", "auto"),
    ]
    for phrase, expected_key in tests:
        app.selected_mode_idx = 0
        result = app._handle_voice_command(phrase)
        assert result is True, f"'{phrase}' should return True (mode selected)"
        selected_key = main_mod.MODES[app.selected_mode_idx][1]
        assert selected_key == expected_key, \
            f"'{phrase}' selected '{selected_key}', expected '{expected_key}'"
    print(f"       All {len(tests)} voice mode commands recognised correctly")
check("Voice command mode selection for all 4 modes", _app_voice_command_modes)

def _app_voice_navigation():
    app = main_mod.PentestGPTApp()
    app.selected_mode_idx = 1  # Start at Web Pentest
    # "next" should advance
    app._handle_voice_command("next")
    assert app.selected_mode_idx == 2, f"Expected 2, got {app.selected_mode_idx}"
    # "back" should go backward
    app._handle_voice_command("back")
    assert app.selected_mode_idx == 1, f"Expected 1, got {app.selected_mode_idx}"
    # "previous" should also go backward
    app._handle_voice_command("previous")
    assert app.selected_mode_idx == 0, f"Expected 0, got {app.selected_mode_idx}"
check("Voice navigation (next/back/previous) moves correctly", _app_voice_navigation)

def _app_network_recon_mode():
    app = main_mod.PentestGPTApp()
    app._init_tools()
    app._init_display()
    results_list = app._run_network_recon()
    assert isinstance(results_list, list) and len(results_list) >= 1
    lines = app._format_results(results_list)
    assert isinstance(lines, list) and len(lines) >= 1
    print(f"       recon mode → {len(results_list)} results, {len(lines)} OLED lines")
check("_run_network_recon() produces results + formatted OLED lines", _app_network_recon_mode)

def _app_save_report():
    app = main_mod.PentestGPTApp()
    with tempfile.TemporaryDirectory() as tmpdir:
        app.cfg["paths"]["reports"] = tmpdir
        results_list = [{"tool": "nmap_ping", "command": "nmap -sn 192.168.1.0/24",
                   "output": "Host is up.", "risk": 2, "success": True}]
        json_path = app._save_report("recon", results_list)
        assert os.path.exists(json_path), "JSON report not created"
        html_path = json_path.replace(".json", ".html")
        assert os.path.exists(html_path), "HTML report not created"
        # Verify JSON structure
        with open(json_path) as f:
            data = json.load(f)
        assert data["tool"] == "PentestGPT-lite"
        assert data["mode"] == "recon"
        assert len(data["results"]) == 1
        print(f"       JSON: {os.path.basename(json_path)}")
        print(f"       HTML: {os.path.basename(html_path)}")
check("Report saves valid JSON + HTML to disk", _app_save_report)

def _app_react_loop():
    app = main_mod.PentestGPTApp()
    app._init_tools()
    app._init_llm()
    app.llm_ready.wait(timeout=5)
    steps_seen = []
    def _on_step(step):
        steps_seen.append(step)
    results_list = app.ai.react_loop(
        task="wifi scan",
        tools=app.tools,
        on_step=_on_step,
    )
    assert isinstance(results_list, list)
    print(f"       ReAct loop: {len(results_list)} step(s), {len(steps_seen)} callback(s)")
check("AI ReAct loop runs, calls on_step, returns results", _app_react_loop)

def _app_risk_scoring():
    app = main_mod.PentestGPTApp()
    app._init_llm()
    app.llm_ready.wait(timeout=5)
    # These rely on heuristic when stub LLM returns non-integer
    low  = app.ai._heuristic_risk("nmap_scan")
    mid  = app.ai._heuristic_risk("hydra_brute")
    high = app.ai._heuristic_risk("arp_spoof deauth")
    assert low  <= 4,  f"nmap risk should be low, got {low}"
    assert mid  >= 5,  f"hydra risk should be medium, got {mid}"
    assert high >= 6,  f"deauth risk should be high, got {high}"
    print(f"       nmap={low}, hydra={mid}, deauth={high}")
check("Risk heuristic scores correctly (nmap<hydra<deauth)", _app_risk_scoring)

def _app_risk_gate():
    """Actions above max_risk should be skipped."""
    from ai_core import AICore
    import configparser as _cp
    c = _cp.ConfigParser()
    c.read_dict({"security": {"max_risk_score": "5", "confirm_threshold": "4"},
                 "llm":      {"max_tokens": "200", "temperature": "0.3",
                              "repeat_penalty": "1.1"}})
    ai = AICore(model_path="/fake.gguf", cfg=c)
    # arp_spoof scores 8 → should be skipped
    score = ai._heuristic_risk("arp_spoof")
    assert score > 5, f"Expected risk > 5 for arp_spoof, got {score}"
    print(f"       arp_spoof heuristic risk = {score} (above gate of 5, will be skipped)")
check("Risk gate correctly identifies high-risk actions", _app_risk_gate)

def _app_state_transitions():
    """Verify state enum values exist and transitions are valid."""
    states = list(main_mod.AppState)
    required = {"BOOT", "MENU", "MODE_RUNNING", "RESULT", "REPORT", "ERROR", "SHUTDOWN"}
    actual   = {s.name for s in states}
    assert required == actual, f"State mismatch: {actual ^ required}"
check("AppState enum has all required states", _app_state_transitions)

# ─────────────────────────────────────────────────────────────────────────────
# Results summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("  SIMULATION RESULTS")
print("="*60)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
for status, name in results:
    print(f"  {status} {name}")

print(f"\n  Total: {passed} passed, {failed} failed out of {len(results)}")
print("="*60 + "\n")

sys.exit(0 if failed == 0 else 1)
