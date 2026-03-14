# 🛡️ NxtGenAI — AI-Powered Offline Pentesting Toolkit

<!--
MIT License — Copyright (c) 2026 DINA OKTARIANA
See LICENSE file for full text.
-->

> **"A pocket-sized AI pentester, offline forever."**
> Powered by TinyLlama on Raspberry Pi Zero 2 W — no cloud, no leaks, full autonomy.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20Zero%202%20W-red)](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Offline](https://img.shields.io/badge/internet-NOT%20required-brightgreen)](#)

---

## 📸 Screenshots (Hardware Preview)

```
┌──────────────────────────┐
│  ██████████████████████  │  ← 128×64 OLED (SSD1306)
│  ██    NxtGenAI        ██  │
│  ██  [WiFi Crack     ] ██  │  ← Button A cycles mode
│  ██  [Web Pentest    ] ██  │
│  ██  [Network Recon  ] ██  │
│  ██  [Full Auto (AI) ] ██  │
│  ██  Batt: 87% ■■■■░  ██  │  ← PiSugar 3 live readout
│  ██████████████████████  │
└──────────────────────────┘
  [A] Next   [B] Back   [C] Push-to-Talk
```

---

## 🔧 Hardware Requirements

| Component | Model | Notes |
|---|---|---|
| SBC | Raspberry Pi Zero 2 W | ARMv8, 512 MB RAM |
| Battery HAT | PiSugar 3 | I2C power monitor, USB-C charge |
| Display / Input HAT | Whisplay Pi AI Hat | SSD1306 128×64 OLED, 3 buttons (A/B/C) |
| Storage | microSD ≥ 8 GB | Class 10 / A1 recommended |
| OS | Raspberry Pi OS Lite (Bookworm) | 64-bit, headless |

---

## ⚡ 60-Second Install (copy-paste ready)

```bash
# 1. Flash Pi OS Lite Bookworm (64-bit) to microSD
# 2. Enable SSH + configure WiFi via raspi-config or imager
# 3. SSH in, then:

git clone https://github.com/NaustudentX18/NxtGenAI.git
cd NxtGenAI
chmod +x setup.sh
sudo ./setup.sh

# That's it. Reboot when prompted:
sudo reboot
```

> **First Boot:** OLED shows animated splash, voice says  
> *"Welcome to NxtGenAI. Press button A to cycle modes, button B to go back. Hold button C to speak a voice command."*

---

## 🚀 Usage

### Operation Modes

| Mode | Description | AI Involvement |
|---|---|---|
| **WiFi Crack** | WPA2 handshake capture + hashcat/aircrack | Suggests wordlist strategy |
| **Web Pentest** | sqlmap + header analysis + directory brute | Chains attacks autonomously |
| **Network Recon** | nmap lite + ARP discovery + OS detection | Summarises findings |
| **Full Auto (AI)** | ReAct loop — AI plans and executes everything | Full autonomy |

### Controls

| Input | Action |
|---|---|
| Button A | Next / cycle menu item |
| Button B | Back / Cancel |
| Button C (hold) | Push-to-Talk — speak a voice command |
| Button C (release) | Send / confirm voice input |

### Report Output

Completed sessions auto-generate:
- `report_YYYYMMDD_HHMMSS.json` — machine-readable findings
- `report_YYYYMMDD_HHMMSS.html` — dark Bootstrap 5 single-file HTML

Copy to USB stick by saying *"export"* via voice command (Button C hold → speak → release).

---

## 🧠 AI Architecture

```
User Input → Thought (LLM) → Action (tool call) → Observation (output) → Next Thought
                                     ↑                                           |
                                     └───────────────── loop ────────────────────┘
                                           (until task complete or risk > 8)
```

- **Model:** TinyLlama-1.1B-Q4_0 GGUF (≈ 620 MB on disk, ≈ 180 MB RAM)
- **Framework:** llama-cpp-python (CPU inference, no GPU needed)
- **Risk Scoring:** 1–10 per action (10 = destructive, auto-skip above threshold)

---

## 🗂️ Project Structure

```
NxtGenAI/
├── setup.sh          # One-command installer
├── main.py           # Boot splash → LLM load → main loop
├── ai_core.py        # ReAct reasoning + risk scoring
├── ui.py             # OLED driver + buttons (A/B/C)
├── tools.py          # nmap, hydra, aireplay-ng, sqlmap, ARP
├── power.py          # PiSugar I2C + low-power management
├── config.ini        # Paths, thresholds, model config
├── requirements.txt  # Minimal Python dependencies
├── README.md         # This file
└── LICENSE           # MIT
```

---

## 🔐 Wordlists

Pre-load to `/home/pi/wordlists/`:

```bash
# rockyou.txt (classic, 14M passwords):
sudo cp /usr/share/wordlists/rockyou.txt /home/pi/wordlists/

# 10k common passwords (bundled by setup.sh):
# /home/pi/wordlists/10k-common.txt  ← auto-downloaded during setup
```

---

## ⚙️ Power Management

| Battery Level | Action |
|---|---|
| > 20% | Normal operation |
| 10–20% | OLED dims to 50%, voice warns |
| < 10% | Save report, voice alert, graceful shutdown |

---

## 📦 RAM Budget

```
TinyLlama Q4_0 inference : ~180 MB
OLED UI + Python runtime :  ~30 MB
Tools (subprocess)        :  ~20 MB
OS overhead               :  ~60 MB
─────────────────────────────────────
Total                     : ~290 MB  (within 512 MB hardware limit)
Swap                      :  64 MB   (configured by setup.sh)
```

---

## ⚠️ Legal & Ethics

This tool is for **authorised penetration testing only**.  
Use only on networks and systems you own or have explicit written permission to test.  
The authors accept no liability for misuse. See [LICENSE](LICENSE).

---

## 🤝 Contributing

PRs welcome! Please follow PEP 8 and include comments explaining any non-obvious logic.

---

*Built with ❤️ and llama.cpp on a £15 computer.*
