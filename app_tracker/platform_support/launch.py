"""Command used to (re)launch the app as a detached process.

Both Windows autorun and the guardian relaunch run ``run.py`` at the project
root so the package ends up on ``sys.path`` regardless of the working directory.
"""

from __future__ import annotations

import os
import sys
from typing import List

from app_tracker.paths import project_root


def python_executable() -> str:
    exe = sys.executable
    if sys.platform == "win32" and exe:
        # Prefer the windowless interpreter so no console flashes up.
        candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


def launcher_path() -> str:
    return str(project_root() / "run.py")


def launch_command() -> List[str]:
    return [python_executable(), launcher_path()]


def launch_command_string() -> str:
    return f'"{python_executable()}" "{launcher_path()}"'
