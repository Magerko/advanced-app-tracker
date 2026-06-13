#!/usr/bin/env python3
"""Bootstrap launcher.

Runs the application regardless of the current working directory by putting
this file's directory (the project root) on ``sys.path``. This is the command
used by Windows autorun and by the guardian when it relaunches the app.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_tracker.app import main  # noqa: E402

if __name__ == "__main__":
    main()
