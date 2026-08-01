"""StructureStages output contract V2 — empty-policy / binding codes."""

from __future__ import annotations

from app.narrative_core.services.structure_stages_output_contract_v2 import (
    FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH,
    FAILURE_EMPTY_RESULT_AFTER_REPAIR,
    FAILURE_REQUIRED_STAGE_MISSING,
    FAILURE_STRUCTURE_CONTRACT,
    _public_shape_validate,
    repair_instruction_text_v2,
)


def test_failure_constants_match_private_codes():
    assert FAILURE_REQUIRED_STAGE_MISSING == "STRUCTURE_REQUIRED_STAGE_MISSING"
    assert FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH == (
        "STRUCTURE_COVERAGE_SCOPE_BINDING_MISMATCH"
    )
    assert FAILURE_EMPTY_RESULT_AFTER_REPAIR == "STRUCTURE_EMPTY_RESULT_AFTER_REPAIR"
    assert FAILURE_STRUCTURE_CONTRACT == "STRUCTURE_CONTRACT_FAILURE"


def test_public_shape_insufficient_empty_without_caps_ok():
    typed, err = _public_shape_validate(
        {
            "contract_version": "v2",
            "coverage_scope": "insufficient",
            "stages": [],
            "turning_points": [],
        },
        allowed_citation_ids=["CIT-AAAAAAAA-0001"],
        capabilities=None,
    )
    assert err is None
    assert typed is not None
    assert typed["stages"] == []


def test_public_shape_local_empty_without_caps_required_stage():
    typed, err = _public_shape_validate(
        {
            "contract_version": "v2",
            "coverage_scope": "local",
            "stages": [],
            "turning_points": [],
        },
        allowed_citation_ids=["CIT-AAAAAAAA-0001"],
        capabilities=None,
    )
    assert typed is None
    assert err == FAILURE_REQUIRED_STAGE_MISSING


def test_public_shape_caps_local_empty_uses_validate_coverage():
    typed, err = _public_shape_validate(
        {
            "contract_version": "v2",
            "coverage_scope": "local",
            "stages": [],
            "turning_points": [],
        },
        allowed_citation_ids=["CIT-AAAAAAAA-0001"],
        capabilities={
            "selected_chapter_orders": (1, 2),
            "all_chapter_orders": (1, 2, 3, 4),
            "selected_paragraph_count": 2,
            "batch_count": 2,
        },
    )
    assert typed is None
    assert err == FAILURE_REQUIRED_STAGE_MISSING


def test_public_shape_caps_binding_mismatch_insufficient():
    typed, err = _public_shape_validate(
        {
            "contract_version": "v2",
            "coverage_scope": "insufficient",
            "stages": [],
            "turning_points": [],
        },
        allowed_citation_ids=["CIT-AAAAAAAA-0001"],
        capabilities={
            "selected_chapter_orders": (1, 2, 3, 4, 5, 6, 7, 8),
            "all_chapter_orders": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
            "selected_paragraph_count": 32,
            "batch_index": 0,
            "batch_count": 2,
        },
    )
    assert typed is None
    assert err == FAILURE_COVERAGE_SCOPE_BINDING_MISMATCH


def test_repair_instruction_empty_binding_uses_frozen_scope():
    text = repair_instruction_text_v2(
        failure_code=FAILURE_REQUIRED_STAGE_MISSING,
        observed_fields=("contract_version", "coverage_scope", "stages"),
        citation_ids=["CIT-AAAAAAAA-0001"],
        capabilities={
            "selected_chapter_orders": (1, 2),
            "all_chapter_orders": (1, 2, 3, 4),
            "selected_paragraph_count": 2,
            "batch_count": 2,
        },
        actual_coverage_scope="insufficient",
        stage_count=0,
        turning_point_count=0,
    )
    assert "expected_coverage_scope" in text
    assert "can_identify_local_stages" in text
    assert "requires_stage_observation" in text or "≥1 legal stage" in text
