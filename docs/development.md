# Development Guide

This guide explains how to develop, test, and iterate on PentestGPT-lite **without physical Raspberry Pi hardware**.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setting Up a Development Environment](#setting-up-a-development-environment)
- [Running Without Hardware](#running-without-hardware)
- [Project Structure](#project-structure)
- [Key Modules](#key-modules)
- [Linting](#linting)
- [Testing the LLM Locally](#testing-the-llm-locally)
- [Simulating Hardware Dependencies](#simulating-hardware-dependencies)
- [Configuration Reference](#configuration-reference)

---

## Prerequisites

You need:
- Python 3.11 or later (matching Raspberry Pi OS Bookworm)
- pip and venv
- A Linux, macOS, or WSL2 environment
- ~2 GB free disk space (for the TinyLlama model)

Optional but useful:
- Docker (for a closer Pi OS environment)
- A Raspberry Pi Zero 2 W for final hardware validation

---

## Setting Up a Development Environment

```bash
# 1. Clone the repository
git clone https://github.com/NaustudentX18/NxtGenAI.git
cd NxtGenAI

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
# On x86_64, skip the Pi-specific ARM flag:
pip install -r requirements.txt

# If llama-cpp-python fails to build on your architecture, install the
# pre-built CPU-only wheel for your platform:
# pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

> **Note:** `adafruit-circuitpython-ssd1306` and `smbus2` install fine on x86_64 but will raise `ImportError` at runtime if the I2C bus is unavailable. See [Simulating Hardware Dependencies](#simulating-hardware-dependencies) below.

---

## Running Without Hardware

The project provides `gui.py` — a Tkinter desktop GUI that mirrors the OLED display and button inputs. This lets you exercise the full ReAct loop without any hardware.

```bash
source venv/bin/activate
python3 gui.py
```

This opens a window with:
- A simulated 128×64 OLED display area.
- Keyboard shortcuts mapping to the three hardware buttons:
  - `A` key → Button A (Next/cycle menu)
  - `B` key → Button B (Back/cancel)
  - `C` key → Button C (Push-to-talk)

> **Note:** Voice input requires a working microphone and the Vosk model. To skip voice input during development, use the text input field in the GUI instead.

---

## Project Structure

```
NxtGenAI/
├── main.py           # Boot splash → LLM load → main event loop
├── ai_core.py        # ReAct reasoning engine + risk scoring (1–10)
├── ui.py             # SSD1306 OLED driver + buttons A/B/C (hardware)
├── gui.py            # Tkinter desktop GUI (development / software testing)
├── tools.py          # Subprocess wrappers: nmap, hydra, aircrack-ng, sqlmap, ARP
├── power.py          # PiSugar 3 I2C battery monitor + low-power shutdown
├── voice_input.py    # Push-to-talk voice input (Vosk offline STT + PyAudio)
├── config.ini        # All configuration (paths, thresholds, LLM params)
├── requirements.txt  # Pinned Python dependencies
├── setup.sh          # One-command installer (Raspberry Pi OS only)
├── docs/
│   ├── development.md    # This file
│   └── troubleshooting.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
└── README.md
```

---

## Key Modules

### `ai_core.py` — ReAct Loop

The heart of the project. Implements a Thought → Action → Observation loop:

1. **Thought:** LLM receives a system prompt + conversation history and generates the next reasoning step.
2. **Action:** The LLM's output is parsed for a tool call (e.g., `nmap`, `hydra`).
3. **Observation:** The tool is executed via `tools.py` and the output is fed back to the LLM.
4. **Risk scoring:** Each action is scored 1–10. Actions above `max_risk_score` in `config.ini` are auto-skipped.

To iterate on the LLM prompting or risk scoring without hardware, import `ai_core` directly:

```python
from ai_core import ReActAgent

agent = ReActAgent(config_path="config.ini")
result = agent.run("Perform a network recon on 192.168.1.0/24")
print(result)
```

### `tools.py` — Tool Wrappers

Each tool is a thin `subprocess.run()` wrapper that returns a dict:
```python
{"stdout": "...", "stderr": "...", "returncode": 0}
```

Tools can be tested in isolation without the LLM:
```python
from tools import run_nmap
result = run_nmap("127.0.0.1", flags=["-sV", "-p", "80,443"])
print(result["stdout"])
```

> **Note:** `nmap`, `hydra`, `aircrack-ng`, and `sqlmap` must be installed locally for tool-level testing. On Ubuntu/Debian: `sudo apt install nmap hydra aircrack-ng sqlmap`

### `power.py` — Battery Monitor

Reads battery level from the PiSugar 3 via I2C (smbus2). On a non-Pi system this will fail at import time unless you mock the I2C bus (see [Simulating Hardware Dependencies](#simulating-hardware-dependencies)).

### `ui.py` — OLED Driver

Hardware-only. On desktop, use `gui.py` instead.

---

## Linting

Before opening a PR, run:

```bash
source venv/bin/activate
pip install flake8
flake8 --max-line-length=100 *.py
```

Fix all reported issues. The project targets zero flake8 warnings.

---

## Testing the LLM Locally

If you want to test LLM inference on a desktop (x86_64):

1. Download the model:
   ```bash
   mkdir -p ~/models
   wget -O ~/models/tinyllama-1.1b-q4_0.gguf \
     https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf
   ```

2. Update `config.ini`:
   ```ini
   [paths]
   model = /home/YOUR_USERNAME/models/tinyllama-1.1b-q4_0.gguf
   ```

3. Run the GUI:
   ```bash
   python3 gui.py
   ```

On modern x86_64 hardware, inference will be significantly faster than on the Pi (often 30–60 tokens/second vs. 3–5 on the Pi).

---

## Simulating Hardware Dependencies

When running on a desktop, hardware-specific imports (`smbus2`, `adafruit_ssd1306`, GPIO) will fail because there is no I2C bus. The recommended approach is to use `gui.py`, which replaces `ui.py` entirely. For `power.py`, mock the battery level in your test environment:

```python
# In your test/dev script, monkey-patch power before importing main:
import power
power.get_battery_level = lambda: 85   # Simulate 85% battery
```

Alternatively, set the `PENTESTGPT_NO_HARDWARE=1` environment variable — this flag is checked by `power.py` to return a dummy battery level without I2C access:

```bash
PENTESTGPT_NO_HARDWARE=1 python3 gui.py
```

---

## Configuration Reference

All configuration is in `config.ini`. Key settings for development:

| Section | Key | Default | Notes |
|---------|-----|---------|-------|
| `[paths]` | `model` | `/home/pi/models/tinyllama-1.1b-q4_0.gguf` | Path to GGUF model file |
| `[llm]` | `n_ctx` | `512` | Context window tokens; reduce to save RAM |
| `[llm]` | `n_threads` | `3` | CPU threads for inference |
| `[llm]` | `max_tokens` | `200` | Max tokens per LLM response |
| `[llm]` | `temperature` | `0.3` | Lower = more deterministic |
| `[security]` | `max_risk_score` | `8` | Auto-skip actions above this score |
| `[security]` | `confirm_threshold` | `6` | Prompt user for confirmation above this score |
| `[oled]` | `i2c_address` | `0x3C` | SSD1306 I2C address |
| `[power]` | `pisugar_address` | `0x57` | PiSugar 3 I2C address |
| `[audio]` | `vosk_model` | `/home/pi/models/vosk-model-small-en-us` | Vosk model directory |
| `[wifi]` | `interface` | `wlan0` | WiFi interface for monitor mode |

For a full explanation of every option, see the inline comments in `config.ini`.
