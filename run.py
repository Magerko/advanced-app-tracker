#!/usr/bin/env python3
"""Launcher used by Windows autorun and by the guardian relaunch.

Adds the project root to sys.path so the app starts from any working directory.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_tracker.app import main  # noqa: E402

if __name__ == "__main__":
    main()
