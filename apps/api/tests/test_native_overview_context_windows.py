"""STEP 2.3-A1 — Production context window builder unit tests."""

from __future__ import annotations

import pytest

from app.narrative_core.services.native_overview_context_windows import (
    OverviewWindowBudget,
    SnapshotParagraphRef,
    assert_full_coverage,
    build_overview_windows,
    estimate_window_count,
    report_window_coverage,
)


def _paras(n: int, *, text: str = "段落正文", chapter_every: int = 100) -> list[SnapshotParagraphRef]:
    rows: list[SnapshotParagraphRef] = []
    for i in range(n):
        chapter_ord = i // chapter_every
        rows.append(
            SnapshotParagraphRef(
                snapshot_paragraph_id=i + 1,
                paragraph_id=f"p-{i}",
                chapter_id=str(chapter_ord + 1),
                source_chapter_id=chapter_ord + 1,
                paragraph_order=i,
                text=text,
                content_hash=f"h{i}",
            )
        )
    return rows


def test_empty_plan():
    assert build_overview_windows([]) == []
    report = report_window_coverage([], [])
    assert report.original_paragraphs_total == 0
    assert report.windows_total == 0


def test_single_paragraph_one_window():
    planned = build_overview_windows(_paras(1))
    assert len(planned) == 1
    assert planned[0].paragraph_count == 1
    assert planned[0].window_index == 0
    assert assert_full_coverage(planned, _paras(1)).is_complete


def test_short_book_fits_single_window():
    paras = _paras(4, chapter_every=2)
    planned = build_overview_windows(paras)
    assert len(planned) == 1
    assert planned[0].cross_chapter is True
    assert planned[0].paragraph_ids == ("p-0", "p-1", "p-2", "p-3")
    assert assert_full_coverage(planned, paras).is_complete


def test_multi_window_overlap_and_full_coverage():
    paras = _paras(10)
    budget = OverviewWindowBudget(
        max_paragraphs_per_window=4,
        overlap_paragraphs=1,
        max_characters_per_window=100_000,
        max_tokens_estimated=100_000,
    )
    planned = build_overview_windows(paras, budget=budget)
    assert len(planned) >= 3
    # Adjacent windows overlap by 1 paragraph id.
    for left, right in zip(planned, planned[1:]):
        overlap = set(left.paragraph_ids) & set(right.paragraph_ids)
        assert len(overlap) == 1
    report = assert_full_coverage(planned, paras)
    assert report.original_coverage_percent == 100.0
    assert report.original_paragraphs_covered == 10


def test_character_budget_shrinks_windows():
    # Each paragraph is 20 chars; budget 45 chars ⇒ at most 2 paras (+1 newline).
    paras = _paras(5, text="abcdefghijabcdefghij")
    budget = OverviewWindowBudget(
        max_paragraphs_per_window=40,
        overlap_paragraphs=1,
        max_characters_per_window=45,
        max_tokens_estimated=100_000,
    )
    planned = build_overview_windows(paras, budget=budget)
    assert len(planned) >= 3
    assert all(w.paragraph_count <= 2 for w in planned)
    assert assert_full_coverage(planned, paras).is_complete


def test_oversized_single_paragraph_still_emitted():
    huge = "x" * 50_000
    paras = [
        SnapshotParagraphRef(
            snapshot_paragraph_id=1,
            paragraph_id="p-huge",
            chapter_id="1",
            source_chapter_id=1,
            paragraph_order=0,
            text=huge,
        )
    ]
    budget = OverviewWindowBudget(
        max_paragraphs_per_window=10,
        overlap_paragraphs=2,
        max_characters_per_window=100,
        max_tokens_estimated=50,
    )
    planned = build_overview_windows(paras, budget=budget)
    assert len(planned) == 1
    assert planned[0].character_count == 50_000
    assert assert_full_coverage(planned, paras).is_complete


def test_zero_overlap_no_shared_paragraphs():
    paras = _paras(6)
    budget = OverviewWindowBudget(
        max_paragraphs_per_window=2,
        overlap_paragraphs=0,
        max_characters_per_window=100_000,
        max_tokens_estimated=100_000,
    )
    planned = build_overview_windows(paras, budget=budget)
    assert len(planned) == 3
    for left, right in zip(planned, planned[1:]):
        assert set(left.paragraph_ids).isdisjoint(right.paragraph_ids)
    assert assert_full_coverage(planned, paras).is_complete


def test_incomplete_coverage_raises():
    paras = _paras(3)
    planned = build_overview_windows(paras[:2])
    with pytest.raises(ValueError, match="incomplete coverage"):
        assert_full_coverage(planned, paras)


def test_budget_validation():
    with pytest.raises(ValueError):
        OverviewWindowBudget(max_paragraphs_per_window=2, overlap_paragraphs=2)
    with pytest.raises(ValueError):
        OverviewWindowBudget(max_characters_per_window=0)


def test_estimate_window_count():
    assert estimate_window_count(0) == 0
    assert estimate_window_count(4) == 1
    assert estimate_window_count(80, budget=OverviewWindowBudget(max_paragraphs_per_window=40, overlap_paragraphs=2)) >= 2
