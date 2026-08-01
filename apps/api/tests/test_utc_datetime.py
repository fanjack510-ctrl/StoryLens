"""UTC datetime serialization helpers."""

from datetime import datetime, timezone

from app.services.utc_datetime import ensure_utc_aware, utc_iso_z


def test_naive_becomes_utc_aware():
    naive = datetime(2026, 7, 28, 15, 5, 7, 191528)
    aware = ensure_utc_aware(naive)
    assert aware is not None
    assert aware.tzinfo == timezone.utc
    assert utc_iso_z(naive) == "2026-07-28T15:05:07.191528Z"


def test_aware_utc_preserved():
    value = datetime(2026, 7, 28, 15, 5, 7, tzinfo=timezone.utc)
    assert utc_iso_z(value) == "2026-07-28T15:05:07Z"
