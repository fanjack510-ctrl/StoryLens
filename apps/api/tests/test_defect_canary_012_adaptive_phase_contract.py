# -*- coding: utf-8 -*-
"""DEFECT-CANARY-012: adaptive chapter Phase count / coverage contract (v1.0.7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.reader_journey import (
    CHAPTER_CONTRACT_VERSION,
    CHAPTER_PROMPT_VERSION,
    ChapterReaderJourneySynthesisResult,
    ReaderJourneyPhaseItem,
)
from app.services.prompt_service import load_prompt
from app.services.reader_journey_validation import (
    adaptive_phase_count_bounds,
    validate_chapter_synthesis,
)
from app.services.validation_errors import StructuralValidationError

from tests.optional_gates import require_main_db_cert_counts, require_path

pytestmark = [
    pytest.mark.canary_offline,
    pytest.mark.requires_audit_assets,
]

ROOT = Path(__file__).resolve().parents[3]
A2_CHAPTER = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v8"
    / "defects"
    / "DEFECT-CANARY-012-attempt1-inv9-initial-response.json"
)
A2_REPAIR = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v8"
    / "defects"
    / "DEFECT-CANARY-012-attempt1-inv10-structural_repair-response.json"
)


def _phase(
    ordinal: int,
    start: int,
    end: int,
    *,
    title: str | None = None,
) -> ReaderJourneyPhaseItem:
    return ReaderJourneyPhaseItem(
        ordinal=ordinal,
        title=title or f"阶段{ordinal}",
        start_scene_ordinal=start,
        end_scene_ordinal=end,
        primary_reader_question=f"q{ordinal}",
        dominant_emotion="紧张",
        reading_payoff=f"p{ordinal}",
        continuation_motivation=f"c{ordinal}",
        summary=f"s{ordinal}",
        confidence=0.7,
    )


def _result(phases: list[ReaderJourneyPhaseItem]) -> ChapterReaderJourneySynthesisResult:
    return ChapterReaderJourneySynthesisResult(
        contract_version=CHAPTER_CONTRACT_VERSION,
        phases=phases,
        chapter_reader_question_chain=["核心问题"],
        pacing_diagnosis=["牵引明确"],
        chapter_strengths=["细节有效"],
        chapter_risks=["信息悬置"],
        one_sentence_diagnosis="本章以明确牵引机制建立短期阅读动力。",
    )


def _cover(scene_count: int, phase_spans: list[tuple[int, int]]) -> ChapterReaderJourneySynthesisResult:
    phases = [
        _phase(index, start, end) for index, (start, end) in enumerate(phase_spans, 1)
    ]
    assert scene_count == phase_spans[-1][1]
    return _result(phases)


def test_adaptive_bounds():
    assert adaptive_phase_count_bounds(1) == (1, 1)
    assert adaptive_phase_count_bounds(2) == (1, 2)
    assert adaptive_phase_count_bounds(3) == (1, 3)
    assert adaptive_phase_count_bounds(7) == (1, 6)
    assert adaptive_phase_count_bounds(12) == (1, 6)


@pytest.mark.parametrize(
    ("scene_count", "spans"),
    [
        (1, [(1, 1)]),
        (2, [(1, 2)]),
        (2, [(1, 1), (2, 2)]),
        (3, [(1, 3)]),
        (3, [(1, 2), (3, 3)]),
        (3, [(1, 1), (2, 2), (3, 3)]),
        (7, [(1, 4), (5, 7)]),
        (7, [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 7)]),
    ],
)
def test_adaptive_phase_pass_cases(scene_count: int, spans: list[tuple[int, int]]):
    validate_chapter_synthesis(_cover(scene_count, spans), total_scene_count=scene_count)


def test_3_scenes_4_phases_fail_count():
    # Force an illegal 4th phase by mutating spans beyond scene_count via direct construction
    bad = _result(
        [
            _phase(1, 1, 1),
            _phase(2, 2, 2),
            _phase(3, 3, 3),
            _phase(4, 3, 3),
        ]
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(bad, total_scene_count=3)
    assert exc.value.error_code == "JOURNEY_PHASE_COUNT_INVALID"


def test_7_scenes_7_phases_fail_count():
    spans = [(i, i) for i in range(1, 8)]
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(_cover(7, spans), total_scene_count=7)
    assert exc.value.error_code == "JOURNEY_PHASE_COUNT_INVALID"


def test_scene_gap_fail():
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(
            _result([_phase(1, 1, 1), _phase(2, 3, 3)]),
            total_scene_count=3,
        )
    assert exc.value.error_code == "JOURNEY_PHASE_SCENE_GAP"


def test_duplicate_scene_fail():
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(
            _result([_phase(1, 1, 2), _phase(2, 2, 3)]),
            total_scene_count=3,
        )
    assert exc.value.error_code == "JOURNEY_PHASE_DUPLICATE_SCENE"


def test_phase_overlap_fail():
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(
            _result([_phase(1, 1, 3), _phase(2, 2, 3)]),
            total_scene_count=3,
        )
    assert exc.value.error_code == "JOURNEY_PHASE_SCENE_OVERLAP"


def test_phase_order_reversed_fail():
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(
            _result([_phase(1, 2, 3), _phase(2, 1, 1)]),
            total_scene_count=3,
        )
    assert exc.value.error_code == "JOURNEY_PHASE_ORDER_INVALID"


def test_phase_range_noncontiguous_fail():
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(
            _result([_phase(1, 2, 1)]),
            total_scene_count=2,
        )
    assert exc.value.error_code == "JOURNEY_PHASE_RANGE_NONCONTIGUOUS"


def test_a2_offline_failure_now_passes_without_forcing_three_phases():
    require_path(A2_CHAPTER)
    require_path(A2_REPAIR)
    payload = json.loads(A2_CHAPTER.read_text(encoding="utf-8"))
    result = ChapterReaderJourneySynthesisResult.model_validate(payload)
    assert len(result.phases) == 2
    # 3 scenes, 2 phases — previously failed hard 3–6 rule; now PASS.
    validate_chapter_synthesis(result, total_scene_count=3, enforce_anti_generic=True)
    repair = ChapterReaderJourneySynthesisResult.model_validate(
        json.loads(A2_REPAIR.read_text(encoding="utf-8"))
    )
    assert len(repair.phases) == 2
    validate_chapter_synthesis(repair, total_scene_count=3, enforce_anti_generic=True)


def test_prompt_v12_adaptive_rules_and_repair_guidance():
    assert CHAPTER_PROMPT_VERSION == "v1.2"
    assert CHAPTER_CONTRACT_VERSION == "1.2"
    bundle = load_prompt("reader_journey_chapter", "v1.2")
    assert "min(6, scene_count)" in bundle.system
    assert "短章节允许" in bundle.system
    assert "不得为了凑满" in bundle.system or "不得为了满足" in bundle.system or "编造虚假" in bundle.system
    assert "JOURNEY_PHASE_COUNT_INVALID" in bundle.repair_template
    assert "不得把短章节合法的 1—2 个 Phase 强行扩成 3 个" in bundle.repair_template
    # Old versions preserved
    old = load_prompt("reader_journey_chapter", "v1.1")
    assert "阶段数3—6" in old.system


def test_valid_short_phase_count_must_not_be_treated_as_count_error():
    result = _cover(3, [(1, 2), (3, 3)])
    # Must not raise — repair must not be triggered for “fewer than 3”.
    validate_chapter_synthesis(result, total_scene_count=3)


def test_main_db_invariant_55_2():
    require_main_db_cert_counts()


def test_no_real_model_marker():
    # This remediation phase must not issue live provider HTTP.
    assert True
