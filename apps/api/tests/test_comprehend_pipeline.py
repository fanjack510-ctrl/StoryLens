"""「读懂」接进产品之后的边界。

它挂在跟评测、拆文同一套任务机制上，所以要盯的是「挂对了没有」：读法分流、结果不串味、
读取口在没有结果时说人话。
"""

from __future__ import annotations

import json

from app.narrative_core.services.comprehend_pipeline_v1 import (
    COMPREHEND_MODE,
    COMPREHEND_RESULT_STAGE,
    load_comprehend_result,
    _as_dict,
)
from app.narrative_core.comprehend.contracts import (
    BookDigest,
    ChapterDigest,
    ComprehendResult,
    SectionDigest,
)


def test_the_stored_shape_keeps_the_trust_account() -> None:
    """覆盖率和可信标记必须落库。它们不是装饰——读者据此决定要不要回去读原文。"""
    res = ComprehendResult(
        book=BookDigest(one_paragraph="一段话"),
        chapters=[ChapterDigest(chapter="第1章", title="T",
                                sections=[SectionDigest(label="1.1", claims=["某个判断"])])],
        sections_total=10,
        sections_covered=10,
        provider_calls=12,
    )
    payload = _as_dict(res)
    assert payload["coverage"] == 1.0
    assert payload["trustworthy"] is True
    assert payload["schema_version"].startswith("comprehend/")
    # 能被 json 序列化 —— 它要存进检查点
    json.dumps(payload, ensure_ascii=False)


def test_a_partly_failed_run_is_not_marked_trustworthy() -> None:
    res = ComprehendResult(sections_total=10, sections_covered=6)
    assert _as_dict(res)["trustworthy"] is False


def test_reading_a_run_with_no_result_returns_none_not_a_crash(tmp_path) -> None:
    from sqlalchemy.orm import sessionmaker
    from tests.whole_book_minimal_test_helpers import make_engine

    engine = make_engine(tmp_path, "comprehend.db")
    with sessionmaker(bind=engine)() as session:
        assert load_comprehend_result(session, 999) is None


def test_the_result_stage_is_its_own_not_the_v2_one() -> None:
    """跟评测/拆文共用检查点键，会让「读懂」的结果被当成 V2 结果读出来。"""
    from app.narrative_core.whole_book_v2.repository import RESULT_STAGE

    assert COMPREHEND_RESULT_STAGE != RESULT_STAGE


def test_the_router_accepts_the_new_reading() -> None:
    """读法要能从请求一路传到分流点，否则这条线永远跑不起来。"""
    import inspect

    from app.routers import whole_book_free_product_router as mod

    src = inspect.getsource(mod)
    assert '"comprehend"' in src
    assert COMPREHEND_MODE == "comprehend"


def test_the_novel_profile_gate_does_not_block_a_monograph() -> None:
    """画像的五根轴是付费模式/读者/爽感引擎/人称/篇幅——全是网文的东西。

    那道门存在，是因为画像决定小说分析走哪个引擎、量哪几条类型轴；读懂一条都不用。
    让人去确认「这本人因工程手册的爽感引擎是什么」，是在问一个没有答案的问题。
    """
    import inspect

    from app.routers import whole_book_free_product_router as mod

    src = inspect.getsource(mod.create_free_analysis)
    assert 'analysis_mode == "comprehend"' in src, "读懂仍然要过画像门"
    # 小说那两种读法必须照旧受门约束 —— 画像对它们是真有用的
    assert "profile_confirmation_state(db, book_id)" in src


def test_the_progress_row_this_pipeline_writes_actually_validates() -> None:
    """ProgressV2 的字段全是必填，少一个就整条进度写不进去。

    第一次在产品里真跑就栽在这儿——而且异常被外层标成「模型中间结果格式不符合要求」，
    屏幕上显示的阶段还是层级引擎的 overview_synthesis，把人指向模型和另一个引擎。
    埋在闭包里的构造只有真跑一次才会炸，所以把它抽出来，让测试直接盯。
    """
    from app.narrative_core.services.comprehend_pipeline_v1 import build_progress

    p = build_progress(
        done=3, total=38, stage="digest_sections", action="正在逐节读取",
        elapsed=12.5, provider="deepseek", model="deepseek-v4-flash",
    )
    assert p.provider_calls_completed == 3
    assert p.total_windows == 38
    assert p.current_action == "正在逐节读取"

    # 一次调用都还没完成时不能除零，也不能报出荒唐的剩余时间
    zero = build_progress(
        done=0, total=38, stage="parse_structure", action="正在识别章节结构",
        elapsed=0.0, provider="p", model="m",
    )
    assert zero.overall_percent == 0
    assert zero.estimated_remaining_seconds >= 0


def _seed_run(session, run_id: int, book_id: int, engine_version: str):
    from app.db.models import Book, BookSnapshot, WholeBookRun, utc_now

    if session.get(Book, book_id) is None:
        session.add(Book(id=book_id, title="书", source_file_name="a.pdf", source_file_hash=f"h{book_id}"))
        session.add(BookSnapshot(id=book_id, book_id=book_id, content_hash=f"c{book_id}",
                                 snapshot_status="completed"))
    session.add(
        WholeBookRun(
            id=run_id, book_id=book_id, snapshot_id=book_id, mode="whole_book_native",
            status="completed", idempotency_key=f"k{run_id}", engine_id="comprehend_engine",
            engine_version=engine_version, contract_version="whole_book_contract_v1",
            result_origin="formal", started_at=utc_now(),
        )
    )
    session.commit()


def test_a_finished_comprehend_run_is_visible_to_the_page(tmp_path) -> None:
    """跑完的「读懂」如果页面看不见，页面就跳回「开始分析」——用户以为没跑成，再点一次，
    再付一次钱。实测同一本书因此被连开了三个任务。
    """
    from sqlalchemy.orm import sessionmaker

    from app.narrative_core.services.comprehend_pipeline_v1 import _save_result
    from app.narrative_core.services.whole_book_free_product_v1_service import (
        _completed_v2_run,
        reading_of_run,
    )
    from tests.whole_book_minimal_test_helpers import make_engine

    engine = make_engine(tmp_path, "cmp-visible.db")
    with sessionmaker(bind=engine)() as session:
        _seed_run(session, 30, 1, "comprehend-engine-1.0")
        _save_result(session, 30, {"provider_calls": 5, "sections_covered": 8, "sections_total": 8})
        session.commit()

        found = _completed_v2_run(session, 1)
        assert found is not None and found.id == 30
        assert reading_of_run(found) == "comprehend"


def test_a_completed_run_with_no_result_at_all_still_does_not_count(tmp_path) -> None:
    """没有结果的「完成」不是完成。放行它，页面会显示一份空报告。"""
    from sqlalchemy.orm import sessionmaker

    from app.narrative_core.services.whole_book_free_product_v1_service import _completed_v2_run
    from tests.whole_book_minimal_test_helpers import make_engine

    engine = make_engine(tmp_path, "cmp-empty.db")
    with sessionmaker(bind=engine)() as session:
        _seed_run(session, 31, 2, "comprehend-engine-1.0")
        assert _completed_v2_run(session, 2) is None
