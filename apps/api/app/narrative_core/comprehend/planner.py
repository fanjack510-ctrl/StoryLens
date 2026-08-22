"""把一本书的大纲规划成若干次模型调用。

「读懂」这条读法的分析单元是**节**，不是「块」。这跟小说那条线的根本区别在于：小说的结构要
花 163 次调用去猜，专著的结构是白给的，模型只需要填内容。所以这里没有窗口规划、没有连续性
链、也没有起承转合——只有「哪些节合成一次调用」。

三件事要同时成立：

**一节都不能漏。** 知识类书漏一节，读者不会知道自己漏了什么——他拿摘要替代原文。所以规划的
第一不变量是：每个节恰好出现在一个单元里，不多不少。这条有测试盯着。

**别为一个标题花一次调用。** `2 VISUALIZATION OBJECTIVES` 这种节只有两三个词——它是父标题，
内容在子节里。为它单独发一次请求，是花钱买一句废话。

**别把一次调用撑爆。** 输出预算有限，输入太长会让模型顾此失彼。超长的节要切开，而切开这件
事必须让读者看得见，否则他会以为那一节就这么点内容。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.document_outline import BookOutline, OutlineNode

__all__ = ["DigestUnit", "plan_units", "MIN_UNIT_WORDS", "MAX_UNIT_WORDS", "STUB_WORDS"]

#: 少于这么多词的节，是「只有标题」的父节，并进后面第一个有内容的节。
STUB_WORDS = 40
#: 一次调用最多读这么多词。手册里最长的一节是 3276 词，单次读完没问题；再长就切。
MAX_UNIT_WORDS = 3500
#: 相邻的小节合并到这个规模再发，省调用次数。
MIN_UNIT_WORDS = 1200


@dataclass
class DigestUnit:
    """一次模型调用要读的东西。"""

    sections: list[OutlineNode] = field(default_factory=list)
    #: 这些节在大纲里的下标。覆盖率必须按下标比对：按 (编号, 标题) 去重会把四章里各自的
    #: 「1 INTRODUCTION」当成同一个，从而把真正的遗漏藏起来。
    source_indexes: list[int] = field(default_factory=list)
    #: 超长节被切开时，这里是第几片 / 共几片。读者要能看出这一节被切过。
    part: int = 1
    part_count: int = 1

    @property
    def word_count(self) -> int:
        return sum(s.word_count for s in self.sections)

    @property
    def label(self) -> str:
        if not self.sections:
            return ""
        first, last = self.sections[0], self.sections[-1]
        span = first.display_title if first is last else f"{first.display_title} … {last.display_title}"
        return span if self.part_count == 1 else f"{span}（{self.part}/{self.part_count}）"


def _split_oversize(node: OutlineNode, index: int) -> list[DigestUnit]:
    """把超长的一节切成几片，按段落边界切，不切断句子。"""
    units: list[DigestUnit] = []
    bucket: list[str] = []
    size = 0
    for para in node.paragraphs:
        words = len(para.split())
        if bucket and size + words > MAX_UNIT_WORDS:
            units.append(DigestUnit(
                sections=[OutlineNode(node.level, node.number, node.title, list(bucket), node.chapter)],
                source_indexes=[index],
            ))
            bucket, size = [], 0
        bucket.append(para)
        size += words
    if bucket:
        units.append(DigestUnit(
            sections=[OutlineNode(node.level, node.number, node.title, list(bucket), node.chapter)],
            source_indexes=[index],
        ))
    for i, unit in enumerate(units, start=1):
        unit.part, unit.part_count = i, len(units)
    return units


def plan_units(outline: BookOutline) -> list[DigestUnit]:
    """规划调用。返回的单元覆盖大纲里的每一个节，恰好一次。"""
    nodes = [n for n in outline.nodes]
    if not nodes:
        return []

    units: list[DigestUnit] = []
    pending: list[OutlineNode] = []      # 攒着的小节 + 只有标题的父节
    pending_idx: list[int] = []
    pending_words = 0

    def flush() -> None:
        nonlocal pending, pending_idx, pending_words
        if pending:
            units.append(DigestUnit(sections=pending, source_indexes=pending_idx))
            pending, pending_idx, pending_words = [], [], 0

    for index, node in enumerate(nodes):
        words = node.word_count

        if words > MAX_UNIT_WORDS:
            # 超长节自己成片。前面攒着的先发出去，免得顺序乱掉——读者是按目录顺序读的。
            flush()
            units.extend(_split_oversize(node, index))
            continue

        if words <= STUB_WORDS:
            # 只有标题的父节：不单独发，跟着后面的内容走。它仍然出现在某个单元里，
            # 所以不会从覆盖率里消失。
            pending.append(node)
            pending_idx.append(index)
            pending_words += words
            continue

        pending.append(node)
        pending_idx.append(index)
        pending_words += words
        if pending_words >= MIN_UNIT_WORDS:
            flush()

    flush()
    return units


def coverage_of(outline: BookOutline, units: list[DigestUnit]) -> tuple[int, int]:
    """(被覆盖的节数, 大纲里的节数)。两者不等，就意味着有内容会静默消失。"""
    covered = {i for u in units for i in u.source_indexes}
    return len(covered), len(outline.nodes)
