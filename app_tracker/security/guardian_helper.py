"""Guardian watcher process.

Run as::

    python -m app_tracker.security.guardian_helper <main_pid> <create_time> <signal_file>

Watches the main application and relaunches it if it dies unexpectedly.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

import psutil

from app_tracker.config import (
    GUARDIAN_MAX_RELAUNCHES,
    GUARDIAN_POLL_INTERVAL_SECONDS,
    GUARDIAN_RELAUNCH_WINDOW_SECONDS,
)
from app_tracker.logging_setup import configure_logging
from app_tracker.paths import data_dir, project_root
from app_tracker.platform_support.launch import launch_command

log = logging.getLogger("guardian")

_CREATE_TIME_TOLERANCE_S = 2.0
_RELAUNCH_HISTORY = data_dir() / "guardian_relaunch.history"


def _main_is_alive(pid: int, create_time: float) -> bool:
    try:
        proc = psutil.Process(pid)
        if create_time and abs(proc.create_time() - create_time) > _CREATE_TIME_TOLERANCE_S:
            return False  # the PID was reused by a different process
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _recent_relaunches() -> list[float]:
    try:
        lines = _RELAUNCH_HISTORY.read_text(encoding="utf-8").split()
    except OSError:
        return []
    now = time.time()
    out = []
    for line in lines:
        try:
            ts = float(line)
        except ValueError:
            continue
        if now - ts <= GUARDIAN_RELAUNCH_WINDOW_SECONDS:
            out.append(ts)
    return out


def _record_relaunch(history: list[float]) -> None:
    try:
        _RELAUNCH_HISTORY.write_text(
            "\n".join(f"{ts:.3f}" for ts in history), encoding="utf-8"
        )
    except OSError as exc:
        log.warning("Could not record relaunch history: %s", exc)


def _relaunch() -> bool:
    history = _recent_relaunches()
    if len(history) >= GUARDIAN_MAX_RELAUNCHES:
        log.error(
            "Relaunch back-off hit (%d in %ds); giving up to avoid a crash-loop.",
            len(history), GUARDIAN_RELAUNCH_WINDOW_SECONDS,
        )
        return False

    history.append(time.time())
    _record_relaunch(history)

    kwargs = {"cwd": str(project_root())}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(launch_command(), **kwargs)
        log.info("Main application relaunched.")
        return True
    except OSError as exc:
        log.error("Relaunch failed: %s", exc)
        return False


def _consume_signal(signal_file: Path) -> bool:
    if signal_file.exists():
        try:
            signal_file.unlink()
        except OSError:
            pass
        return True
    return False


def run(main_pid: int, create_time: float, signal_file: Path) -> int:
    log.info("Guardian watching PID %s (signal: %s).", main_pid, signal_file)
    while True:
        if _consume_signal(signal_file):
            log.info("Clean-shutdown signal received; exiting without relaunch.")
            return 0

        if not _main_is_alive(main_pid, create_time):
            # Re-check the signal to avoid racing a simultaneous clean exit.
            if _consume_signal(signal_file):
                log.info("Main exited cleanly; not relaunching.")
                return 0
            log.warning("Main process %s vanished unexpectedly.", main_pid)
            _relaunch()
            # The relaunched app spawns its own guardian, so we exit either way.
            return 0

        time.sleep(GUARDIAN_POLL_INTERVAL_SECONDS)


def main(argv: list[str] | None = None) -> int:
    configure_logging(tag="guardian")
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 3:
        log.error("Usage: guardian_helper <main_pid> <create_time> <signal_file>")
        return 2
    try:
        main_pid = int(argv[0])
        create_time = float(argv[1])
    except ValueError:
        log.error("Invalid arguments: %s", argv)
        return 2
    signal_file = Path(argv[2])
    try:
        return run(main_pid, create_time, signal_file)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
