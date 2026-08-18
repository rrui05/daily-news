"""Time-window policy for freshness guarantees."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import ResearchWindow


SHANGHAI_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def normalize_topic(topic: str | None) -> str | None:
    if topic is None:
        return None
    normalized = topic.replace("\u3000", " ").strip()
    return normalized or None


def normalize_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(SHANGHAI_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=SHANGHAI_TZ)
    return now.astimezone(SHANGHAI_TZ)


def create_window(topic: str | None, now: datetime | None = None) -> ResearchWindow:
    ended_at = normalize_now(now)
    hours = 168 if normalize_topic(topic) else 24
    return ResearchWindow(
        started_at=ended_at - timedelta(hours=hours),
        ended_at=ended_at,
    )

