"""跨书检索：在所有分析过的书里找东西。

「我记得有本书用过一个『主角没报名却被选上』的桥段——是哪本？」这个问题以前在产品里
无法回答：分析结果按书分开存着。

这个文件钉的几条，都是实跑时踩过的：一本书的几份文档必须取并集（不然半边内容
搜不到）、截断了必须说、按意思找只覆盖写法层这件事必须讲出来。
"""

from __future__ import annotations

import pytest

from app.narrative_core.cross_book.index import SearchItem
from app.narrative_core.cross_book.search import keyword_search, split_query
from app.narrative_core.cross_book.semantic import parse_and_verify


def _items() -> list[SearchItem]:
    return [
        SearchItem(1, "甲书", "technique", "用一句反常识的话立住人物",
                   "让角色说一句与预期相反的话",
                   "用一句反常识的话立住人物 让角色说一句与预期相反的话 打破刻板印象 可迁移到悬疑职场"),
        SearchItem(1, "甲书", "moment", "他在报名表上写我妈逼的", "打破严肃场合",
                   "他在报名表上写我妈逼的 我妈逼的 打破严肃场合", chapter=5),
        SearchItem(2, "乙书", "hook", "他真的会回来吗？", "", "他真的会回来吗？", chapter=12),
        SearchItem(2, "乙书", "evidence", "反转来得猝不及防", "", "反转来得猝不及防", chapter=88),
    ]


def test_a_craft_item_outranks_a_raw_quote() -> None:
    """搜「反常识」的人多半在找手法，不是在找某一章的原文。

    写法层排前面不是偏见，是这个功能被用来做什么决定的。
    """
    result = keyword_search(_items(), "打破")
    kinds = [h["kind"] for h in result["hits"]]
    assert kinds[0] in ("technique", "moment")


def test_a_title_hit_outranks_a_body_hit() -> None:
    result = keyword_search(_items(), "反常识")
    assert result["hits"][0]["title"] == "用一句反常识的话立住人物"


def test_truncation_is_stated_not_silent() -> None:
    """一份悄悄截到 N 条的结果，读起来和「一共就这么多」完全一样。

    而这两件事该做的下一步正好相反：一个是换个词再搜，一个是接着往下翻。
    """
    result = keyword_search(_items(), "打破", limit=1)
    assert result["truncated"] is True
    assert result["total"] > len(result["hits"])


def test_the_snippet_centres_on_the_match() -> None:
    """从头截一段是最没用的截法——命中往往在中间。"""
    long_item = SearchItem(
        1, "甲书", "evidence", "很长的一段",
        "", "前面全是无关的铺垫内容" * 12 + "这里才是命中的词",
    )
    result = keyword_search([long_item], "命中的词")
    assert "命中的词" in result["hits"][0]["snippet"]


def test_an_empty_query_asks_instead_of_returning_everything() -> None:
    """空查询返回全部条目，等于把一万两千条倒在用户脸上。"""
    result = keyword_search(_items(), "   ")
    assert result["hits"] == []
    assert result["message"]


def test_chinese_is_matched_whole_not_split_into_characters() -> None:
    """「反转」不该被切成「反」和「转」。

    切了之后，任何含「反」字的句子都会命中——噪音淹掉真正的结果。
    """
    assert split_query("反转 hook_2") == ["反转", "hook_2"]
    result = keyword_search(_items(), "反转")
    assert all("反转" in h["title"] or "反转" in h["snippet"] for h in result["hits"])


def test_kind_filter_narrows_the_search() -> None:
    result = keyword_search(_items(), "打破", kinds=["technique"])
    assert {h["kind"] for h in result["hits"]} == {"technique"}


# ---------- 按意思找：编号核对 ----------


def test_an_out_of_range_number_is_dropped() -> None:
    """模型给了一个不存在的编号。

    放过去的话，界面会显示一条来路不明的结果——而它看起来和真的一模一样。
    """
    result = parse_and_verify({"matches": [{"n": 999, "why": "x"}]}, _items())
    assert result["matches"] == []
    assert result["dropped"]


def test_the_same_number_twice_is_one_result() -> None:
    """同一条给两次不是两个结果——界面上会出现两张一模一样的卡片。"""
    result = parse_and_verify(
        {"matches": [{"n": 1, "why": "a"}, {"n": 1, "why": "b"}]}, _items()
    )
    assert len(result["matches"]) == 1


def test_a_verified_match_carries_the_book_it_came_from() -> None:
    result = parse_and_verify({"matches": [{"n": 1, "why": "正合适"}]}, _items())
    hit = result["matches"][0]
    assert hit["book_title"] == "甲书"
    assert hit["title"] == "用一句反常识的话立住人物"
    assert hit["why"] == "正合适"


def test_the_model_order_is_kept() -> None:
    """模型按符合程度排的序要保留——重排一遍等于把它的判断丢掉。"""
    result = parse_and_verify(
        {"matches": [{"n": 3, "why": "b"}, {"n": 1, "why": "a"}]}, _items()
    )
    assert [m["title"] for m in result["matches"]] == ["他真的会回来吗？", "用一句反常识的话立住人物"]


def test_unreadable_output_says_so() -> None:
    assert parse_and_verify("不是 JSON", _items())["parse_failed"] is True


@pytest.mark.parametrize("payload", [None, {}, [], {"matches": None}])
def test_malformed_payloads_do_not_crash(payload) -> None:
    assert isinstance(parse_and_verify(payload, _items())["matches"], list)


def test_a_chapter_of_zero_is_not_reported_as_chapter_zero() -> None:
    """界面会把 0 显示成「第 0 章」，那是一个不存在的位置。"""
    from app.narrative_core.cross_book.index import _chapter_of

    assert _chapter_of(0) is None
    assert _chapter_of("") is None
    assert _chapter_of(7) == 7
