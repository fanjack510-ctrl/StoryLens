"""WB-0.2 Public whole_book_contract_v1 automated tests (L1 / zero-cost)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.narrative_core.contracts.whole_book_contract_v1 import (
    BOOK_OVERVIEW_CLAIM_KEYS_V1,
    ArtifactState,
    BookOverviewClaimV1,
    BookOverviewResultV1,
    CandidateAssetV1,
    CandidateEntityV1,
    CandidateEvidenceV1,
    CandidateNarrativeRefV1,
    CandidateRelationV1,
    EngineProposalDecision,
    EvidenceState,
    NarrativeAssetVersionV1,
    NarrativeRefKind,
    OverviewClaimAvailability,
    ResultOrigin,
    SnapshotEvidenceLocatorV1,
    SnapshotStatus,
    WholeBookMode,
    WholeBookRunStageV1,
    WholeBookRunStatus,
    WholeBookStageStatus,
    WholeBookWindowAnalysisResponseV1,
    WholeBookWindowCoverageV1,
    build_wire_contract_schema,
    canonical_json_bytes,
    evaluate_engine_proposal_against_current_version,
    schema_sha256,
    validate_evidence_locator,
    validate_window_analysis_response_v1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from tests.whole_book_contract_v1_fixtures import (
    make_coverage,
    make_paragraph,
    make_provenance,
    make_run,
    make_sha,
    make_snapshot,
    make_window,
    native_usage,
    utc_now,
)


def test_01_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        make_snapshot().model_copy()
        BookSnapshot = make_snapshot().__class__
        BookSnapshot.model_validate({**make_snapshot().model_dump(mode="json"), "extra": 1})


def test_02_illegal_sha_rejected() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(content_hash="not-a-sha")


def test_03_non_utc_datetime_rejected() -> None:
    local = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    with pytest.raises(ValidationError):
        make_snapshot(created_at=local, completed_at=local)


def test_04_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        CandidateEntityV1(
            candidate_key="e1",
            entity_type="character",
            canonical_name="A",
            confidence=1.5,
            evidence_keys=["ev1"],
        )


def test_05_native_nonzero_chapter_assets_rejected() -> None:
    with pytest.raises(ValidationError):
        make_run(
            mode=WholeBookMode.whole_book_native,
            input_usage=native_usage().model_copy(update={"chapter_analysis_asset_count": 1}),
        )


def test_06_enhanced_requires_full_text_snapshot() -> None:
    with pytest.raises(ValidationError):
        make_run(
            mode=WholeBookMode.whole_book_enhanced,
            input_usage=native_usage().model_copy(
                update={
                    "full_text_snapshot_used": False,
                    "chapter_analysis_asset_count": 1,
                }
            ),
        )


def test_07_completed_snapshot_requires_completed_at() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(status=SnapshotStatus.completed, completed_at=None)


def test_08_building_snapshot_forbids_completed_at() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(status=SnapshotStatus.building, completed_at=utc_now())


def test_09_paragraph_character_count_mismatch() -> None:
    with pytest.raises(ValidationError):
        make_paragraph(text="abc", character_count=2)


def test_10_evidence_offset_oob_unresolved() -> None:
    text = "abcdef"
    locator = SnapshotEvidenceLocatorV1(
        snapshot_id=1,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        chapter_id=1,
        chapter_index=0,
        paragraph_index=0,
        global_paragraph_index=0,
        start_offset=0,
        end_offset=100,
        quote_text="x",
        quote_hash=sha256_hex("x"),
        paragraph_text_hash=sha256_hex(text),
    )
    # quote mismatch + oob → unresolved
    assert validate_evidence_locator(locator, text) == EvidenceState.unresolved


def test_11_evidence_quote_mismatch_unresolved() -> None:
    text = "abcdef"
    locator = SnapshotEvidenceLocatorV1(
        snapshot_id=1,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        chapter_id=1,
        chapter_index=0,
        paragraph_index=0,
        global_paragraph_index=0,
        start_offset=0,
        end_offset=3,
        quote_text="zzz",
        quote_hash=sha256_hex("zzz"),
        paragraph_text_hash=sha256_hex(text),
    )
    assert validate_evidence_locator(locator, text) == EvidenceState.unresolved


def test_12_evidence_paragraph_hash_mismatch_stale() -> None:
    text = "abcdef"
    locator = SnapshotEvidenceLocatorV1(
        snapshot_id=1,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        chapter_id=1,
        chapter_index=0,
        paragraph_index=0,
        global_paragraph_index=0,
        start_offset=0,
        end_offset=3,
        quote_text="abc",
        quote_hash=sha256_hex("abc"),
        paragraph_text_hash=sha256_hex("other"),
    )
    assert validate_evidence_locator(locator, text) == EvidenceState.stale


def test_13_run_completed_requires_completed_at() -> None:
    with pytest.raises(ValidationError):
        make_run(status=WholeBookRunStatus.completed, completed_at=None)


def test_14_run_failed_requires_failure_code() -> None:
    with pytest.raises(ValidationError):
        make_run(status=WholeBookRunStatus.failed, failed_at=utc_now(), failure_code=None)


def test_15_stage_progress_current_gt_total() -> None:
    with pytest.raises(ValidationError):
        WholeBookRunStageV1(
            stage_id=1,
            run_id=1,
            stage_code="windowing",
            sequence=0,
            status=WholeBookStageStatus.running,
            progress_current=3,
            progress_total=2,
        )


def test_16_completed_stage_progress_incomplete() -> None:
    with pytest.raises(ValidationError):
        WholeBookRunStageV1(
            stage_id=1,
            run_id=1,
            stage_code="windowing",
            sequence=0,
            status=WholeBookStageStatus.completed,
            progress_current=1,
            progress_total=2,
            completed_at=utc_now(),
        )


def test_17_window_invalid_range() -> None:
    with pytest.raises(ValidationError):
        make_window(first_global_paragraph_index=5, last_global_paragraph_index=1)


def test_18_coverage_math() -> None:
    cov = WholeBookWindowCoverageV1(
        snapshot_id=1,
        run_id=1,
        total_paragraphs=10,
        covered_unique_paragraphs=8,
        duplicated_paragraphs=2,
        uncovered_paragraphs=2,
        coverage_ratio=0.8,
        order_valid=True,
        first_global_paragraph_index=0,
        last_global_paragraph_index=9,
    )
    assert cov.coverage_ratio == 0.8
    empty = WholeBookWindowCoverageV1(
        snapshot_id=1,
        run_id=1,
        total_paragraphs=0,
        covered_unique_paragraphs=0,
        duplicated_paragraphs=0,
        uncovered_paragraphs=0,
        coverage_ratio=1.0,
        order_valid=True,
    )
    assert empty.coverage_ratio == 1.0


def _valid_locator(text: str = "hello world") -> SnapshotEvidenceLocatorV1:
    return SnapshotEvidenceLocatorV1(
        snapshot_id=1,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        chapter_id=1,
        chapter_index=0,
        paragraph_index=0,
        global_paragraph_index=0,
        start_offset=0,
        end_offset=5,
        quote_text=text[:5],
        quote_hash=sha256_hex(text[:5]),
        paragraph_text_hash=sha256_hex(text),
    )


def test_19_candidate_missing_evidence_ref_rejected() -> None:
    resp = WholeBookWindowAnalysisResponseV1(
        run_id=1,
        snapshot_id=1,
        window_id=1,
        entities=[
            CandidateEntityV1(
                candidate_key="e1",
                entity_type="character",
                canonical_name="A",
                confidence=0.9,
                evidence_keys=["missing"],
            )
        ],
        evidences=[],
        provenance=make_provenance(),
    )
    with pytest.raises(ValueError, match="missing evidence"):
        validate_window_analysis_response_v1(resp)


def test_20_relation_missing_candidate_ref_rejected() -> None:
    loc = _valid_locator()
    resp = WholeBookWindowAnalysisResponseV1(
        run_id=1,
        snapshot_id=1,
        window_id=1,
        evidences=[
            CandidateEvidenceV1(evidence_key="ev1", locator=loc, confidence=0.9),
        ],
        relations=[
            CandidateRelationV1(
                candidate_key="r1",
                relation_type="supports",
                subject=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="nope"),
                object=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="nope2"),
                confidence=0.5,
                evidence_keys=["ev1"],
            )
        ],
        provenance=make_provenance(),
    )
    with pytest.raises(ValueError, match="candidate_key missing"):
        validate_window_analysis_response_v1(resp)


def _version(payload_hash: str, **kw) -> NarrativeAssetVersionV1:
    data = dict(
        asset_version_id=1,
        asset_id=1,
        version_no=1,
        state=ArtifactState.candidate,
        payload={},
        payload_hash=payload_hash,
        source_run_id=1,
        source_window_ids=[],
        evidence_ids=[1],
        created_by="engine",
        created_at=utc_now(),
        is_current=True,
    )
    data.update(kw)
    return NarrativeAssetVersionV1(**data)


def test_21_confirmed_new_proposal_create_conflict() -> None:
    cur = _version(make_sha("a"), state=ArtifactState.confirmed)
    prop = _version(make_sha("b"), asset_version_id=2, version_no=2)
    assert (
        evaluate_engine_proposal_against_current_version(
            ArtifactState.confirmed, cur, prop
        )
        == EngineProposalDecision.create_conflict
    )


def test_22_candidate_identical_ignore() -> None:
    h = make_sha("same")
    cur = _version(h)
    prop = _version(h, asset_version_id=2, version_no=2)
    assert (
        evaluate_engine_proposal_against_current_version(ArtifactState.candidate, cur, prop)
        == EngineProposalDecision.ignore_identical
    )


def test_23_overview_available_without_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        BookOverviewClaimV1(
            claim_key="protagonist",
            availability=OverviewClaimAvailability.available,
            summary="hero",
            confidence=0.9,
            evidence_ids=[],
        )


def test_24_completed_overview_incomplete_claims() -> None:
    claims = [
        BookOverviewClaimV1(
            claim_key=k,  # type: ignore[arg-type]
            availability=OverviewClaimAvailability.insufficient_evidence,
            summary="insufficient evidence",
        )
        for k in BOOK_OVERVIEW_CLAIM_KEYS_V1
        if k != "key_events"
    ]
    with pytest.raises(ValidationError):
        BookOverviewResultV1(
            run_id=1,
            book_id=1,
            snapshot_id=1,
            mode=WholeBookMode.whole_book_native,
            result_origin=ResultOrigin.formal,
            status="completed",
            claims=claims,
            coverage=make_coverage(),
            input_usage=native_usage(),
            provenance=make_provenance(),
            created_at=utc_now(),
        )


def test_25_fixture_origin_explicit() -> None:
    run = make_run(result_origin=ResultOrigin.fixture)
    assert run.result_origin == ResultOrigin.fixture
    prov = make_provenance(result_origin=ResultOrigin.fixture, deterministic=True)
    assert prov.result_origin == ResultOrigin.fixture


def test_26_contract_version_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        make_run().model_validate(
            {**make_run().model_dump(mode="json"), "contract_version": "whole_book_contract_v0"}
        )


def test_27_json_round_trip() -> None:
    snap = make_snapshot()
    data = snap.model_dump(mode="json")
    again = snap.__class__.model_validate(data)
    assert again == snap


def test_28_schema_export_deterministic() -> None:
    a = build_wire_contract_schema()
    b = build_wire_contract_schema()
    assert canonical_json_bytes(a) == canonical_json_bytes(b)
    assert schema_sha256(a) == schema_sha256(b)


def test_29_persistence_mapping_doc_exists() -> None:
    root = Path(__file__).resolve().parents[3]
    path = root / "docs" / "whole-book" / "contracts" / "V1_PERSISTENCE_MAPPING.md"
    assert path.is_file(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    for col in (
        "Contract Object",
        "Contract Field",
        "Existing Model",
        "Existing Field",
        "Mapping Status",
        "Migration Required",
        "Notes",
    ):
        assert col in text
    for status in ("reuse", "adapter", "extend_later", "new_in_wb_0_4", "not_applicable"):
        assert status in text


def test_30_no_db_writes_from_validators() -> None:
    # Validators are pure; this test asserts no sqlalchemy Session usage markers.
    import app.narrative_core.contracts.whole_book_contract_v1.validators as v

    src = Path(v.__file__).read_text(encoding="utf-8")
    assert "Session" not in src
    assert "sqlalchemy" not in src
    assert validate_evidence_locator(_valid_locator("hello world"), "hello world") == EvidenceState.valid


def test_valid_window_response_crossrefs() -> None:
    loc = _valid_locator()
    resp = WholeBookWindowAnalysisResponseV1(
        run_id=1,
        snapshot_id=1,
        window_id=1,
        evidences=[CandidateEvidenceV1(evidence_key="ev1", locator=loc, confidence=0.8)],
        entities=[
            CandidateEntityV1(
                candidate_key="e1",
                entity_type="character",
                canonical_name="A",
                confidence=0.8,
                evidence_keys=["ev1"],
            )
        ],
        assets=[
            CandidateAssetV1(
                candidate_key="a1",
                asset_type="event",
                title="E",
                summary="happened",
                confidence=0.7,
                subject_entity_keys=["e1"],
                evidence_keys=["ev1"],
            )
        ],
        relations=[
            CandidateRelationV1(
                candidate_key="r1",
                relation_type="participates_in",
                subject=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="e1"),
                object=CandidateNarrativeRefV1(kind=NarrativeRefKind.asset, candidate_key="a1"),
                confidence=0.6,
                evidence_keys=["ev1"],
            )
        ],
        provenance=make_provenance(),
    )
    validate_window_analysis_response_v1(resp)
