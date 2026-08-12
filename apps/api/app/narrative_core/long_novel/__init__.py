"""LongNovelAnalysisEngine — Phase 1 Foundation.

Implements the contracts frozen in ``DESIGN_FREEZE.md`` (2026-08-12): identity derivation,
budgets, provider robustness, persistence and invariants. **There is no pipeline here and
nothing routes to this package** — extraction, reduction, interpretation, projection and
synthesis are Phase 2 and later.

The engine exists because whole-book analysis of a 542-chapter novel cannot be done by
re-reading prose at every level. It reads the text exactly once, at L1, into immutable
paragraph-anchored facts, and every layer above works over those facts within an input
budget that is decided *before* a request is sent. Three properties are worth knowing before
reading any module here:

* **Identity is layered and never positional.** No provider-array ordinal and no global
  chapter ordinal enters any key, so reordering a model's output or inserting a chapter
  cannot invalidate work that did not change.
* **Every provider call is bounded in book length.** Including repair, and including the
  pacing projection, whose curve is resampled to a fixed number of bins.
* **Ambiguity fails closed.** Rebase, mention occurrence and anchor mismatches refuse rather
  than guess, because a wrong guess in any of them is silent corruption that passes every
  other check.
"""

from __future__ import annotations

from app.narrative_core.long_novel.errors import (
    FailureClass,
    LongNovelError,
    LongNovelErrorCode,
    failure_class,
    is_locally_repairable,
)

__all__ = [
    "FailureClass",
    "LongNovelError",
    "LongNovelErrorCode",
    "failure_class",
    "is_locally_repairable",
]
