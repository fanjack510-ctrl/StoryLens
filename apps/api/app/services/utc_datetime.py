"""UTC-aware datetime serialization helpers for API responses."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc_aware(value: datetime | None) -> datetime | None:
    """Treat naive datetimes as UTC; convert aware values to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_iso_z(value: datetime | None) -> str | None:
    """Serialize datetime as RFC3339 UTC with trailing Z."""
    aware = ensure_utc_aware(value)
    if aware is None:
        return None
    text = aware.isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


__all__ = ["ensure_utc_aware", "utc_iso_z"]
