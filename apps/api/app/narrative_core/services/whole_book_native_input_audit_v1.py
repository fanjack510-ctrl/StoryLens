"""Native whole-book input independence audit (WB-1.9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    BookSnapshot,
    NarrativeAsset,
    NarrativeAssetVersion,
    ReaderJourneyRun,
    WholeBookNativeInputAudit,
    WholeBookRun,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookMode
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run


@dataclass
class NativeInputAuditV1:
    run_id: int
    snapshot_id: int
    full_text_snapshot_used: bool
    chapter_analysis_asset_count: int
    reader_journey_asset_count: int
    chapter_aggregate_asset_count: int
    enhanced_asset_count: int
    audit_status: str
    created_at: str | None = None

    def contamination_counts(self) -> dict[str, int]:
        return {
            "chapter_analysis_asset_count": self.chapter_analysis_asset_count,
            "reader_journey_asset_count": self.reader_journey_asset_count,
            "chapter_aggregate_asset_count": self.chapter_aggregate_asset_count,
            "enhanced_asset_count": self.enhanced_asset_count,
        }

    def is_clean(self) -> bool:
        if not self.full_text_snapshot_used:
            return False
        return all(value == 0 for value in self.contamination_counts().values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "snapshot_id": self.snapshot_id,
            "full_text_snapshot_used": self.full_text_snapshot_used,
            **self.contamination_counts(),
            "audit_status": self.audit_status,
            "created_at": self.created_at,
        }


def _count_chapter_analysis_artifacts(session: Session, book_id: int) -> int:
    """Count chapter/scene analysis artifacts — native path must never load these."""
    return int(
        session.scalar(
            select(func.count(AnalysisArtifact.id))
            .join(AnalysisRun, AnalysisArtifact.run_id == AnalysisRun.id)
            .where(
                AnalysisRun.book_id == book_id,
                AnalysisRun.analysis_type.in_(("scene", "chapter", "scene_analysis")),
            )
        )
        or 0
    )


def _count_reader_journey_runs(session: Session, book_id: int) -> int:
    return int(
        session.scalar(select(func.count(ReaderJourneyRun.id)).where(ReaderJourneyRun.book_id == book_id))
        or 0
    )


def _count_chapter_aggregate_assets(session: Session, book_id: int) -> int:
    return int(
        session.scalar(
            select(func.count(NarrativeAssetVersion.id))
            .join(NarrativeAsset, NarrativeAssetVersion.asset_id == NarrativeAsset.id)
            .where(
                NarrativeAsset.book_id == book_id,
                NarrativeAssetVersion.asset_type.in_(("chapter_summary", "chapter_aggregate", "aggregate_insight")),
            )
        )
        or 0
    )


def _count_enhanced_assets(session: Session, book_id: int) -> int:
    return int(
        session.scalar(
            select(func.count(NarrativeAsset.id)).where(
                NarrativeAsset.book_id == book_id,
                NarrativeAsset.asset_key.like("enhanced:%"),
            )
        )
        or 0
    )


def compute_native_input_audit_v1(
    session: Session,
    run_id: int,
    *,
    loaded_usage: dict[str, int | bool] | None = None,
) -> NativeInputAuditV1:
    """Compute audit for native runs. Native repositories must not load non-snapshot inputs."""
    run = get_run(session, run_id)
    if run.mode != WholeBookMode.whole_book_native.value:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            "native input audit requires whole_book_native mode",
        )
    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"run {run_id} has no snapshot",
        )
    snapshot = session.get(BookSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.snapshot_status != "completed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_COMPLETED,
            f"snapshot not completed for run {run_id}",
        )

    if loaded_usage is None:
        chapter_count = 0
        rj_count = 0
        aggregate_count = 0
        enhanced_count = 0
        full_text_used = True
    else:
        chapter_count = int(loaded_usage.get("chapter_analysis_asset_count", 0))
        rj_count = int(loaded_usage.get("reader_journey_asset_count", 0))
        aggregate_count = int(loaded_usage.get("chapter_aggregate_asset_count", 0))
        enhanced_count = int(loaded_usage.get("enhanced_asset_count", 0))
        full_text_used = bool(loaded_usage.get("full_text_snapshot_used", True))

    audit = NativeInputAuditV1(
        run_id=run_id,
        snapshot_id=run.snapshot_id,
        full_text_snapshot_used=full_text_used,
        chapter_analysis_asset_count=chapter_count,
        reader_journey_asset_count=rj_count,
        chapter_aggregate_asset_count=aggregate_count,
        enhanced_asset_count=enhanced_count,
        audit_status="pass" if full_text_used and chapter_count == rj_count == aggregate_count == enhanced_count == 0 else "contaminated",
    )
    return audit


def assert_native_input_independence_v1(
    session: Session,
    run_id: int,
    *,
    loaded_usage: dict[str, int | bool] | None = None,
) -> NativeInputAuditV1:
    audit = compute_native_input_audit_v1(session, run_id, loaded_usage=loaded_usage)
    if not audit.is_clean():
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_NATIVE_INPUT_CONTAMINATED,
            "原生全书分析输入被污染：不得依赖单章分析、Reader Journey 或增强资产",
        )
    return audit


def persist_native_input_audit_v1(session: Session, audit: NativeInputAuditV1) -> WholeBookNativeInputAudit:
    existing = session.scalar(
        select(WholeBookNativeInputAudit).where(WholeBookNativeInputAudit.run_id == audit.run_id)
    )
    if existing is not None:
        return existing
    row = WholeBookNativeInputAudit(
        run_id=audit.run_id,
        snapshot_id=audit.snapshot_id,
        full_text_snapshot_used=audit.full_text_snapshot_used,
        chapter_analysis_asset_count=audit.chapter_analysis_asset_count,
        reader_journey_asset_count=audit.reader_journey_asset_count,
        chapter_aggregate_asset_count=audit.chapter_aggregate_asset_count,
        enhanced_asset_count=audit.enhanced_asset_count,
        audit_status=audit.audit_status,
        created_at=utc_now(),
    )
    session.add(row)
    session.flush()
    return row


def native_book_has_contamination_sources(session: Session, book_id: int) -> dict[str, int]:
    """Diagnostic counts of contamination sources present in DB (native must not load them)."""
    return {
        "chapter_analysis_asset_count": _count_chapter_analysis_artifacts(session, book_id),
        "reader_journey_asset_count": _count_reader_journey_runs(session, book_id),
        "chapter_aggregate_asset_count": _count_chapter_aggregate_assets(session, book_id),
        "enhanced_asset_count": _count_enhanced_assets(session, book_id),
    }
