"""专著与工具书的结构识别：把一本书拆成「章 → 节」，一次模型都不调。

小说那条线最贵的一步是「读完再猜结构」——起承转合是 163 个块烧出来的。这类书不用猜：章首
自带一份带页码的小节目录，正文里每一节又以同样的编号起头。两边一对，结构就出来了。

难的不是找标题，是**这类 PDF 里空格不可信**。同一个标题会以三种面貌出现：

    Usability T esting          单个字母被字距拆出来
    5I N T E R A C T I O N      整词拉开，编号还粘在第一个字母上
    Datavisualizationisabout    反过来：词间空格丢光

为每一种写一条规则，补一个漏一个（实测卡在 76/79）。这里只用一条：**匹配时把空白整个抹掉，
另存一张「无空白位置 → 原文位置」的映射表**。三种面貌抹完都长一个样。

页眉页脚同理。第一版我按某家排版厂的 `Trim Size: … Page NNN` 硬匹配——换一本书就废。这里改
成让重复自己暴露：**在大多数页面上都出现的首尾行，就是版面家具**，跟它长什么样无关。

定位不到的节不会消失，而是退回按目录页码近似，并标出来。一份缺了节的摘要，读者不会知道自己
漏了什么——对知识类书来说，覆盖率是及格线，不是加分项。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal, Sequence

__all__ = [
    "MonographSection",
    "MonographDetection",
    "detect_monograph",
    "strip_page_furniture",
    "squeeze",
]

#: 章首那行：CHAPTER 35 / 第 35 章 / Chapter 35
_CHAPTER = re.compile(r"^\s*(?:CHAPTER|Chapter)\s+(\d+)\s*$|^\s*第\s*([0-9一二三四五六七八九十百]+)\s*章\s*$", re.M)
#: 章首目录行：`2.1 Audience and Purpose 896`
_TOC_ENTRY = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(\S[^\n]*?)\s+(\d{1,4})\s*$", re.M)
#: 一行里只有数字 —— 页码的样子
_LONE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")

#: 一行在多少比例的页面上出现，才算版面家具
_FURNITURE_RATIO = 0.5
#: 每页头尾各看几行
_FURNITURE_EDGE = 3


def squeeze(text: str) -> tuple[str, list[int]]:
    """去掉全部空白，并返回「新位置 → 原位置」的映射。

    这是整个模块唯一处理空格的方式。不是省事：这类 PDF 的空格由字距渲染而来，既会凭空多出
    来，也会整片丢掉，**它根本不承载分词信息**。既然不可信，就不依赖它。
    """
    kept: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if not ch.isspace():
            kept.append(ch)
            index.append(i)
    return "".join(kept), index


def _edge_width(line_count: int) -> int:
    """一页的头尾各看几行才算「边缘」。

    写死 3 行，在只有四五行的页面上会把整页都算成边缘——而数字被归一成 # 之后，
    `真正的内容 1` 和 `真正的内容 2` 看起来一模一样，于是正文被当成页眉删掉。
    页眉页脚在版面上永远只占一小截，所以边缘宽度得跟着页面长度走。
    """
    return max(1, min(_FURNITURE_EDGE, line_count // 3))


def _normalise_furniture(line: str) -> str:
    """把行里的数字抹成 #，好让「895 页」和「896 页」认出是同一条页眉。"""
    return re.sub(r"\d+", "#", line.strip())


def strip_page_furniture(pages: Sequence[str]) -> list[str]:
    """去掉页眉页脚，靠的是「它在很多页上重复」，不是「它长什么样」。

    硬编码某一家排版厂的标记（`Trim Size: … Page NNN`）只对那一本书有效。重复性是所有书共有
    的性质：正文不会一模一样地出现在半数页面的同一位置上，页眉会。
    """
    if len(pages) < 4:
        return list(pages)
    seen: Counter[str] = Counter()
    for page in pages:
        lines = [ln for ln in page.splitlines() if ln.strip()]
        k = _edge_width(len(lines))
        edge = lines[:k] + lines[-k:]
        for ln in set(_normalise_furniture(x) for x in edge):
            if len(ln) >= 4:
                seen[ln] += 1
    threshold = max(3, int(len(pages) * _FURNITURE_RATIO))
    furniture = {ln for ln, n in seen.items() if n >= threshold}
    if not furniture:
        return list(pages)

    cleaned: list[str] = []
    for page in pages:
        out = []
        lines = page.splitlines()
        k = _edge_width(len([x for x in lines if x.strip()]))
        for i, ln in enumerate(lines):
            near_edge = i < k or i >= len(lines) - k
            if near_edge and _normalise_furniture(ln) in furniture:
                continue
            out.append(ln)
        cleaned.append("\n".join(out))
    return cleaned


