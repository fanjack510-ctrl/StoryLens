"""共性视图：把一组书摆在一起，看它们共同做对了什么。

这个功能最容易变成一段「看起来很有道理的废话」——「这些书都很会写钩子」既正确、又无用、
还无法证伪。防住它的不是把话说得更谨慎，是**结构上不允许**：每条共性都要列出引用的书和
那本书里的技法名原文，后端逐条核对，编造的丢掉。

所以这个文件里最重要的不是「能不能归纳出来」，是**编造的东西会不会被挡下**。
"""

from __future__ import annotations

import pytest

from app.narrative_core.common_patterns.aggregate import BookFacts, Technique, count_genres
from app.narrative_core.common_patterns.synthesize import MIN_SUPPORT, parse_and_verify


def _facts() -> list[BookFacts]:
    return [
        BookFacts(
            book_id=1,
            title="甲书",
            chapters_analysed=100,
            chapters_total=100,
            primary_genre="悬疑",
            techniques=[Technique("反常识开场", "a", "b", "c"), Technique("数字堆叠", "a", "b", "c")],
            hook_count=50,
        ),
        BookFacts(
            book_id=2,
            title="乙书",
            chapters_analysed=5,
            chapters_total=500,
            scope_kind="opening",
            primary_genre="悬疑",
            techniques=[Technique("粗俗细节破严肃", "a", "b", "c")],
            hook_count=2,
        ),
        BookFacts(
            book_id=3,
            title="丙书",
            excluded_reason="还没有分析过——先跑一次拆解",
        ),
    ]


def test_a_pattern_that_cites_a_book_outside_the_set_is_dropped() -> None:
    """模型引用了不在这组里的书号。

    这是最危险的一种编造：书名看着眼熟，结论读着通顺，而那本书根本不在用户选的这一组里。
    """
    result = parse_and_verify(
        {
            "patterns": [
                {
                    "name": "编的",
                    "instances": [
                        {"book_id": 999, "technique_name": "随便什么"},
                        {"book_id": 1, "technique_name": "反常识开场"},
                    ],
                }
            ]
        },
        _facts(),
    )
    assert result["patterns"] == []
    assert any("999" in d["reason"] for d in result["dropped"])


def test_a_pattern_that_invents_a_technique_name_is_dropped() -> None:
    """书号是真的，技法名是编的。

    比编书号更难发现——引用的书确实在这组里，只是那本书里根本没有这一招。
    """
    result = parse_and_verify(
        {
            "patterns": [
                {
                    "name": "编的",
                    "instances": [
                        {"book_id": 1, "technique_name": "这一招不存在"},
                        {"book_id": 2, "technique_name": "粗俗细节破严肃"},
                    ],
                }
            ]
        },
        _facts(),
    )
    assert result["patterns"] == []
    assert any("不存在" in d["reason"] for d in result["dropped"])


def test_one_book_cited_twice_is_still_one_book() -> None:
    """同一本书的两条技法，不构成「两本书都这么做」。

    这是最容易蒙混过去的一种：所有引用都是真的，只是全部来自同一本书——
    而「共性」这个词要求至少两本。
    """
    result = parse_and_verify(
        {
            "patterns": [
                {
                    "name": "只有一本",
                    "instances": [
                        {"book_id": 1, "technique_name": "反常识开场"},
                        {"book_id": 1, "technique_name": "数字堆叠"},
                    ],
                }
            ]
        },
        _facts(),
    )
    assert result["patterns"] == []
    assert any(str(MIN_SUPPORT) in d["reason"] for d in result["dropped"])


