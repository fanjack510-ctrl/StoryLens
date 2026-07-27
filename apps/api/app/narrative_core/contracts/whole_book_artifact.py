"""WholeBook stage artifact envelope (Phase 1C Integration freeze).

Reuses analysis_artifacts — no dedicated table / migration.
Artifact stores refs + structured summary only (never full novel / evidence body).
Does not become a Narrative Asset and does not replace Asset/Relation/Evidence tables.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

WHOLE_BOOK_STAGE_ARTIFACT_TYPE = "whole_book_stage_result"
WHOLE_BOOK_STAGE_ARTIFACT_SCHEMA = "whole_book_stage_artifact"
WHOLE_BOOK_STAGE_ARTIFACT_VERSION = "1"


@dataclass(frozen=True, slots=True)
class WholeBookStageArtifactEnvelope:
    """Frozen payload written into AnalysisArtifact.payload_json."""

    schema: str
    version: str
    run_id: int
    run_stage_id: int | None
    stage_key: str
    engine_id: str
    engine_version: str
    book_id: int
    book_snapshot_id: int
    analysis_mode: str
    mock: bool
    synthetic: bool
    non_production: bool
    status: str
    output_refs: tuple[str, ...] = ()
    created_asset_version_ids: tuple[int, ...] = ()
    created_relation_version_ids: tuple[int, ...] = ()
    conflict_ids: tuple[int, ...] = ()
    checkpoint_summary: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_payload(self) -> dict[str, Any]:
        if not self.schema:
            raise ValueError("schema is required")
        if not self.version:
            raise ValueError("version is required")
        payload = asdict(self)
        # Ensure JSON-friendly lists
        payload["output_refs"] = list(self.output_refs)
        payload["created_asset_version_ids"] = list(self.created_asset_version_ids)
        payload["created_relation_version_ids"] = list(self.created_relation_version_ids)
        payload["conflict_ids"] = list(self.conflict_ids)
        payload["warnings"] = list(self.warnings)
        return payload


def build_whole_book_stage_artifact_envelope(
    *,
    run_id: int,
    run_stage_id: int | None,
    stage_key: str,
    engine_id: str,
    engine_version: str,
    book_id: int,
    book_snapshot_id: int,
    analysis_mode: str,
    status: str,
    mock: bool = True,
    synthetic: bool = True,
    non_production: bool = True,
    output_refs: tuple[str, ...] | list[str] = (),
    created_asset_version_ids: tuple[int, ...] | list[int] = (),
    created_relation_version_ids: tuple[int, ...] | list[int] = (),
    conflict_ids: tuple[int, ...] | list[int] = (),
    checkpoint_summary: dict[str, Any] | None = None,
    warnings: tuple[str, ...] | list[str] = (),
    metrics: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> WholeBookStageArtifactEnvelope:
    return WholeBookStageArtifactEnvelope(
        schema=WHOLE_BOOK_STAGE_ARTIFACT_SCHEMA,
        version=WHOLE_BOOK_STAGE_ARTIFACT_VERSION,
        run_id=int(run_id),
        run_stage_id=int(run_stage_id) if run_stage_id is not None else None,
        stage_key=str(stage_key),
        engine_id=str(engine_id),
        engine_version=str(engine_version),
        book_id=int(book_id),
        book_snapshot_id=int(book_snapshot_id),
        analysis_mode=str(analysis_mode),
        mock=bool(mock),
        synthetic=bool(synthetic),
        non_production=bool(non_production),
        status=str(status),
        output_refs=tuple(str(x) for x in output_refs),
        created_asset_version_ids=tuple(int(x) for x in created_asset_version_ids),
        created_relation_version_ids=tuple(int(x) for x in created_relation_version_ids),
        conflict_ids=tuple(int(x) for x in conflict_ids),
        checkpoint_summary=dict(checkpoint_summary or {}),
        warnings=tuple(str(x) for x in warnings),
        metrics=dict(metrics or {}),
        created_at=created_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
