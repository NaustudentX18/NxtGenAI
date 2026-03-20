#!/usr/bin/env python3
"""Repository-level entrypoint for OLED mode."""

from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nxtgenai.main import AppState, MODES, NxtGenAIApp, main

PentestGPTApp = NxtGenAIApp

__all__ = ["AppState", "MODES", "NxtGenAIApp", "PentestGPTApp", "main"]


if __name__ == "__main__":
    main()
