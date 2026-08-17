"""章节识别：非「第N章」格式的兜底 (CHG-20260815-094).

Detection only ever recognised 「第N章」. Three books in a seven-book library arrived as
1–4 "chapters" holding the whole file, which disables everything downstream — the whole-book
planner needs at least 4 chapters per block and 500'd, and per-chapter analysis had nothing
to analyse.

What is pinned here: the house format still wins whenever it works (no re-cutting of books
that were already right), the alternatives only get a turn when it fails, and a loose rule
never fires on prose.
"""

from __future__ import annotations

from app.domain.ingestion import detect_chapters

HOUSE = "\n\n".join(f"第{n}章 标题{n}\n\n正文段落，内容足够长。" for n in "一二三四五六")
ORDINAL = "\n\n".join(f"{n}.黑白道一（{n}）\n\n正文段落，内容足够长。" for n in range(1, 8))
LATIN = "\n\n".join(f"Chapter{n}拿着爱的号码牌（{n}）\n\n正文段落，内容足够长。" for n in range(1, 7))
VOLUME = "\n\n".join(f"第{n}卷 卷名{n}\n\n正文段落，内容足够长。" for n in "一二三四五")


def _adopted(text: str) -> list[str]:
    return [c.text for c in detect_chapters(text).candidates if c.adopted]


def test_house_format_still_detected() -> None:
    assert len(_adopted(HOUSE)) == 6


def test_ordinal_format_detected() -> None:
    # 黑白道: 4 chapters before, 205 candidates after.
    assert len(_adopted(ORDINAL)) == 7


def test_latin_chapter_format_detected() -> None:
    # 剩女遇见爱情: 1 chapter before, 88 candidates after.
    assert len(_adopted(LATIN)) == 6


def test_volume_format_used_only_as_last_resort() -> None:
    assert len(_adopted(VOLUME)) == 5


def test_house_format_wins_when_both_present() -> None:
    # A book carrying both must be cut by the stronger signal, not re-cut by the weaker one.
    mixed = HOUSE + "\n\n" + ORDINAL
    adopted = _adopted(mixed)
    assert len(adopted) >= 6
    assert all(item.startswith("第") for item in adopted[:6])


def test_prose_with_numbers_is_not_mistaken_for_chapters() -> None:
    # The ordinal rule requires a separator AND a title on its own short line; ordinary
    # sentences and bare years must not split a book.
    prose = "\n\n".join(
        [
            "2008.",
            "他在1999年离开，2003年回来，仍旧一个人。",
            "第二天早上，他想起了那句话。",
            "1、",
            "价格是 3.5 元，数量是 12 个。",
        ]
        * 3
    )
    assert len(_adopted(prose)) == 0


def test_single_marker_does_not_trigger_alternative() -> None:
    # Below MIN_BELIEVABLE_CHAPTERS the alternative is not believed either — one stray
    # 「1.」 line must not become the book's only division.
    text = "1.某个小标题\n\n" + "\n\n".join(["普通正文段落。"] * 20)
    assert len(_adopted(text)) == 0


def _bare(n: int, restart_at: int | None = None) -> str:
    """A book whose only chapter markers are numerals alone on their line."""
    out: list[str] = []
    for i in range(1, n + 1):
        out.append(str(i if restart_at is None or i < restart_at else i - restart_at + 1))
        out.append("这一段是第 %d 节的正文，写了一些事情。" % i)
    return "\n\n".join(out)


def test_a_numeral_alone_on_its_line_is_a_chapter_marker() -> None:
    """《一梦如初》 marks its sections with nothing but 1, 2, 3 … and no 第X章 anywhere.

    Before this format was recognised the whole book — 36,714 words — arrived as a single
    chapter, which silently disables every downstream analysis for that book.
    """
    adopted = _adopted(_bare(19))
    assert len(adopted) == 19


def test_a_numeral_run_may_restart_once_for_a_番外() -> None:
    # The real book runs 1…19 and then restarts at 1 under 番外一：慧娘.
    adopted = _adopted(_bare(24, restart_at=20))
    assert len(adopted) == 24


def test_bare_numerals_that_do_not_count_are_not_chapters() -> None:
    """The guard that makes the bare rule safe: markers count, stray numerals do not.

    Every one of these lines matches the pattern. None of them forms an ascending run, and
    adopting any would cut a chapter in the middle of a sentence.
    """
    scattered = "\n\n".join(
        ["他数了数，一共有", "2008", "那年的事。", "5", "又过了几年。", "1999", "他不再提起。", "42"] * 3
    )
    assert len(_adopted(scattered)) == 0


def test_a_run_that_starts_too_high_is_not_believed() -> None:
    # Chapter numbering starts at the beginning. A run of 90, 91, 92 … is a page number or a
    # year column, not a table of contents.
    text = "\n\n".join(sum(([str(n), "正文一段。"] for n in range(90, 99)), []))
    assert len(_adopted(text)) == 0


def test_house_format_still_wins_over_bare_numerals() -> None:
    # A book carrying both must not be re-cut by the weaker signal.
    mixed = HOUSE + "\n\n" + _bare(8)
    adopted = _adopted(mixed)
    assert all(item.startswith("第") and "章" in item for item in adopted)
