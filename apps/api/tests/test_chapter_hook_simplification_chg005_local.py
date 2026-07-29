"""CHG-20260729-005 — hook simplification is FE presentation only; formula untouched."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FORMULA_PATH = REPO_ROOT / "config" / "reader_journey_formulas_v2.json"


def test_formula_v2_untouched_for_chg005():
    text = FORMULA_PATH.read_text(encoding="utf-8")
    assert "reading_momentum" in text
    assert "plot_progress" in text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(digest) == 64


def test_hook_tab_name_unchanged_in_desktop_copy_anchor():
    # Anchor: product tab label remains 钩子回收 (no rename).
    path = (
        REPO_ROOT
        / "apps"
        / "desktop"
        / "src"
        / "components"
        / "readerJourney"
        / "readerJourneyLensExplanation.ts"
    )
    text = path.read_text(encoding="utf-8")
    assert 'title: "钩子回收"' in text
    assert "提出了哪些问题" in text
    assert "回收率越高越好" not in text