def test_a_real_pattern_survives_with_its_citations() -> None:
    result = parse_and_verify(
        {
            "patterns": [
                {
                    "name": "用认知冲突立人物",
                    "what_they_do": "让角色说一句与预期相反的话",
                    "why_it_works": "打破刻板印象",
                    "instances": [
                        {"book_id": 1, "technique_name": "反常识开场"},
                        {"book_id": 2, "technique_name": "粗俗细节破严肃"},
                    ],
                }
            ]
        },
        _facts(),
    )
    assert len(result["patterns"]) == 1
    kept = result["patterns"][0]
    assert kept["book_count"] == 2
    # 书名跟着引用一起给出去——只给 book_id 的话，界面得自己去查，而查错了没人会发现。
    assert {i["book_title"] for i in kept["instances"]} == {"甲书", "乙书"}


def test_the_model_renaming_the_keys_does_not_throw_the_answer_away() -> None:
    """实测模型会写成 `shared_techniques` / `technique_names`。

    键名改了不影响内容的真假。因为一个键名把一份好结果整个丢掉，用户看到的是
    「归纳失败」——那是误导，而且他会重跑一次，再付一次钱。
    """
    result = parse_and_verify(
        {
            "shared_techniques": [
                {
                    "what_they_do": "x",
                    "instances": [
                        {"book_id": 1, "technique_names": ["反常识开场", "数字堆叠"]},
                        {"book_id": 2, "technique_names": ["粗俗细节破严肃"]},
                    ],
                }
            ]
        },
        _facts(),
    )
    assert len(result["patterns"]) == 1
    assert result["patterns"][0]["book_count"] == 2


def test_patterns_are_ordered_by_how_many_books_back_them() -> None:
    """十本里有八本在用的招，比两本在用的更该先看见。"""
    facts = _facts()
    facts[2] = BookFacts(
        book_id=3, title="丙书", primary_genre="言情",
        techniques=[Technique("反常识开场", "a", "b", "c")],
        chapters_analysed=10, chapters_total=10,
    )
    result = parse_and_verify(
        {
            "patterns": [
                {"name": "两本", "instances": [
                    {"book_id": 1, "technique_name": "数字堆叠"},
                    {"book_id": 2, "technique_name": "粗俗细节破严肃"}]},
                {"name": "三本", "instances": [
                    {"book_id": 1, "technique_name": "反常识开场"},
                    {"book_id": 2, "technique_name": "粗俗细节破严肃"},
                    {"book_id": 3, "technique_name": "反常识开场"}]},
            ]
        },
        facts,
    )
    assert [p["name"] for p in result["patterns"]] == ["三本", "两本"]


def test_unreadable_output_says_so_instead_of_returning_nothing() -> None:
    """解析不了要说解析不了。

    静默返回「零条共性」会被读成「这些书没有共同点」——那是一个完全不同的、
    而且是错的结论。
    """
    result = parse_and_verify("这不是 JSON", _facts())
    assert result["parse_failed"] is True


def test_hooks_are_reported_per_chapter_not_as_a_raw_count() -> None:
    """1245 个钩子听起来很多，但那本书有 1299 章。

    原始计数在书长差异面前没有可比性，而共性视图整件事就是把不同的书放在一起比。
    """
    facts = _facts()
    assert facts[0].hooks_per_chapter == 0.5  # 50 / 100
    assert facts[1].hooks_per_chapter == 0.4  # 2 / 5
    assert BookFacts(book_id=9, title="没读过").hooks_per_chapter is None


def test_a_book_that_cannot_join_says_why() -> None:
    """从比较里消失而不说明原因，用户会以为自己选错了书。

    真正的原因通常是「这本还没拆过文」——那是一句他能直接照做的话。
    """
    facts = _facts()
    excluded = [f for f in facts if not f.usable]
    assert len(excluded) == 1
    assert "拆" in excluded[0].excluded_reason


def test_genre_counts_ignore_books_that_cannot_join() -> None:
    assert count_genres(_facts()) == [("悬疑", 2)]


@pytest.mark.parametrize("payload", [None, {}, [], "", {"patterns": None}])
def test_empty_or_malformed_payloads_do_not_crash(payload) -> None:
    result = parse_and_verify(payload, _facts())
    assert isinstance(result["patterns"], list)
