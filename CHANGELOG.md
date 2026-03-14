# Changelog

All notable changes to PentestGPT-lite will be documented in this file.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `CONTRIBUTING.md` — contributor guidelines, code style, and PR process.
- `CHANGELOG.md` — this file.
- `SECURITY.md` — security policy and responsible disclosure process.
- `docs/troubleshooting.md` — common issues and fixes.
- `docs/development.md` — guide for developing and testing without physical hardware.
- Updated `README.md` with links to new documentation files.

---

## [1.0.0] — 2026-03-13

### Added
- Initial public release of PentestGPT-lite.
- `main.py` — boot splash, LLM loading, and main event loop.
- `ai_core.py` — TinyLlama-powered ReAct reasoning loop with 1–10 risk scoring.
- `ui.py` — SSD1306 128×64 OLED driver with button A/B/C support.
- `tools.py` — wrappers for nmap, hydra, aircrack-ng/aireplay-ng, sqlmap, ARP.
- `power.py` — PiSugar 3 I2C battery monitor with automatic low-power shutdown.
- `voice_input.py` — push-to-talk voice command input using Vosk offline speech recognition.
- `gui.py` — optional Tkinter desktop GUI for development and testing.
- `config.ini` — single configuration file for all paths, thresholds, and settings.
- `setup.sh` — one-command installer (system packages, venv, model download, systemd service).
- `requirements.txt` — pinned Python dependencies for Raspberry Pi OS Bookworm.
- Four operation modes: WiFi Crack, Web Pentest, Network Recon, Full Auto (AI).
- Auto-generated JSON and HTML reports per session.
- Voice export of reports to USB via Button C hold.

[Unreleased]: https://github.com/NaustudentX18/NxtGenAI/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/NaustudentX18/NxtGenAI/releases/tag/v1.0.0
