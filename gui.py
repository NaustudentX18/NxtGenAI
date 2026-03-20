#!/usr/bin/env python3
"""Repository-level entrypoint for desktop GUI mode."""

from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nxtgenai.gui import main


if __name__ == "__main__":
    main()
