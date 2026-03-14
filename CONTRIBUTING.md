# Contributing to PentestGPT-lite

Thank you for your interest in contributing to PentestGPT-lite! This guide explains how to contribute code, documentation, and bug reports effectively.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Testing](#testing)
- [Commit Messages](#commit-messages)

---

## Code of Conduct

This project is intended for **authorised penetration testing research and education only**. Contributions that introduce capabilities intended for illegal or unethical use will not be accepted. Please keep all discussion respectful and constructive.

---

## Reporting Bugs

1. Search [existing issues](https://github.com/NaustudentX18/NxtGenAI/issues) to avoid duplicates.
2. Open a new issue with:
   - A clear, descriptive title.
   - Steps to reproduce the problem.
   - Expected behaviour vs. actual behaviour.
   - Hardware details (Pi Zero 2 W, OS version, Python version).
   - Relevant log output (from `journalctl -u pentestgpt` or the terminal).

---

## Suggesting Features

Open an issue with the `enhancement` label. Describe:
- The use case / problem it solves.
- How it fits within the offline, resource-constrained (512 MB RAM) design philosophy.
- Any hardware implications (new sensors, interfaces, etc.).

---

## Pull Request Process

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** — keep commits focused and atomic.

3. **Test** on real hardware (Raspberry Pi Zero 2 W) if your change touches hardware drivers (`ui.py`, `power.py`). For software-only changes, see [docs/development.md](docs/development.md) for how to test without physical hardware.

4. **Lint** your Python code:
   ```bash
   pip install flake8
   flake8 --max-line-length=100 *.py
   ```

5. **Update documentation** in `README.md`, `docs/`, or inline comments if your change affects user-visible behaviour or configuration.

6. **Open a Pull Request** against `main`. Fill in the PR template with:
   - What problem is solved.
   - How it was tested.
   - Any breaking changes.

7. A maintainer will review your PR within a reasonable time. Address review comments promptly.

---

## Code Style

- Follow **[PEP 8](https://peps.python.org/pep-0008/)** for Python code.
- Maximum line length: **100 characters**.
- Use **descriptive variable names** — avoid single-letter names except in comprehensions.
- Add **inline comments** explaining non-obvious logic, especially around hardware I/O, LLM prompting, and risk scoring.
- Do **not** add external network calls — this project is designed to work fully offline.

### Example: Adding a New Tool

When adding a new pentest tool to `tools.py`, follow the existing pattern:

```python
def run_my_tool(target: str, options: dict) -> dict:
    """
    Run my-tool against target.

    Args:
        target: IP address or hostname to scan.
        options: dict of optional parameters.

    Returns:
        dict with keys 'stdout', 'stderr', 'returncode'.
    """
    cmd = ["my-tool", "--flag", target]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
```

---

## Testing

There is currently no automated test suite (hardware-in-the-loop testing is complex). Contributions that add unit tests for pure-Python logic (e.g., risk scoring in `ai_core.py`, report formatting) are especially welcome.

### Manual Testing Checklist

Before opening a PR, verify:

- [ ] `python3 -m py_compile *.py` — no syntax errors.
- [ ] `flake8 --max-line-length=100 *.py` — no PEP 8 violations.
- [ ] The specific feature or fix works as expected (document how you tested it in the PR).
- [ ] No new warnings printed to stderr during normal operation.
- [ ] RAM usage stays within budget (`free -m` after startup should show < 350 MB used).

See [docs/development.md](docs/development.md) for setting up a development environment without physical hardware.

---

## Commit Messages

Use the **imperative mood** and be concise:

- ✅ `Add nmap UDP scan support to tools.py`
- ✅ `Fix PiSugar I2C timeout on cold boot`
- ❌ `fixed stuff`
- ❌ `changes`

For larger changes, include a short body paragraph explaining *why* the change was made.
