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
