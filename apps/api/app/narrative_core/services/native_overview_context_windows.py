"""Production context-window builder for native Whole-Book Overview (STEP 2.3-A1).

Builds multi-window slices over Snapshot paragraphs with overlap, character/token
budgets, and guaranteed original coverage (every valid paragraph in ≥1 window).
Cross-chapter windows are allowed. Does not persist DB rows — Orchestrator does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# Rough token estimate — language-agnostic heuristic (matches whole_book_context_units).
_CHARS_PER_TOKEN = 4

# Production defaults — aligned with ParagraphGroupingPolicy initial values.
DEFAULT_MAX_PARAGRAPHS_PER_WINDOW = 40
DEFAULT_OVERLAP_PARAGRAPHS = 2
DEFAULT_MAX_CHARACTERS_PER_WINDOW = 12_000
DEFAULT_MAX_TOKENS_ESTIMATED = 3_000


@dataclass(frozen=True, slots=True)
class OverviewWindowBudget:
    """Budgets for production window slicing. Not book-title keyed."""

    max_paragraphs_per_window: int = DEFAULT_MAX_PARAGRAPHS_PER_WINDOW
    overlap_paragraphs: int = DEFAULT_OVERLAP_PARAGRAPHS
    max_characters_per_window: int = DEFAULT_MAX_CHARACTERS_PER_WINDOW
    max_tokens_estimated: int = DEFAULT_MAX_TOKENS_ESTIMATED
    chars_per_token: int = _CHARS_PER_TOKEN

    def __post_init__(self) -> None:
        if self.max_paragraphs_per_window < 1:
            raise ValueError("max_paragraphs_per_window must be >= 1")
        if self.overlap_paragraphs < 0:
            raise ValueError("overlap_paragraphs must be >= 0")
        if self.overlap_paragraphs >= self.max_paragraphs_per_window:
            raise ValueError("overlap_paragraphs must be < max_paragraphs_per_window")
        if self.max_characters_per_window < 1:
            raise ValueError("max_characters_per_window must be >= 1")
        if self.max_tokens_estimated < 1:
            raise ValueError("max_tokens_estimated must be >= 1")
        if self.chars_per_token < 1:
            raise ValueError("chars_per_token must be >= 1")

    def estimate_tokens(self, character_count: int) -> int:
        return max(0, (int(character_count) + self.chars_per_token - 1) // self.chars_per_token)


@dataclass(frozen=True, slots=True)
class SnapshotParagraphRef:
    """Minimal Snapshot paragraph locator used by the window planner."""

    snapshot_paragraph_id: int
    paragraph_id: str
    chapter_id: str
    source_chapter_id: int | None
    paragraph_order: int
    text: str
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class PlannedOverviewWindow:
    """One planned production window (not yet persisted)."""

    window_index: int
    snapshot_paragraph_ids: tuple[int, ...]
    paragraph_ids: tuple[str, ...]
    start_paragraph_id: str
    end_paragraph_id: str
    start_chapter_id: int | None
    end_chapter_id: int | None
    chapter_ids: tuple[str, ...]
    character_count: int
    token_estimate: int
    cross_chapter: bool

    @property
    def paragraph_count(self) -> int:
        return len(self.snapshot_paragraph_ids)


@dataclass(frozen=True, slots=True)
class WindowCoverageReport:
    """Coverage of planned windows over the Snapshot paragraph set."""

    original_paragraphs_total: int
    original_paragraphs_covered: int
    original_coverage_percent: float
    windows_total: int
    uncovered_paragraph_ids: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return (
            self.original_paragraphs_total > 0
            and self.original_paragraphs_covered == self.original_paragraphs_total
            and abs(self.original_coverage_percent - 100.0) < 1e-9
        )


def _slice_metrics(
    paragraphs: Sequence[SnapshotParagraphRef],
    start: int,
    end: int,
    budget: OverviewWindowBudget,
) -> tuple[int, int]:
    texts = [paragraphs[i].text for i in range(start, end)]
    char_count = sum(len(t) for t in texts) + max(0, len(texts) - 1)
    return char_count, budget.estimate_tokens(char_count)


def _fit_end(
    paragraphs: Sequence[SnapshotParagraphRef],
    start: int,
    proposed_end: int,
    budget: OverviewWindowBudget,
) -> int:
    """Shrink end so the slice respects character/token budgets.

    Always keeps at least ``start+1`` (single oversized paragraph still gets a window).
    """
    end = min(proposed_end, len(paragraphs))
    if end <= start:
        return start + 1 if start < len(paragraphs) else start

    while end > start + 1:
        char_count, tokens = _slice_metrics(paragraphs, start, end, budget)
        if (
            char_count <= budget.max_characters_per_window
            and tokens <= budget.max_tokens_estimated
        ):
            break
        end -= 1
    return end


def build_overview_windows(
    paragraphs: Sequence[SnapshotParagraphRef],
    *,
    budget: OverviewWindowBudget | None = None,
) -> list[PlannedOverviewWindow]:
    """Plan overlapping windows covering 100% of ordered Snapshot paragraphs.

    Edge cases:
    - empty input → empty plan (caller rejects BOOK_CONTENT_EMPTY)
    - single paragraph → one window
    - short book under all budgets → one window
    - single paragraph exceeding char/token budget → still one dedicated window
    - multi-window → adjacent windows overlap by ``overlap_paragraphs`` (clamped)
    """
    policy = budget or OverviewWindowBudget()
    ordered = list(paragraphs)
    if not ordered:
        return []

    windows: list[PlannedOverviewWindow] = []
    n = len(ordered)
    max_paras = policy.max_paragraphs_per_window
    overlap = min(policy.overlap_paragraphs, max(0, max_paras - 1))

    start = 0
    index = 0
    while start < n:
        proposed_end = min(n, start + max_paras)
        end = _fit_end(ordered, start, proposed_end, policy)
        slice_paras = ordered[start:end]
        char_count, tokens = _slice_metrics(ordered, start, end, policy)
        chapter_ids = tuple(dict.fromkeys(p.chapter_id for p in slice_paras))
        start_ch = slice_paras[0].source_chapter_id
        end_ch = slice_paras[-1].source_chapter_id
        windows.append(
            PlannedOverviewWindow(
                window_index=index,
                snapshot_paragraph_ids=tuple(p.snapshot_paragraph_id for p in slice_paras),
                paragraph_ids=tuple(p.paragraph_id for p in slice_paras),
                start_paragraph_id=slice_paras[0].paragraph_id,
                end_paragraph_id=slice_paras[-1].paragraph_id,
                start_chapter_id=start_ch,
                end_chapter_id=end_ch,
                chapter_ids=chapter_ids,
                character_count=char_count,
                token_estimate=tokens,
                cross_chapter=start_ch != end_ch,
            )
        )
        index += 1
        if end >= n:
            break
        # Overlap advance with guaranteed forward progress (handles budget-shrunk slices).
        if overlap > 0:
            start = max(start + 1, end - overlap)
        else:
            start = end

    return windows


def report_window_coverage(
    planned: Sequence[PlannedOverviewWindow],
    paragraphs: Sequence[SnapshotParagraphRef],
) -> WindowCoverageReport:
    """Compute unique paragraph coverage for planned windows."""

    total_ids = [p.paragraph_id for p in paragraphs]
    total = len(total_ids)
    if total == 0:
        return WindowCoverageReport(
            original_paragraphs_total=0,
            original_paragraphs_covered=0,
            original_coverage_percent=0.0,
            windows_total=len(planned),
            uncovered_paragraph_ids=(),
        )

    covered: set[str] = set()
    for window in planned:
        covered.update(window.paragraph_ids)
    uncovered = tuple(pid for pid in total_ids if pid not in covered)
    covered_count = total - len(uncovered)
    percent = round(covered_count / total * 100.0, 6) if total else 0.0
    return WindowCoverageReport(
        original_paragraphs_total=total,
        original_paragraphs_covered=covered_count,
        original_coverage_percent=percent,
        windows_total=len(planned),
        uncovered_paragraph_ids=uncovered,
    )


def assert_full_coverage(
    planned: Sequence[PlannedOverviewWindow],
    paragraphs: Sequence[SnapshotParagraphRef],
) -> WindowCoverageReport:
    """Raise ValueError when planned windows do not cover every paragraph."""

    report = report_window_coverage(planned, paragraphs)
    if paragraphs and not report.is_complete:
        raise ValueError(
            "overview window plan incomplete coverage: "
            f"covered={report.original_paragraphs_covered}/"
            f"{report.original_paragraphs_total} "
            f"uncovered={list(report.uncovered_paragraph_ids)}"
        )
    return report


def estimate_window_count(
    paragraph_count: int,
    *,
    character_count: int = 0,
    budget: OverviewWindowBudget | None = None,
) -> int:
    """Cheap preflight estimate (upper-bound style) without loading paragraph texts."""

    policy = budget or OverviewWindowBudget()
    if paragraph_count <= 0:
        return 0
    by_paras = 1
    step = max(1, policy.max_paragraphs_per_window - policy.overlap_paragraphs)
    remaining = paragraph_count
    while remaining > policy.max_paragraphs_per_window:
        by_paras += 1
        remaining -= step
    if character_count > 0:
        # Rough lower-bound on windows from character budget (no overlap discount).
        by_chars = max(
            1,
            (character_count + policy.max_characters_per_window - 1)
            // policy.max_characters_per_window,
        )
        return max(by_paras, by_chars)
    return by_paras


__all__ = [
    "DEFAULT_MAX_CHARACTERS_PER_WINDOW",
    "DEFAULT_MAX_PARAGRAPHS_PER_WINDOW",
    "DEFAULT_MAX_TOKENS_ESTIMATED",
    "DEFAULT_OVERLAP_PARAGRAPHS",
    "OverviewWindowBudget",
    "PlannedOverviewWindow",
    "SnapshotParagraphRef",
    "WindowCoverageReport",
    "assert_full_coverage",
    "build_overview_windows",
    "estimate_window_count",
    "report_window_coverage",
]
