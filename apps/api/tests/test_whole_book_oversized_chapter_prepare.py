"""一章塞不进窗口时，准备接口不该整页失败。

这道闸门本来是给小说那两种读法的：评测和拆文要把一章塞进一个窗口，一章过大就是真读不了。
但它原本让 `prepare` 直接抛错，于是整个全书分析页只剩一句「无法读取数据」。

代价是具体的：那本 1603 页的人因工程手册有一节 22.5 万字符，于是**唯一读得了它的那种读法
（读懂）也被一起埋了**——而读懂根本不用窗口，超长的节由规划器按段落切开。

所以这里钉两件事：页面能开；三种读法的可用性各归各位。
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import sessionmaker

from app.db.models import Book, Chapter, Paragraph, ProviderConfiguration
from app.narrative_core.services.whole_book_free_product_v1_service import (
    prepare_free_whole_book_analysis_v1,
)
from tests.whole_book_minimal_test_helpers import make_engine


def _seed_book_with_one_huge_chapter(session, *, chapters: int, chars_per: int, huge_chars: int):
    from app.services.whole_book_source_fingerprint import sha256_utf8

    book = Book(
        title="oversized",
        source_file_name="oversized.txt",
        source_file_hash=sha256_utf8(f"oversized-{uuid.uuid4()}"),
        import_status="ready",
    )
    session.add(book)
    session.flush()
    for i in range(1, chapters + 1):
        body = "汉" * (huge_chars if i == 2 else chars_per)
        ch = Chapter(book_id=book.id, chapter_index=i, title=f"第{i}章", word_count=len(body))
        session.add(ch)
        session.flush()
        session.add(
            Paragraph(
                id=f"p-{book.id}-{i}",
                book_id=book.id,
                chapter_id=ch.id,
                paragraph_index=0,
                raw_text=body,
                normalized_text=body,
                char_start=0,
                char_end=len(body),
                content_hash=sha256_utf8(f"{book.id}-{i}"),
            )
        )
    provider = ProviderConfiguration(
        provider_name="deepseek",
        plus_model="deepseek-v4-flash",
        enabled=True,
        disconnected=False,
    )
    session.add(provider)
    session.commit()
    session.refresh(book)
    return book


def test_oversized_chapter_keeps_the_page_open_and_lets_comprehend_run(tmp_path):
    engine = make_engine(tmp_path, "oversized-prepare.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed_book_with_one_huge_chapter(
            session, chapters=6, chars_per=2000, huge_chars=400_000
        )

        for mode in ("diagnostic", "story_breakdown"):
            payload = prepare_free_whole_book_analysis_v1(session, book.id, analysis_mode=mode)
            # 页面能开——这是整条修复的重点，抛异常就等于整页「无法读取数据」。
            assert payload["book_id"] == book.id
            reason = payload["chapter_too_large_reason"]
            assert reason and "超出了一次分析能读的长度" in reason
            assert reason in payload["blocking_reasons"]
            assert payload["run_creation_enabled"] is False
            assert payload["context_safe"] is False
            # 预估说不出数时给的是空值，不是编出来的数字——也不是 0，0 会被读成「不要钱」。
            assert payload["estimate"]["estimated_provider_calls"] is None
            assert payload["estimate"]["estimated_windows"] is None
            assert payload["estimate"]["price_known"] is False
            # 但行是真的：开跑要靠它绑定服务商配置，没有行就报「缺少字段 estimate_id」。
            assert isinstance(payload["estimate"]["estimate_id"], int)

        got = prepare_free_whole_book_analysis_v1(session, book.id, analysis_mode="comprehend")
        # 读懂按节读，一章过大跟它无关：原因照样说给界面听，但不进阻断清单、也不禁用它。
        assert got["chapter_too_large_reason"]
        assert got["chapter_too_large_reason"] not in got["blocking_reasons"]
        # 「没有被扣掉」比「等于 True」更贴切：能不能开跑还取决于服务商是否可用（测试环境里
        # 不可用），这里要证的是一章过大没有额外扣掉读懂的任何东西。
        assert got["run_creation_enabled"] == bool(
            got["real_provider_enabled"] and got["provider_available"]
        )


def test_unavailable_estimate_row_is_reused_not_reinserted(tmp_path):
    """轮询不能每调一次插一行。

    这个页面在有任务跑着时每 3 秒调一次准备接口。上一次就是这里把写锁撑爆的——日志里
    84 次 `database is locked` 全出自「一个纯看的页面成了写入方」。
    """
    from app.db.models import WholeBookCostEstimate

    engine = make_engine(tmp_path, "oversized-reuse.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed_book_with_one_huge_chapter(
            session, chapters=6, chars_per=2000, huge_chars=400_000
        )
        ids = set()
        for _ in range(4):
            payload = prepare_free_whole_book_analysis_v1(
                session, book.id, analysis_mode="comprehend"
            )
            ids.add(payload["estimate"]["estimate_id"])
        assert len(ids) == 1
        rows = session.query(WholeBookCostEstimate).filter(
            WholeBookCostEstimate.book_id == book.id
        ).count()
        assert rows == 1
