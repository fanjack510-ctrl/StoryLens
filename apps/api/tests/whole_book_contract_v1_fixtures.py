"""Helpers for whole_book_contract_v1 tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.narrative_core.contracts.whole_book_contract_v1 import (
    AnalysisProvenanceV1,
    BookSnapshotMetadataV1,
    ResultOrigin,
    SnapshotParagraphV1,
    SnapshotStatus,
    WholeBookInputUsageV1,
    WholeBookMode,
    WholeBookRunStatus,
    WholeBookRunV1,
    WholeBookUnitStatus,
    WholeBookWindowCoverageV1,
    WholeBookWindowV1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex as _sha


def utc_now() -> datetime:
    return datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def make_sha(text: str = "x") -> str:
    return _sha(text)


def native_usage() -> WholeBookInputUsageV1:
    return WholeBookInputUsageV1(
        full_text_snapshot_used=True,
        chapter_analysis_asset_count=0,
        reader_journey_asset_count=0,
        confirmed_whole_book_asset_count=0,
    )


def enhanced_usage(*, chapter: int = 1, journey: int = 0, confirmed: int = 0) -> WholeBookInputUsageV1:
    return WholeBookInputUsageV1(
        full_text_snapshot_used=True,
        chapter_analysis_asset_count=chapter,
        reader_journey_asset_count=journey,
        confirmed_whole_book_asset_count=confirmed,
    )


def make_snapshot(**overrides) -> BookSnapshotMetadataV1:
    data = dict(
        snapshot_id=1,
        book_id=1,
        snapshot_version=1,
        status=SnapshotStatus.completed,
        content_hash=make_sha("book"),
        chapter_count=1,
        paragraph_count=1,
        character_count=5,
        created_at=utc_now(),
        completed_at=utc_now(),
    )
    data.update(overrides)
    return BookSnapshotMetadataV1(**data)


def make_provenance(**overrides) -> AnalysisProvenanceV1:
    data = dict(
        run_id=1,
        snapshot_id=1,
        window_ids=[],
        engine_id="wb-engine",
        engine_version="0.1.0",
        prompt_version="p1",
        provider_id="mock",
        model_name="mock-model",
        result_origin=ResultOrigin.formal,
        source_mode=WholeBookMode.whole_book_native,
        deterministic=False,
        config_hashes={"policy": make_sha("policy")},
        generated_at=utc_now(),
    )
    data.update(overrides)
    return AnalysisProvenanceV1(**data)


def make_run(**overrides) -> WholeBookRunV1:
    data = dict(
        run_id=1,
        book_id=1,
        snapshot_id=1,
        mode=WholeBookMode.whole_book_native,
        status=WholeBookRunStatus.running,
        current_stage_code="windowing",
        idempotency_key="idem-1",
        engine_id="wb-engine",
        engine_version="0.1.0",
        prompt_version="p1",
        result_origin=ResultOrigin.formal,
        input_usage=native_usage(),
        created_at=utc_now(),
        started_at=utc_now(),
    )
    data.update(overrides)
    return WholeBookRunV1(**data)


def make_paragraph(text: str = "hello", **overrides) -> SnapshotParagraphV1:
    data = dict(
        snapshot_paragraph_id=1,
        snapshot_id=1,
        snapshot_chapter_id=1,
        chapter_id=1,
        chapter_index=0,
        paragraph_index=0,
        global_paragraph_index=0,
        text=text,
        text_hash=make_sha(text),
        character_count=len(text),
    )
    data.update(overrides)
    return SnapshotParagraphV1(**data)


def make_window(**overrides) -> WholeBookWindowV1:
    data = dict(
        window_id=1,
        run_id=1,
        snapshot_id=1,
        window_index=0,
        first_global_paragraph_index=0,
        last_global_paragraph_index=0,
        chapter_start_index=0,
        chapter_end_index=0,
        paragraph_count=1,
        character_count=5,
        token_estimate=2,
        overlap_before_paragraphs=0,
        overlap_after_paragraphs=0,
        window_hash=make_sha("w0"),
        idempotency_key="win-idem-1",
        status=WholeBookUnitStatus.pending,
    )
    data.update(overrides)
    return WholeBookWindowV1(**data)


def make_coverage(**overrides) -> WholeBookWindowCoverageV1:
    data = dict(
        snapshot_id=1,
        run_id=1,
        total_paragraphs=1,
        covered_unique_paragraphs=1,
        duplicated_paragraphs=0,
        uncovered_paragraphs=0,
        coverage_ratio=1.0,
        order_valid=True,
        first_global_paragraph_index=0,
        last_global_paragraph_index=0,
    )
    data.update(overrides)
    return WholeBookWindowCoverageV1(**data)
