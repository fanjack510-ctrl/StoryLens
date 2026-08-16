"""任务列表混合时区排序 (CHG-20260815-097).

The task list merges two sources with different timestamp conventions: chapter runs come
back from SQLite naive, whole-book projections carry UTC-aware values. Ordering them raised
`TypeError: can't compare offset-naive and offset-aware datetimes`, which took GET
/api/v1/analysis-runs down with a 500 — and because an unhandled exception never reaches the
CORS middleware, the browser reported it as a CORS failure and the 开始分析 button did
nothing at all when clicked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.narrative_core.whole_book_v2.task_center_projection import _sort_key


class _Row:
    def __init__(self, created_at):
        self.created_at = created_at


def test_naive_and_aware_sort_together() -> None:
    naive = _Row(datetime(2026, 8, 15, 4, 0, 0))
    aware = _Row(datetime(2026, 8, 15, 5, 0, 0, tzinfo=timezone.utc))
    rows = [naive, aware]
    # The bug was here: sorting raised instead of returning an order.
    rows.sort(key=_sort_key, reverse=True)
    assert rows[0] is aware


def test_naive_is_read_as_utc_not_local() -> None:
    # Guessing local time would silently reorder runs by the machine's offset.
    naive = datetime(2026, 8, 15, 4, 0, 0)
    assert _sort_key(_Row(naive)) == naive.replace(tzinfo=timezone.utc)


def test_missing_timestamp_sorts_as_now_and_never_raises() -> None:
    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    value = _sort_key(_Row(None))
    assert value.tzinfo is not None
    assert value > before


def test_aware_value_is_untouched() -> None:
    aware = datetime(2026, 8, 15, 5, 0, 0, tzinfo=timezone.utc)
    assert _sort_key(_Row(aware)) is aware
