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
