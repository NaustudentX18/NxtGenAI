"""Compatibility wrapper for src-layout package imports."""

from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nxtgenai.ai_core import AICore

__all__ = ["AICore"]
