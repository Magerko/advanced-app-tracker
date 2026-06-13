"""How to (re)launch the application as a detached process.

Both Windows autorun and the guardian relaunch need a command that starts the
app independent of the current working directory. We launch the ``run.py``
bootstrap at the project root, which puts the package on ``sys.path`` and calls
``main()``.
"""

from __future__ import annotations

import os
import sys
from typing import List

from app_tracker.paths import project_root


def python_executable() -> str:
    """Return the interpreter to launch with (prefer windowless pythonw)."""
    exe = sys.executable
    if sys.platform == "win32" and exe:
        candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


def launcher_path() -> str:
    return str(project_root() / "run.py")


def launch_command() -> List[str]:
    """Argument list suitable for :class:`subprocess.Popen`."""
    return [python_executable(), launcher_path()]


def launch_command_string() -> str:
    """Quoted command string (for the Windows registry Run value)."""
    return f'"{python_executable()}" "{launcher_path()}"'
