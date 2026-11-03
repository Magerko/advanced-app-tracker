"""Local HTTP API used by the browser extension (127.0.0.1 only)."""
from __future__ import annotations

import logging
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_tracker.browser.models import (
    BrowserStartEvent,
    BrowserStopEvent,
    BrowserTitleEvent,
)
from app_tracker.browser.storage import BrowserStorage

log = logging.getLogger(__name__)

HOST = "127.0.0.1"  # never expose this to the network


def create_app(storage: BrowserStorage) -> FastAPI:
    api = FastAPI(title="Advanced App Tracker Browser API")
    # noinspection PyTypeChecker
    api.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(moz|chrome)-extension://[A-Za-z0-9_.-]+$",
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @api.get("/health")
    def health():
        return {"status": "ok", "app": "advanced-app-tracker", "service": "browser-api"}

    @api.post("/browser-event/start")
    def start_event(event: BrowserStartEvent):
        created = storage.start_session(
            event.session_id, event.browser, event.url, event.title, event.started_at
        )
        return {"status": "ok", "created": created, "session_id": event.session_id}

    @api.post("/browser-event/update-title")
    def title_event(event: BrowserTitleEvent):
        storage.update_title(event.session_id, event.title)
        return {"status": "ok"}

    @api.post("/browser-event/stop")
    def stop_event(event: BrowserStopEvent):
        duration = storage.stop_session(event.session_id, event.ended_at)
        return {"status": "ok", "duration_seconds": duration, "reason": event.reason}

    return api


class BrowserApiServer:
    """Runs uvicorn in a background thread and can be stopped cleanly."""

    def __init__(self, storage: BrowserStorage, port: int) -> None:
        self.port = port
        config = uvicorn.Config(
            create_app(storage), host=HOST, port=port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="browser-api", daemon=True
        )
        self._thread.start()
        log.info("Browser API starting on %s:%s", HOST, self.port)

    def _run(self) -> None:
        try:
            self._server.run()
        except (Exception, SystemExit):
            # uvicorn calls sys.exit(1) when the port is already taken.
            log.exception("Browser API stopped (is port %s busy?)", self.port)

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=3.0)
