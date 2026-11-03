import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app_tracker.browser.api import create_app  # noqa: E402
from app_tracker.browser.storage import BrowserStorage  # noqa: E402
from app_tracker.core.database import DatabaseManager  # noqa: E402


@pytest.fixture
def client(tmp_path):
    db = DatabaseManager(tmp_path / "api.db")
    yield TestClient(create_app(BrowserStorage(db)))
    db.close()


def test_health(client):
    assert client.get("/health").json()["service"] == "browser-api"


def test_full_session_flow(client):
    sid = "b1f0c9de-8b2a-4f7c-9b6d-1d5a2b8f1234"
    start = client.post("/browser-event/start", json={
        "session_id": sid,
        "browser": "firefox",
        "url": "https://www.youtube.com/watch?v=abc",
        "title": "YouTube",
        "started_at": "2026-10-26T07:00:00.000Z",
    })
    assert start.json()["created"] is True

    assert client.post("/browser-event/update-title", json={
        "session_id": sid, "title": "Physics Lecture 4",
    }).json() == {"status": "ok"}

    stop = client.post("/browser-event/stop", json={
        "session_id": sid,
        "ended_at": "2026-10-26T07:12:30.000Z",
        "reason": "tab_switch",
    }).json()
    assert stop["duration_seconds"] == 750


def test_bad_request_is_rejected(client):
    assert client.post("/browser-event/start", json={"url": 5}).status_code == 422