def book_page_numbers(pages: Sequence[str]) -> dict[int, int]:
    """书内页码 → 该页在文件里的序号。

    只认「首尾行只有一个数字」且整体递增的那一列，所以图注里的数字不会冒充页码。递增是关键：
    单看一页分不出页码和别的数字，看整本就分得出。
    """
    found: list[tuple[int, int]] = []
    for i, page in enumerate(pages):
        lines = [ln for ln in page.splitlines() if ln.strip()]
        if not lines:
            continue
        for cand in (lines[0], lines[-1]):
            if _LONE_NUMBER.match(cand):
                found.append((i, int(cand.strip())))
                break
    if len(found) < max(3, len(pages) // 3):
        return {}
    # 只保留单调递增的那条主链，剔除偶然的孤立数字
    chain: list[tuple[int, int]] = []
    for item in found:
        if not chain or item[1] > chain[-1][1]:
            chain.append(item)
    if len(chain) < max(3, len(pages) // 3):
        return {}
    mapping: dict[int, int] = {}
    for pdf_i, book_p in chain:
        mapping.setdefault(book_p, pdf_i)
    return mapping


@dataclass(frozen=True)
class MonographSection:
    """一节。它是这条读法真正的分析单元——不是「块」，也不是「章」。"""

    number: str
    title: str
    chapter_no: int | None
    chapter_title: str
    book_page: int | None
    paragraphs: list[str]
    located: Literal["exact", "approximate"]

    @property
    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)

    @property
    def display_title(self) -> str:
        head = f"第{self.chapter_no}章 " if self.chapter_no is not None else ""
        return f"{head}{self.number} {self.title}".strip()


@dataclass
class MonographDetection:
    sections: list[MonographSection] = field(default_factory=list)
    chapter_titles: dict[int, str] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    #: 章首目录里列出、但正文里没能定位的节。**必须留下来**：静默丢掉，覆盖率会拿
    #: 「找到的」当分母，把一份残缺的摘要报成 100%，而读者正是拿它替代原文的。
    missing: list[str] = field(default_factory=list)

    @property
    def exact_count(self) -> int:
        return sum(1 for s in self.sections if s.located == "exact")

    @property
    def coverage(self) -> float:
        """有多少节最终拿到了正文。低于 1.0 就意味着有内容会从摘要里静默消失。"""
        return 1.0 if not self.sections else sum(
            1 for s in self.sections if s.paragraphs
        ) / len(self.sections)


def _paragraphs_of(text: str) -> list[str]:
    body = re.sub(r"\s+", " ", text).strip()
    if not body:
        return []
    # 学术正文在 PDF 里没有可靠的段落边界（换行是排版换行），所以按句子聚成中等长度的块，
    # 而不是假装能还原原书的分段。
    parts = re.split(r"(?<=[.!?。！？])\s+", body)
    out: list[str] = []
    buf = ""
    for p in parts:
        buf = f"{buf} {p}".strip()
        if len(buf) >= 400:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out



def _ascending(cands: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """从候选目录项里挑出最长的一条递增编号链。

    这里原本是一句 `if int(num) > 99: continue`——用一个数值上限挡页眉混进来的假编号。
    实测下来它挡错了东西：一章 500 节的书，第 100 节起全被丢掉，而且**丢得无声无息**，
    覆盖率照样报 100%。上限是错的抽象：目录的特征不是「编号小」，是「编号递增」。

    所以按序挑，而不是按大小挑。孤立的噪声项（页眉里的年份、页码）不合这条链，自然落选；
    一章有多少节，则完全不设限。
    """
    if not cands:
        return []
    keys = [tuple(int(x) for x in c[0].split(".")) for c in cands]
    best = [1] * len(keys)
    prev = [-1] * len(keys)
    for i in range(len(keys)):
        for j in range(i):
            if keys[j] < keys[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    end = max(range(len(keys)), key=lambda i: best[i])
    chain: list[int] = []
    while end != -1:
        chain.append(end)
        end = prev[end]
    return [cands[i] for i in reversed(chain)]


def detect_monograph(pages: Sequence[str]) -> MonographDetection:
    """把 PDF 的逐页文本，识别成「章 → 节」。"""
    det = MonographDetection()
    clean = strip_page_furniture(pages)
    det.rules.append(f"页眉页脚：按重复率剔除（阈值 {_FURNITURE_RATIO:.0%}）")
    page_map = book_page_numbers(pages)
    if page_map:
        det.rules.append(f"书内页码：识别到 {len(page_map)} 页")

    chapters: list[tuple[int, int, str]] = []       # (pdf_index, chapter_no, title)
    for i, text in enumerate(clean):
        m = _CHAPTER.search(text)
        if not m:
            continue
        no = int(m.group(1)) if m.group(1) else None
        after = [x.strip() for x in text[m.end():].strip().splitlines() if x.strip()]
        chapters.append((i, no or (len(chapters) + 1), after[0] if after else ""))
    if not chapters:
        det.rules.append("未找到章首标记，全书作为一章处理")
        chapters = [(0, 1, "")]

    for ci, (start, no, ch_title) in enumerate(chapters):
        stop = chapters[ci + 1][0] if ci + 1 < len(chapters) else len(clean)
        det.chapter_titles[no] = ch_title

        # 目录窗口按证据长，不按固定页数。原本写死「章首 2 页」，那是照着手边这本手册的
        # 版面定的；一章的目录排到第 3 页，第 3 页起的节就连「漏了」都报不出来——它们
        # 根本没被看见，连 missing 都进不去。所以：只要下一页还在往下续目录，就接着看。
        cands: list[tuple[str, str, int]] = []
        seen: set[str] = set()
        toc_last = start
        for page_i in range(start, stop):
            before = len(cands)
            for m in _TOC_ENTRY.finditer(clean[page_i]):
                num, title, page = m.group(1), re.sub(r"\s{2,}", " ", m.group(2).strip()), int(m.group(3))
                if num in seen:
                    continue
                seen.add(num)
                cands.append((num, title, page))
            # 正文页只会零星撞上一两行「像目录」的行；连续两条以上才算目录还在往下排。
            if page_i > start and len(cands) - before < 2:
                break
            toc_last = page_i
        if toc_last > start:
            det.rules.append(f"第{no}章目录跨 {toc_last - start + 1} 页")
        entries = _ascending(cands)

        # 章首页要留下：目录之下就是正文开头，整页跳过会让每章的第 1 节永远找不到
        first = clean[start]
        cut = None
        for m in _TOC_ENTRY.finditer(first):
            cut = m.end()
        body = " ".join([first[cut:] if cut else first] + list(clean[start + 1: stop]))
        flat, index = squeeze(body)

        marks: list[tuple[int, str, str, int, str]] = []
        for num, title, page in entries:
            key = squeeze(f"{num} {title}")[0][:28]
            at = flat.find(key)
            if at != -1:
                marks.append((index[at], num, title, page, "exact"))
                continue
            pdf_i = page_map.get(page)
            if pdf_i is not None and start <= pdf_i < stop:
                before = " ".join([first[cut:] if cut else first] + list(clean[start + 1: pdf_i]))
                marks.append((len(before), num, title, page, "approximate"))

        found = {num for _, num, _, _, _ in marks}
        for num, title, _page in entries:
            if num not in found:
                det.missing.append(f"第{no}章 {num} {title}")

        marks.sort(key=lambda x: x[0])
        for mi, (at, num, title, page, how) in enumerate(marks):
            end = marks[mi + 1][0] if mi + 1 < len(marks) else len(body)
            det.sections.append(
                MonographSection(
                    number=num,
                    title=title,
                    chapter_no=no,
                    chapter_title=ch_title,
                    book_page=page,
                    paragraphs=_paragraphs_of(body[at:end]),
                    located=how,  # type: ignore[arg-type]
                )
            )
    det.rules.append(f"小节 {len(det.sections)} 个，精确定位 {det.exact_count} 个")
    if det.missing:
        det.rules.append(f"目录列出但正文未定位 {len(det.missing)} 节")
    return det
