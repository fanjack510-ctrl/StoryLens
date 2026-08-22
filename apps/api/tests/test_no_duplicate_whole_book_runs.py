"""同一本书不该在十几秒内起两个全书分析。

今天两次都栽在这里：《我不是戏神》相差 10 秒起了两个（run 14 / 15），《余罪》相差 14 秒起了
两个（run 19 / 20）。多出来的那个做完一两次调用就杵住，而页面挑任务挑的是「最新的那个」——
于是屏幕盯着空壳，真正在跑的那个反倒看不见。用户看到的是「卡在 4%」「无法读取数据」「点重新
分析还是这个界面」，三个症状同一个根。

已有的幂等键拦不住：它的输入里含 client_request_id，每次点击都是新的，所以它防的是「同一个
请求重试」，不是「点了两次」。

判活必须用心跳而不是创建时刻——两个方向都是坑：
  · 用创建时刻，1299 章跑三小时的任务会被当成僵尸，用户中途能再起一个；
  · 完全不判活，一个死掉的任务会把这本书的开始按钮永久堵住（今天就是我用接口手工取消才解开的）。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import Book, BookSnapshot, WholeBookRun, utc_now
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_free_product_v1_service import (
    LIVE_RUN_STALE_AFTER,
    live_run_for_book,
)
from tests.whole_book_minimal_test_helpers import make_engine


@pytest.fixture()
def session(tmp_path):
    engine = make_engine(tmp_path, "dup-runs.db")
    with sessionmaker(bind=engine)() as s:
        s.add(Book(id=1, title="我不是戏神", source_file_name="a.txt", source_file_hash="h"))
        s.add(BookSnapshot(id=1, book_id=1, content_hash="c1", snapshot_status="completed"))
        s.commit()
        yield s


def _run(session, run_id: int, status: str, *, heartbeat=None, started=None) -> WholeBookRun:
    row = WholeBookRun(
        id=run_id,
        book_id=1,
        snapshot_id=1,
        mode="whole_book_native",
        status=status,
        idempotency_key=f"k{run_id}",
        engine_id="long_novel_engine",
        engine_version="long-novel-engine-1.0",
        contract_version="whole_book_contract_v1",
        result_origin="formal",
        started_at=started or utc_now(),
        last_heartbeat_at=heartbeat,
    )
    session.add(row)
    session.commit()
    return row


def test_a_running_analysis_is_found_so_a_second_one_is_never_created(session) -> None:
    _run(session, 14, WholeBookRunStatus.running.value, heartbeat=utc_now())
    live = live_run_for_book(session, 1)
    assert live is not None and live.id == 14


def test_a_three_hour_run_is_still_alive_as_long_as_it_keeps_paying(session) -> None:
    """1299 章要跑三个多小时。按创建时刻判活，它半路就会被当成僵尸——而它正在花钱。"""
    _run(
        session,
        14,
        WholeBookRunStatus.running.value,
        started=utc_now() - timedelta(hours=3),
        heartbeat=utc_now() - timedelta(seconds=30),
    )
    assert live_run_for_book(session, 1) is not None


def test_a_wedged_run_stops_blocking_the_book(session) -> None:
    """反方向的坑：run 20 心跳停了二十分钟，页面却一直显示它，开始按钮再也点不出来。

    今天是我用取消接口手工解开的——产品自己得能解开。
    """
    _run(
        session,
        20,
        WholeBookRunStatus.running.value,
        heartbeat=utc_now() - LIVE_RUN_STALE_AFTER - timedelta(minutes=1),
    )
    assert live_run_for_book(session, 1) is None


def test_a_run_with_no_heartbeat_yet_gets_the_same_grace(session) -> None:
    """刚创建、第一条进度还没写出来的任务，也算活着——否则连点两下照样是两个任务。"""
    _run(session, 21, WholeBookRunStatus.pending.value, started=utc_now(), heartbeat=None)
    assert live_run_for_book(session, 1) is not None


def test_finished_runs_never_block_a_new_one(session) -> None:
    for i, st in enumerate(
        (
            WholeBookRunStatus.completed.value,
            WholeBookRunStatus.failed.value,
            WholeBookRunStatus.cancelled.value,
        ),
        start=30,
    ):
        _run(session, i, st, heartbeat=utc_now())
    assert live_run_for_book(session, 1) is None


def test_another_books_run_does_not_block_this_one(session) -> None:
    session.add(Book(id=2, title="余罪", source_file_name="b.txt", source_file_hash="h2"))
    session.add(BookSnapshot(id=2, book_id=2, content_hash="c2", snapshot_status="completed"))
    session.commit()
    _run(session, 19, WholeBookRunStatus.running.value, heartbeat=utc_now())
    assert live_run_for_book(session, 2) is None
    assert live_run_for_book(session, 1) is not None
