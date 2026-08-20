"""两种读法都能被找到——页面原先只能到达最后跑完的那一份。"""
from types import SimpleNamespace

from app.narrative_core.services.whole_book_free_product_v1_service import reading_of_run


def test_reading_is_read_back_from_engine_version():
    assert reading_of_run(SimpleNamespace(engine_version="long-novel-engine-1.0+story_breakdown")) == "story_breakdown"
    assert reading_of_run(SimpleNamespace(engine_version="long-novel-engine-1.0")) == "diagnostic"


def test_missing_or_empty_engine_version_reads_as_diagnostic():
    # 旧运行行上这一列可能是空的。空不等于拆文——默认落在评测上，不会凭空多出一份报告。
    assert reading_of_run(SimpleNamespace(engine_version="")) == "diagnostic"
    assert reading_of_run(SimpleNamespace(engine_version=None)) == "diagnostic"
    assert reading_of_run(SimpleNamespace()) == "diagnostic"


def test_suffix_must_be_at_the_end():
    # 「+story_breakdown」出现在中间不算——只认结尾那个标记。
    assert reading_of_run(SimpleNamespace(engine_version="x+story_breakdown-2.0")) == "diagnostic"
