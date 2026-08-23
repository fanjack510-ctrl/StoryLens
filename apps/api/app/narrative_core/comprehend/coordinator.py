"""「读懂」的执行：逐节 → 章级上卷 → 全书上卷。

模型调用以可调用对象注入，跟小说那条线的 RunCoordinator 同一个路子——测试因此不需要 provider，
也就能盯住那些真正要紧的边界（失败留痕、覆盖率、并发不改结果）。

**并发。** 节与节之间没有连续性依赖——这正是这条读法比小说简单的地方：小说的块必须按顺序读，
因为每块要带着上一块的连续性状态；这里每一节都是独立的。所以可以直接并发，不需要分区那套。

**失败必须留痕。** 一次调用失败就静默跳过，等于让那几节的内容从报告里消失，而读者不会知道。
所以失败的单元照样进结果，带着错误原因，并把覆盖率拉下来。低于九成，整份报告标为不可信——
读者据此决定要不要回去读原文。
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from app.domain.document_outline import BookOutline
from app.narrative_core.comprehend.contracts import (
    BookDigest,
    ChapterDigest,
    ComprehendResult,
    SectionDigest,
)
from app.narrative_core.comprehend.planner import DigestUnit, coverage_of, plan_units
from app.narrative_core.comprehend.prompts import (
    build_book_prompt,
    build_chapter_prompt,
    build_section_prompt,
)

__all__ = ["ComprehendCoordinator", "parse_sections"]

#: 模型答案里的分段标记。用 `## ` 而不是 JSON：这类长文本任务上，结构化输出的失败率明显更高，
#: 而这里的结构简单到用标题就能切干净。
_HEAD = re.compile(r"^##\s*(.+?)\s*$", re.M)

_EMPTY_ANSWERS = {
    "本节未提出主张", "本节未给出依据", "本节未给操作", "无", "原文未明确",
}


def parse_sections(text: str) -> dict[str, list[str]]:
    """把 `## 小标题` 分段的回答切成 {小标题: [条目]}。

    模型偶尔会多写一层项目符号或编号，这里一并剥掉——留着它们，导出的报告里就会出现
    「· 1. · 分类数据……」这种叠了三层的行。
    """
    out: dict[str, list[str]] = {}
    marks = list(_HEAD.finditer(text or ""))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        items: list[str] = []
        for raw in body.splitlines():
            line = raw.strip()
            # 项目符号后面必须跟空白才算项目符号。不要这个条件，`**该读**：…` 会被吃掉
            # 一个星号变成 `*该读**：…` —— 报告里就多出一个孤零零的星号。
            line = re.sub(r"^[·•\-*]\s+", "", line)
            line = re.sub(r"^\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"^\d+[.、)]\s*", "", line)
            if line:
                items.append(line)
        out[m.group(1).strip()] = items
    return out


def _pick(parsed: dict[str, list[str]], *names: str) -> list[str]:
    for name in names:
        for key, value in parsed.items():
            if name in key:
                return [v for v in value if v not in _EMPTY_ANSWERS]
    return []


class ComprehendCoordinator:
    def __init__(
        self,
        *,
        ask: Callable[[str], str],
        concurrency: int = 4,
        on_call: Callable[[int, int], None] | None = None,
    ) -> None:
        self._ask = ask
        self._concurrency = max(1, int(concurrency))
        self._on_call = on_call
        self._lock = threading.Lock()
        self._calls = 0

    # ------------------------------------------------------------------ 逐节

    def _digest_unit(self, unit: DigestUnit, book_title: str, total: int) -> SectionDigest:
        out = SectionDigest(
            label=unit.label,
            section_numbers=[s.display_title for s in unit.sections],
            book_pages=[],
            part=unit.part,
            part_count=unit.part_count,
        )
        try:
            answer = self._ask(build_section_prompt(unit, book_title=book_title))
        except Exception as exc:  # noqa: BLE001 — 失败要留痕，不能让内容静默消失
            out.error = f"{type(exc).__name__}: {exc}"[:200]
            return out
        finally:
            with self._lock:
                self._calls += 1
                done = self._calls
            if self._on_call is not None:
                try:
                    self._on_call(done, total)
                except Exception:  # noqa: BLE001 — 报进度不该拖垮分析
                    pass

        parsed = parse_sections(answer)
        out.claims = _pick(parsed, "主张")
        out.evidence = _pick(parsed, "依据")
        out.actions = _pick(parsed, "做法", "怎么用")
        out.terms = _pick(parsed, "术语")
        out.open_questions = _pick(parsed, "存疑", "没回答")
        if not out.claims and not out.error:
            # 拿回了东西但一条主张也没有：这跟成功不是一回事，不能算进覆盖率。
            out.error = "模型未按格式给出主张"
        return out

    # ------------------------------------------------------------------ 全流程

    def run(self, outline: BookOutline, *, book_title: str) -> ComprehendResult:
        result = ComprehendResult(rules=list(outline.rules))
        units = plan_units(outline)
        covered, total = coverage_of(outline, units)
        result.sections_total = total
        # 目录列了、正文没定位到的节，跟「读失败的节」是同一类事：读者都没拿到内容。
        # 放进同一张清单里，他才会在报告上看见它们。
        for label in outline.missing:
            result.failures.append(f"{label}：目录里有这一节，正文里没能定位到")
        if not units:
            result.book.error = "这本书没有识别出任何内容"
            return result

        if self._concurrency <= 1 or len(units) == 1:
            digests = [self._digest_unit(u, book_title, len(units)) for u in units]
        else:
            with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
                digests = list(
                    pool.map(lambda u: self._digest_unit(u, book_title, len(units)), units)
                )

        # 覆盖率按「内容真的进了报告的节」算，不是按「发出去的调用」算。
        good_indexes: set[int] = set()
        for unit, digest in zip(units, digests):
            if digest.ok:
                good_indexes.update(unit.source_indexes)
            else:
                result.failures.append(f"{unit.label}：{digest.error or '无主张'}")
        result.sections_covered = len(good_indexes)
        del covered

        by_chapter: dict[str, ChapterDigest] = {}
        for unit, digest in zip(units, digests):
            key = unit.sections[0].chapter if unit.sections else ""
            chapter = by_chapter.get(key)
            if chapter is None:
                chapter = ChapterDigest(chapter=key, title=_chapter_title(outline, key))
                by_chapter[key] = chapter
            chapter.sections.append(digest)
        result.chapters = list(by_chapter.values())

        for chapter in result.chapters:
            claims = [c for s in chapter.sections for c in s.claims]
            if not claims:
                chapter.error = "本章没有任何一节产出主张"
                continue
            try:
                answer = self._ask(build_chapter_prompt(chapter.chapter, chapter.title, claims))
                parsed = parse_sections(answer)
                chapter.summary = " ".join(_pick(parsed, "讲了什么"))
                chapter.through_line = " ".join(_pick(parsed, "主线"))
            except Exception as exc:  # noqa: BLE001
                chapter.error = f"{type(exc).__name__}: {exc}"[:200]
            finally:
                with self._lock:
                    self._calls += 1

        lines = [
            f"【{c.chapter} {c.title}】{c.summary or '（本章未产出摘要）'}"
            for c in result.chapters
        ]
        try:
            answer = self._ask(build_book_prompt(book_title, lines))
            parsed = parse_sections(answer)
            result.book.one_paragraph = " ".join(_pick(parsed, "一段话"))
            result.book.argument = " ".join(_pick(parsed, "全书的主张", "主张"))
            result.book.what_you_get = " ".join(_pick(parsed, "带走"))
            result.book.who_should_read = " ".join(_pick(parsed, "谁该读"))
        except Exception as exc:  # noqa: BLE001
            result.book.error = f"{type(exc).__name__}: {exc}"[:200]
        finally:
            with self._lock:
                self._calls += 1
            result.provider_calls = self._calls
        return result


def _chapter_title(outline: BookOutline, chapter: str) -> str:
    """这一章叫什么。

    先用解析时抽到的章标题；没有才退回「第一节的标题」。退回那一支曾经是唯一的一支，于是
    57 章里 49 章都显示成「INTRODUCTION」——每章第一节的名字，而不是章的名字。
    """
    for node in outline.nodes:
        if node.chapter == chapter and node.chapter_title:
            return node.chapter_title
    for node in outline.nodes:
        if node.chapter == chapter:
            return node.title
    return ""

