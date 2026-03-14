# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Yes     |

Only the latest release on the `main` branch receives security fixes. Please upgrade before reporting a vulnerability.

---

## Responsible Disclosure

**Please do NOT open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in PentestGPT-lite, please report it privately so it can be fixed before it is disclosed publicly.

### How to Report

1. **Email:** Open a [GitHub Security Advisory](https://github.com/NaustudentX18/NxtGenAI/security/advisories/new) (preferred — keeps the report private and tracked).
2. Alternatively, email the maintainer directly. Find the contact in the [GitHub profile](https://github.com/NaustudentX18).

### What to Include

- A description of the vulnerability and its potential impact.
- Steps to reproduce (proof-of-concept code if applicable).
- The version of PentestGPT-lite affected.
- Any suggested mitigations.

### Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgement | Within 72 hours |
| Triage and severity assessment | Within 7 days |
| Fix or mitigation | Within 30 days (critical), 90 days (others) |
| Public disclosure | After fix is released |

---

## Scope

### In Scope

- Vulnerabilities in Python source files (`main.py`, `ai_core.py`, `ui.py`, `tools.py`, `power.py`, `voice_input.py`, `gui.py`).
- Insecure defaults in `config.ini` that could expose users to risk.
- Issues in `setup.sh` that could compromise the host system (e.g., insecure file permissions, unvalidated downloads).
- Injection vulnerabilities in tool wrappers in `tools.py` (command injection via unsanitised user input).

### Out of Scope

- Vulnerabilities in third-party tools invoked by PentestGPT-lite (nmap, hydra, aircrack-ng, sqlmap, etc.). Report those to the respective upstream projects.
- Issues that require physical access to a device where the operator already has root (the device is a personal pentest tool, root access is by design).
- The TinyLlama model file itself — report model-level issues to [Mozilla-Ocho/llamafile](https://github.com/Mozilla-Ocho/llamafile) or the llama.cpp project.

---

## Security Design Notes

PentestGPT-lite is designed for **offline, stand-alone use** on a Raspberry Pi you own. Key design decisions:

- **No internet connectivity required or expected.** All inference is local; no data leaves the device.
- **Risk scoring (1–10)** in `ai_core.py` prevents the AI from autonomously executing high-risk actions (threshold configurable in `config.ini` under `[security]`).
- **Confirmation prompts** are required for actions with risk score ≥ `confirm_threshold` (default: 6).
- **Reports** are stored locally in `/home/pi/reports/` and are only exported manually via USB.

---

## Legal Notice

This tool is for **authorised penetration testing only**. Use it only on networks and systems you own or have explicit written permission to test. The authors accept no liability for misuse. See [LICENSE](LICENSE).
