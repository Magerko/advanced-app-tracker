"""Request bodies sent by the browser extension."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BrowserStartEvent(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    browser: str = Field(default="firefox", max_length=32)
    url: str
    title: str = ""
    started_at: datetime
    window_id: Optional[int] = None
    tab_id: Optional[int] = None


class BrowserTitleEvent(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    title: str = ""


class BrowserStopEvent(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    ended_at: datetime
    reason: str = "unknown"
