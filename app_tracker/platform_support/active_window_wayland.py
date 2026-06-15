"""
Поддержка KDE Plasma на Wayland — отслеживание активного окна.

Как это работает:
- При старте устанавливается маленький скрипт в KWin, который подписывается
  на событие смены активного окна и пишет в journald строку вида
  ACTIVE_WINDOW:<pid>|<resourceName>|<заголовок>
- Отдельный поток читает journalctl -f и обновляет последнее известное окно.
- Основной поток просто читает из памяти — никаких subprocess на каждый тик.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Optional

import psutil

log = logging.getLogger(__name__)

# то что KWin будет выполнять внутри себя
_KWIN_SCRIPT = """\
workspace.windowActivated.connect(function(client) {
    if (client) {
        print("ACTIVE_WINDOW:" + client.pid + "|" + client.resourceName + "|" + client.caption);
    }
});
"""

_SCRIPT_DIR = os.path.expanduser(
    "~/.local/share/kwin/scripts/activewindowtracker/contents/code"
)
_SCRIPT_PATH = os.path.join(_SCRIPT_DIR, "main.js")
_METADATA_PATH = os.path.expanduser(
    "~/.local/share/kwin/scripts/activewindowtracker/metadata.json"
)

# последнее известное активное окно, обновляется из фонового потока
_lock = threading.Lock()
_latest: Optional[tuple[Optional[int], str, str]] = None  # (pid, resource_name, заголовок)


def _install_kwin_script() -> None:
    """Записать скрипт на диск, если его ещё нет или он изменился."""
    os.makedirs(_SCRIPT_DIR, exist_ok=True)

    current = ""
    if os.path.exists(_SCRIPT_PATH):
        with open(_SCRIPT_PATH) as f:
            current = f.read()

    if current != _KWIN_SCRIPT:
        with open(_SCRIPT_PATH, "w") as f:
            f.write(_KWIN_SCRIPT)
        log.info("KWin active-window script written to %s", _SCRIPT_PATH)

    if not os.path.exists(_METADATA_PATH):
        with open(_METADATA_PATH, "w") as f:
            json.dump({"KPlugin": {"Name": "ActiveWindowTracker", "Version": "1.0"}}, f)


def _load_kwin_script() -> None:
    """Попросить KWin загрузить скрипт через DBus."""
    try:
        result = subprocess.run(
            [
                "qdbus", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting.loadScript",
                _SCRIPT_PATH, "activewindowtracker",
            ],
            capture_output=True, text=True, timeout=3,
        )
        script_id = result.stdout.strip()
        if script_id.isdigit():
            subprocess.run(
                [
                    "qdbus", "org.kde.KWin", f"/Scripting/Script{script_id}",
                    "org.kde.kwin.Script.run",
                ],
                capture_output=True, timeout=3,
            )
            log.info("KWin active-window script loaded (id=%s)", script_id)
        else:
            log.warning("KWin вернул неожиданный ответ при загрузке скрипта: %r", result.stdout)
    except Exception as exc:
        log.warning("Не удалось загрузить KWin скрипт: %s", exc)


def _parse_line(line: str) -> Optional[tuple[Optional[int], str, str]]:
    """Вытащить pid, имя и заголовок из строки journald."""
    marker = "ACTIVE_WINDOW:"
    idx = line.find(marker)
    if idx == -1:
        return None
    payload = line[idx + len(marker):]
    parts = payload.split("|", 2)
    if len(parts) < 3:
        return None
    pid_str, resource_name, caption = parts[0].strip(), parts[1].strip(), parts[2].strip()
    pid = int(pid_str) if pid_str.isdigit() else None
    return pid, resource_name, caption


def _journald_watcher() -> None:
    """Фоновый поток: читает journalctl -f и обновляет _latest."""
    global _latest
    try:
        proc = subprocess.Popen(
            ["journalctl", "-f", "-g", "ACTIVE_WINDOW:", "_COMM=kwin_wayland"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        for line in proc.stdout:
            parsed = _parse_line(line)
            if parsed:
                with _lock:
                    _latest = parsed
    except Exception as exc:
        log.warning("journald watcher упал: %s", exc)


_started = False


def ensure_started() -> None:
    """Установить скрипт и запустить watcher-поток. Можно звать сколько угодно раз."""
    global _started
    if _started:
        return
    _started = True
    _install_kwin_script()
    _load_kwin_script()
    t = threading.Thread(target=_journald_watcher, daemon=True, name="kwin-journald-watcher")
    t.start()
    log.info("Wayland active-window watcher запущен.")


def get_active_window_wayland() -> Optional[tuple[Optional[int], Optional[str], Optional[str], Optional[str]]]:
    """
    Вернуть (pid, process_name, executable_path, window_title) для активного окна
    под KDE Plasma Wayland, или None если ещё ничего не поймали.
    """
    ensure_started()
    with _lock:
        info = _latest

    if info is None:
        return None

    pid, resource_name, caption = info
    process_name: Optional[str] = resource_name or None
    executable_path: Optional[str] = None

    if pid:
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                process_name = proc.name()
                executable_path = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return pid, process_name, executable_path, caption
