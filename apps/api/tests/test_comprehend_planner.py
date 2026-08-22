"""「读懂」的调用规划。

这条读法的价值前提是「读者不读原文也知道书里说了什么」。前提能不能立住，第一关就是这里：
**规划漏掉一节，那一节的内容就永远不会进入摘要，而读者不会知道自己漏了什么。**

所以这组测试盯的是覆盖和边界，不是好路径。
"""

from __future__ import annotations

from app.domain.document_outline import BookOutline, OutlineNode
from app.narrative_core.comprehend.planner import (
    MAX_UNIT_WORDS,
    STUB_WORDS,
    DigestUnit,
    coverage_of,
    plan_units,
)


def _node(number: str, title: str, words: int, level: int = 2) -> OutlineNode:
    # 用英文词造正文，方便按词数控制规模
    para = " ".join(["word"] * 200)
    full, rest = divmod(words, 200)
    paras = [para] * full + ([" ".join(["word"] * rest)] if rest else [])
    return OutlineNode(level=level, number=number, title=title, paragraphs=paras)


def _outline(*nodes: OutlineNode) -> BookOutline:
    return BookOutline(nodes=list(nodes), source="inferred")


def test_every_section_lands_in_exactly_one_unit() -> None:
    """第一不变量。漏一节 = 读者永远看不到那部分内容，而且他不会发现。"""
    outline = _outline(
        _node("1", "Intro", 500),
        _node("2", "Parent", 3),
        _node("2.1", "Child", 900),
        _node("3", "Long", 5000),
        _node("4", "Tail", 100),
    )
    units = plan_units(outline)
    covered, total = coverage_of(outline, units)
    assert covered == total == 5


def test_a_heading_only_section_does_not_buy_its_own_call() -> None:
    """`2 VISUALIZATION OBJECTIVES` 只有两三个词——它是父标题，内容在子节里。

    为它单独发一次请求，是花钱买一句废话；但它也不能消失，否则目录就对不上了。
    """
    outline = _outline(_node("2", "Parent", 3), _node("2.1", "Child", 900))
    units = plan_units(outline)
    assert len(units) == 1
    assert [s.number for s in units[0].sections] == ["2", "2.1"]


def test_an_oversize_section_is_split_and_says_so() -> None:
    """切开这件事必须让读者看得见，否则他会以为那一节就这么点内容。"""
    outline = _outline(_node("3", "Long", MAX_UNIT_WORDS * 2 + 400))
    units = plan_units(outline)
    assert len(units) > 1
    assert all(u.part_count == len(units) for u in units)
    assert "1/" in units[0].label
    assert all(u.word_count <= MAX_UNIT_WORDS for u in units)


def test_reading_order_survives_an_oversize_section() -> None:
    """读者按目录顺序读。超长节插队会让摘要的顺序和书对不上。"""
    outline = _outline(
        _node("1", "First", 300),
        _node("2", "Huge", MAX_UNIT_WORDS + 800),
        _node("3", "Third", 300),
    )
    order = [s.number for u in plan_units(outline) for s in u.sections]
    assert order == ["1", "2", "2", "3"] or order == ["1", "2", "3"]
    assert order.index("1") < order.index("3")


def test_small_sections_are_batched_instead_of_one_call_each() -> None:
    """76 节里一多半不到 400 词。一节一次调用，是把钱花在往返上而不是内容上。"""
    outline = _outline(*[_node(f"1.{i}", f"S{i}", 200) for i in range(1, 13)])
    units = plan_units(outline)
    assert len(units) < 12
    covered, total = coverage_of(outline, units)
    assert covered == total


def test_an_empty_outline_plans_nothing_rather_than_crashing() -> None:
    assert plan_units(_outline()) == []


def test_a_section_with_no_body_still_gets_carried() -> None:
    """有标题没正文的节是「内容静默消失」的唯一入口，必须留在规划里被看见。"""
    empty = OutlineNode(level=2, number="6.4", title="Scientific Visualization", paragraphs=[])
    outline = _outline(empty, _node("6.5", "Next", 800))
    units = plan_units(outline)
    covered, total = coverage_of(outline, units)
    assert covered == total == 2
