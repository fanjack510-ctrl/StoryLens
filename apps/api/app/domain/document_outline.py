"""一本书的大纲：章 → 节 → 小节，以及每一节的正文。

这是「读懂」这条读法的分析单元。它有意做成一个**中间形态**，因为不同格式给出结构的方式差别
极大：

    Word / Markdown / LaTeX / HTML / EPUB    标题层级明写在文件里，直接读
    PDF                                      没有层级，只能从章首目录和正文标题里认
    TXT                                      什么都没有，只能靠编号习惯猜

以前的流水线把所有格式先拍平成一个大字符串，再用小说的「第 N 章」正则去切——于是前四种格式
里现成的结构被扔掉了，再花力气从纯文本里猜回来，还猜不准。这里反过来：**能直接读到结构的就
别猜**，只有 PDF 和 TXT 才走推断。

中英文都要认。中文书的编号习惯和英文完全不同（`第三章` / `一、` / `（二）` / `§2`），而且
中文专著常常**没有**英文手册那种「章首自带带页码的小节目录」——所以推断这一支不能只会认
`3.1 Title` 这一种形态。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["OutlineNode", "BookOutline", "detect_headings", "outline_from_headings"]


@dataclass
class OutlineNode:
    """一节。level 1 是章，2 是节，3 及以下是小节。"""

    level: int
    number: str
    title: str
    paragraphs: list[str] = field(default_factory=list)
    #: 这一节属于哪一章。四章里各有一个「1 INTRODUCTION」，不记章号就分不出是哪一个——
    #: 而分不出，覆盖率检查就会把四个节当成一个，把真正的遗漏藏起来。
    chapter: str = ""

    @property
    def word_count(self) -> int:
        # 中文按字数、西文按词数——两者混在一本书里也各算各的。
        total = 0
        for p in self.paragraphs:
            han = len(re.findall(r"[一-鿿]", p))
            western = len(re.findall(r"[A-Za-z][A-Za-z'\-]*", p))
            total += han + western
        return total

    @property
    def display_title(self) -> str:
        head = f"{self.chapter} " if self.chapter else ""
        return f"{head}{self.number} {self.title}".strip()


@dataclass
class BookOutline:
    nodes: list[OutlineNode] = field(default_factory=list)
    #: 结构是读来的还是猜的。读来的可信，猜的要在界面上说清楚。
    source: str = "inferred"
    rules: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(n.word_count for n in self.nodes)

    @property
    def empty_nodes(self) -> list[OutlineNode]:
        """有标题却没正文的节。它们是「内容会静默消失」的唯一入口，必须能被数出来。"""
        return [n for n in self.nodes if not n.paragraphs]


#: 中文数字，够用到「第一百二十章」
_CN_NUM = "零一二三四五六七八九十百千两"

#: 一行是不是标题，以及它是第几级。顺序有意义：先匹配到的优先。
_HEADING_PATTERNS: tuple[tuple[re.Pattern[str], int, str], ...] = (
    # 第三章 / 第 3 章 / 第三编 / 第三部分
    (re.compile(rf"^\s*第\s*([0-9{_CN_NUM}]+)\s*[章篇编部]\s*[、.：: ]?\s*(.*)$"), 1, "cn-chapter"),
    (re.compile(rf"^\s*第\s*([0-9{_CN_NUM}]+)\s*节\s*[、.：: ]?\s*(.*)$"), 2, "cn-section"),
    # Chapter 3 / CHAPTER 3 / Part II
    (re.compile(r"^\s*(?:CHAPTER|Chapter)\s+([0-9IVXLC]+)\s*[.:]?\s*(.*)$"), 1, "en-chapter"),
    (re.compile(r"^\s*(?:SECTION|Section)\s+([0-9.]+)\s*[.:]?\s*(.*)$"), 2, "en-section"),
    # 1.2.3 标题 —— 点号的个数就是层级
    (re.compile(r"^\s*(\d+(?:\.\d+){1,3})\.?\s+(\S.*)$"), 0, "numeric"),
    # 一、标题   （二）标题
    (re.compile(rf"^\s*([{_CN_NUM}]+)\s*、\s*(\S.*)$"), 2, "cn-enum"),
    (re.compile(rf"^\s*[（(]\s*([0-9{_CN_NUM}]+)\s*[)）]\s*(\S.*)$"), 3, "cn-paren"),
    # § 2  /  §2.1
    (re.compile(r"^\s*§\s*(\d+(?:\.\d+)*)\s*(.*)$"), 2, "section-sign"),
)

#: 标题不会太长。一段正文碰巧以「1.2 」开头的情况存在，长度是最便宜的分辨手段。
_MAX_HEADING_CHARS = 60


def _classify(line: str) -> tuple[int, str, str, str] | None:
    text = line.strip()
    if not text or len(text) > _MAX_HEADING_CHARS:
        return None
    for pattern, level, rule in _HEADING_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        number, title = m.group(1), (m.group(2) or "").strip()
        if rule == "numeric":
            level = min(4, number.count(".") + 1)
            # `1.2 的取值范围` 这种正文开头，标题部分会以中文助词起头 —— 但更可靠的信号是
            # 整行是否短，上面已经拦过了。这里只再挡一种：标题不以句末标点收尾。
            if title.endswith(("。", "！", "？", ".", "!", "?")):
                return None
        return level, number, title, rule
    return None


def detect_headings(lines: list[str]) -> list[tuple[int, int, str, str, str]]:
    """从纯文本里认标题，返回 (行号, 层级, 编号, 标题, 命中的规则)。

    只在没有现成结构时才用。规则命名一并返回，是为了让界面能说出「这本书的结构是怎么认出来
    的」——用户看到 76 节时，有权知道那是读来的还是猜的。
    """
    out: list[tuple[int, int, str, str, str]] = []
    for i, line in enumerate(lines):
        hit = _classify(line)
        if hit is not None:
            level, number, title, rule = hit
            out.append((i, level, number, title, rule))
    return out


def outline_from_headings(lines: list[str], *, source: str = "inferred") -> BookOutline:
    """把「文本行 + 认出来的标题」组装成大纲。

    标题之间的所有行都是那一节的正文；第一个标题之前的内容（封面、版权页、总目录）归入一个
    没有编号的前置节，而不是丢掉——丢掉的东西用户看不见，也就无从发现丢了。
    """
    outline = BookOutline(source=source)
    heads = detect_headings(lines)
    if not heads:
        body = [ln.strip() for ln in lines if ln.strip()]
        if body:
            outline.nodes.append(OutlineNode(level=1, number="", title="正文", paragraphs=body))
            outline.rules.append("未识别到任何标题，全书作为一节")
        return outline

    rules_used = sorted({h[4] for h in heads})
    outline.rules.append("标题识别规则：" + "、".join(rules_used))

    first = heads[0][0]
    if first > 0:
        front = [ln.strip() for ln in lines[:first] if ln.strip()]
        if front:
            outline.nodes.append(
                OutlineNode(level=1, number="", title="前置内容", paragraphs=front)
            )

    for idx, (line_no, level, number, title, _rule) in enumerate(heads):
        stop = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        body = [ln.strip() for ln in lines[line_no + 1: stop] if ln.strip()]
        outline.nodes.append(
            OutlineNode(level=level, number=number, title=title or "（无标题）", paragraphs=body)
        )
    return outline
