"""「读懂」的执行层。

这份产出会被当成原文的替代品。所以这里盯的不是「跑得通」，而是三件会让它不可信的事：

  · 一次调用失败被静默跳过 —— 那几节的内容从报告里消失，而读者不会知道
  · 模型答非所问却算成功 —— 覆盖率虚高，读者以为读全了
  · 并发改变结果 —— 那这份报告就不可复现
"""

from __future__ import annotations

import threading
import time

from app.domain.document_outline import BookOutline, OutlineNode
from app.narrative_core.comprehend.coordinator import ComprehendCoordinator, parse_sections

GOOD = """## 主张
· 分类数据应当用色相区分，类别数不宜超过 12 种
1. 定量数据应使用同一色相的明度渐变
## 依据
Palmer & Schloss (2010) 的色彩偏好实验
## 做法
从 ColorBrewer 选取不超过 12 种色相
## 术语
Sequential mapping（顺序映射）
## 存疑
如何量化「感知均匀」带来的决策效率提升？
"""


def _outline(n: int = 6) -> BookOutline:
    body = " ".join(["word"] * 900)
    return BookOutline(
        nodes=[
            OutlineNode(2, f"1.{i}", f"Section {i}", [body], chapter="第1章")
            for i in range(1, n + 1)
        ],
        source="declared",
    )


def test_bullets_and_numbering_are_stripped_once_not_stacked() -> None:
    """留着它们，导出的报告里会出现「· 1. · 分类数据……」这种叠三层的行。"""
    parsed = parse_sections(GOOD)
    assert parsed["主张"][0].startswith("分类数据")
    assert parsed["主张"][1].startswith("定量数据")


def test_a_failed_call_is_recorded_and_lowers_coverage() -> None:
    """静默跳过 = 内容消失且读者不知道。失败必须进结果，并把覆盖率拉下来。"""
    calls = {"n": 0}

    def ask(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("provider exploded")
        return GOOD

    res = ComprehendCoordinator(ask=ask, concurrency=1).run(_outline(), book_title="书")
    assert res.failures, "失败没有留痕"
    assert res.sections_covered < res.sections_total


def test_an_off_format_answer_does_not_count_as_covered() -> None:
    """拿回了字符串但没有主张，跟成功不是一回事——否则覆盖率虚高，读者以为读全了。"""
    res = ComprehendCoordinator(ask=lambda p: "我觉得这本书挺好的。", concurrency=1).run(
        _outline(2), book_title="书"
    )
    assert res.sections_covered == 0
    assert not res.trustworthy


def test_full_coverage_reads_as_trustworthy() -> None:
    res = ComprehendCoordinator(ask=lambda p: GOOD, concurrency=1).run(_outline(), book_title="书")
    assert res.sections_covered == res.sections_total
    assert res.trustworthy
    assert res.chapters and res.chapters[0].sections


def test_concurrency_does_not_change_the_result() -> None:
    """节与节之间没有依赖，所以并发只该改变墙上时间。改变了结果，报告就不可复现。"""
    serial = ComprehendCoordinator(ask=lambda p: GOOD, concurrency=1).run(_outline(8), book_title="书")
    parallel = ComprehendCoordinator(ask=lambda p: GOOD, concurrency=4).run(_outline(8), book_title="书")
    assert serial.sections_covered == parallel.sections_covered
    assert [s.label for c in serial.chapters for s in c.sections] == [
        s.label for c in parallel.chapters for s in c.sections
    ]


def test_sections_really_run_at_the_same_time() -> None:
    """不重叠的话，「并发」只是个名字。"""
    seen: list[tuple[float, float]] = []
    lock = threading.Lock()

    def ask(prompt: str) -> str:
        start = time.monotonic()
        time.sleep(0.05)
        with lock:
            seen.append((start, time.monotonic()))
        return GOOD

    ComprehendCoordinator(ask=ask, concurrency=4).run(_outline(8), book_title="书")
    overlapped = any(
        a[0] < b[1] and b[0] < a[1] for i, a in enumerate(seen) for b in seen[i + 1:]
    )
    assert overlapped


def test_progress_is_reported_per_completed_call() -> None:
    ticks: list[tuple[int, int]] = []
    ComprehendCoordinator(
        ask=lambda p: GOOD, concurrency=1, on_call=lambda done, total: ticks.append((done, total))
    ).run(_outline(4), book_title="书")
    assert ticks and ticks[-1][0] >= ticks[0][0]


def test_an_empty_book_says_so_instead_of_pretending() -> None:
    res = ComprehendCoordinator(ask=lambda p: GOOD).run(BookOutline(), book_title="书")
    assert res.book.error
    assert not res.trustworthy


def test_a_bold_marker_is_not_mistaken_for_a_bullet() -> None:
    """`**该读**：…` 被吃掉一个星号会变成 `*该读**：…` —— 报告里多一个孤零零的星号。

    项目符号后面必须跟空白才算项目符号。
    """
    parsed = parse_sections("## 谁该读\n**该读**：设计师\n**不必读**：纯后端\n")
    assert parsed["谁该读"][0].startswith("该读")
    assert "*" not in "".join(parsed["谁该读"])


def test_a_real_bullet_is_still_stripped() -> None:
    parsed = parse_sections("## 主张\n· 第一条\n- 第二条\n* 第三条\n")
    assert parsed["主张"] == ["第一条", "第二条", "第三条"]
