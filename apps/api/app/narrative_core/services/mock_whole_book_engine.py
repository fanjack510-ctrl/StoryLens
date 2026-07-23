"""Mock WholeBook Analysis Engine (Phase 1C Agent G).

Implements the frozen Phase 1C-P Protocol with deterministic synthetic outputs.
No model calls, no real novel analysis, no canonical/lock writes.
All outputs are marked mock / synthetic / non-production.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from app.narrative_core.contracts.stage import (
    WholeBookStageContext,
    WholeBookStagePlan,
    WholeBookStageResult,
)
from app.narrative_core.contracts.whole_book_dto import (
    WholeBookAnalysisRequest,
    require_consistency_fields,
    validate_request_shape,
)
from app.narrative_core.contracts.whole_book_artifact import (
    WHOLE_BOOK_STAGE_ARTIFACT_TYPE,
    build_whole_book_stage_artifact_envelope,
)
from app.narrative_core.enums import (
    AssetType,
    CapabilityKey,
    OriginType,
    RelationType,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.whole_book_engine_adapters import (
    MOCK_NON_PRODUCTION_MARKER,
    MOCK_SOURCE_MARKER,
    MOCK_SYNTHETIC_MARKER,
    mock_source_fingerprint,
)
from app.narrative_core.services.whole_book_stage_plan import (
    build_whole_book_stage_plan,
    stage_definitions_to_run_stage_keys,
)

MOCK_ENGINE_ID = "mock_whole_book_v0"
MOCK_ENGINE_VERSION = "0.1.0-mock"

_FORBIDDEN_BODY_KEYS = frozenset(
    {
        "full_text",
        "fulltext",
        "book_text",
        "novel_text",
        "novel_body",
        "chapters_text",
        "paragraph_texts",
        "raw_book_content",
        "content_text",
    }
)

_STAGE_TOKEN_COST: dict[WholeBookStageKey, tuple[int, float]] = {
    WholeBookStageKey.BUILD_FULLTEXT_INDEX: (10, 0.0),
    WholeBookStageKey.RESOLVE_ENTITIES: (20, 0.0),
    WholeBookStageKey.ANALYZE_STRUCTURE: (30, 0.001),
    WholeBookStageKey.ANALYZE_STORYLINES: (40, 0.001),
    WholeBookStageKey.ANALYZE_CHARACTERS: (40, 0.001),
    WholeBookStageKey.ANALYZE_HOOKS: (35, 0.001),
    WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE: (45, 0.001),
    WholeBookStageKey.GENERATE_DIAGNOSTICS: (25, 0.0),
    WholeBookStageKey.VERIFY_EVIDENCE: (15, 0.0),
    WholeBookStageKey.PERSIST_NARRATIVE_ASSETS: (20, 0.0),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_ids(values: Sequence[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        iv = int(value)
        if iv in seen:
            continue
        seen.add(iv)
        out.append(iv)
    return tuple(out)


class MockWholeBookAnalysisEngine:
    """Full mock implementing WholeBookAnalysisEngine Protocol."""

    def __init__(
        self,
        *,
        snapshot_reader: Any | None = None,
        binding_resolver: Any | None = None,
        write_candidates: bool = True,
    ) -> None:
        self._snapshot_reader = snapshot_reader
        self._binding_resolver = binding_resolver
        self._write_candidates = write_candidates
        self._cancelled: set[tuple[int, str]] = set()
        self._paused: set[tuple[int, str]] = set()
        self._checkpoints: dict[tuple[int, str], dict[str, Any]] = {}

    @property
    def engine_id(self) -> str:
        return MOCK_ENGINE_ID

    @property
    def engine_version(self) -> str:
        return MOCK_ENGINE_VERSION

    def supported_modes(self) -> Sequence[WholeBookAnalysisMode]:
        return (WholeBookAnalysisMode.NATIVE, WholeBookAnalysisMode.ENHANCED)

    def supported_modules(self) -> Sequence[WholeBookModuleKey]:
        return tuple(WholeBookModuleKey)

    def validate_request(self, request: WholeBookAnalysisRequest) -> None:
        validate_request_shape(request)

        if request.run_id is None or int(request.run_id) <= 0:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                "run_id is required and must be positive",
            )
        # Fingerprint is mandatory once bindings/adapters are wired; pure
        # contract-stub calls (no snapshot/binding adapters) remain compatible.
        fingerprint = str(request.configuration_fingerprint or "").strip()
        if not fingerprint and (
            self._snapshot_reader is not None or self._binding_resolver is not None
        ):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                "configuration_fingerprint must be non-empty",
            )
        if request.capability_context.capability_key != CapabilityKey.WHOLE_BOOK_ANALYSIS:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                "capability_key must be whole_book_analysis",
            )
        if not request.capability_context.allowed:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                request.capability_context.display_message or "capability denied",
            )
        if request.analysis_mode not in self.supported_modes():
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
                f"unsupported analysis_mode: {request.analysis_mode}",
            )

        supported = set(self.supported_modules())
        for raw in request.requested_modules:
            module = (
                raw
                if isinstance(raw, WholeBookModuleKey)
                else WholeBookModuleKey(str(raw))
                if str(raw) in {m.value for m in WholeBookModuleKey}
                else None
            )
            if module is None or module not in supported:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED,
                    f"requested module not supported: {raw}",
                )

        self._assert_no_full_body(request)

        # Native never requires chapter analysis assets.
        # Enhanced may lack chapter assets — degrade with warning, do not fail.
        if request.analysis_mode == WholeBookAnalysisMode.ENHANCED:
            has_chapter_assets = bool(
                request.extra.get("has_chapter_analysis_assets", False)
            )
            if not has_chapter_assets:
                # Degrade coverage is recorded for orchestrator metrics only.
                request.extra.setdefault(
                    "enhanced_degraded",
                    True,
                )
                request.extra.setdefault(
                    "enhanced_degrade_reason",
                    "missing chapter analysis assets; continuing with native-like coverage",
                )

        if self._snapshot_reader is not None:
            self._snapshot_reader.require_completed_for_book(
                int(request.book_snapshot_id),
                int(request.book_id),
            )
        if self._binding_resolver is not None:
            self._binding_resolver.require_book(int(request.book_id))
            self._binding_resolver.validate_run_snapshot_consistency(
                run_id=int(request.run_id),
                book_id=int(request.book_id),
                book_snapshot_id=int(request.book_snapshot_id),
            )
        else:
            bound_book = request.extra.get("bound_book_id")
            bound_snapshot = request.extra.get("bound_snapshot_id")
            require_consistency_fields(
                run_id=request.run_id,
                book_id=request.book_id,
                book_snapshot_id=request.book_snapshot_id,
                bound_book_id=int(bound_book) if bound_book is not None else None,
                bound_snapshot_id=int(bound_snapshot) if bound_snapshot is not None else None,
            )

    def build_stage_plan(self, request: WholeBookAnalysisRequest) -> WholeBookStagePlan:
        self.validate_request(request)
        return build_whole_book_stage_plan(
            mode=request.analysis_mode,
            requested_modules=request.requested_modules,
            supported_modules=self.supported_modules(),
        )

    def plan_stage_keys(self, request: WholeBookAnalysisRequest) -> list[str]:
        plan = self.build_stage_plan(request)
        return stage_definitions_to_run_stage_keys(plan.stages)

    def execute_stage(self, context: WholeBookStageContext) -> WholeBookStageResult:
        return self._run_stage(context, resumable_only=False)

    def resume_stage(self, context: WholeBookStageContext) -> WholeBookStageResult:
        key = (int(context.run_id), str(context.stage_key))
        self._paused.discard(key)
        self._cancelled.discard(key)
        return self._run_stage(context, resumable_only=True)

    def cancel_stage(self, run_id: int, stage_key: WholeBookStageKey | str) -> None:
        key = (int(run_id), str(stage_key))
        self._cancelled.add(key)
        self._paused.discard(key)

    def pause_stage(self, run_id: int, stage_key: WholeBookStageKey | str) -> None:
        """Test helper — pause ≠ failed."""

        self._paused.add((int(run_id), str(stage_key)))

    def health_check(self) -> dict[str, Any]:
        modes = [m.value for m in self.supported_modes()]
        modules = [m.value for m in self.supported_modules()]
        return {
            "engine_id": MOCK_ENGINE_ID,
            "engine_version": MOCK_ENGINE_VERSION,
            "available": True,
            "healthy": True,  # Phase 1C-P contract compatibility
            "supported_modes": modes,
            "supported_modules": modules,
            "mock": True,
            "detail": (
                f"{MOCK_SOURCE_MARKER}/{MOCK_SYNTHETIC_MARKER}/"
                f"{MOCK_NON_PRODUCTION_MARKER}; no model calls"
            ),
            "checked_at": _utc_now_iso(),
            "production_ready": False,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _assert_no_full_body(self, request: WholeBookAnalysisRequest) -> None:
        for key in _FORBIDDEN_BODY_KEYS:
            if key in request.extra:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                    f"request must not include full novel body field: {key}",
                )
            if key in request.provider_policy or key in request.budget_context:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                    f"request must not include full novel body field: {key}",
                )

    def _run_stage(
        self,
        context: WholeBookStageContext,
        *,
        resumable_only: bool,
    ) -> WholeBookStageResult:
        if not context.capability_context.allowed:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                "capability denied",
            )

        stage_key = WholeBookStageKey(context.stage_key)
        run_key = (int(context.run_id), stage_key.value)

        token = context.cancellation_token
        if token is not None:
            token.raise_if_cancelled()
        if run_key in self._cancelled:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED,
                f"stage cancelled: {stage_key.value}",
            )
        if run_key in self._paused:
            checkpoint = self._make_checkpoint(
                context,
                status="paused",
                note="mock stage paused (not failed)",
            )
            self._checkpoints[run_key] = checkpoint
            return WholeBookStageResult(
                stage_key=stage_key,
                status=StageStatus.PAUSED,
                checkpoint=checkpoint,
                message="mock stage paused",
                metrics=self._base_metrics(stage_key, status="paused"),
            )

        if resumable_only and stage_key.value:
            # Resume continues from stored checkpoint when present.
            _ = context.checkpoint or self._checkpoints.get(run_key, {})

        budget = context.budget_guard
        tokens, cost = _STAGE_TOKEN_COST.get(stage_key, (10, 0.0))
        if budget is not None and not budget.check_budget(
            stage_key=stage_key.value, estimated_tokens=tokens
        ):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_BUDGET_DENIED,
                f"budget denied for stage {stage_key.value}",
            )

        artifact_ids: list[int] = []
        asset_ids: list[int] = []
        relation_ids: list[int] = []
        conflict_ids: list[int] = []
        warnings: list[str] = []

        if context.extra.get("enhanced_degraded"):
            warnings.append(str(context.extra.get("enhanced_degrade_reason") or "enhanced degraded"))

        # Persist stage only writes candidates; earlier stages stay synthetic.
        if (
            self._write_candidates
            and stage_key == WholeBookStageKey.PERSIST_NARRATIVE_ASSETS
            and context.asset_writer is not None
        ):
            asset_ids, relation_ids, conflict_ids = self._write_mock_candidates(context)

        if context.artifact_writer is not None:
            envelope = build_whole_book_stage_artifact_envelope(
                run_id=int(context.run_id),
                run_stage_id=context.run_stage_id,
                stage_key=stage_key.value,
                engine_id=MOCK_ENGINE_ID,
                engine_version=MOCK_ENGINE_VERSION,
                book_id=int(context.book_id),
                book_snapshot_id=int(context.book_snapshot_id),
                analysis_mode=(
                    context.analysis_mode.value
                    if hasattr(context.analysis_mode, "value")
                    else str(context.analysis_mode)
                ),
                status=StageStatus.COMPLETED.value,
                mock=True,
                synthetic=True,
                non_production=True,
                output_refs=(),
                created_asset_version_ids=tuple(asset_ids),
                created_relation_version_ids=tuple(relation_ids),
                conflict_ids=tuple(conflict_ids),
                checkpoint_summary={"status": "completed", "mock": True},
                warnings=tuple(warnings),
                metrics=self._base_metrics(stage_key, status="completed"),
            )
            artifact_id = context.artifact_writer.write_artifact(
                int(context.run_id),
                WHOLE_BOOK_STAGE_ARTIFACT_TYPE,
                envelope.to_payload(),
            )
            artifact_ids.append(int(artifact_id))

        if budget is not None:
            budget.record_spend(stage_key=stage_key.value, tokens=tokens, cost_usd=cost)

        if token is not None:
            token.raise_if_cancelled()
        if run_key in self._cancelled:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED,
                f"stage cancelled after work: {stage_key.value}",
            )

        checkpoint = self._make_checkpoint(
            context,
            status="completed",
            note="mock stage completed",
            extra={
                "token_usage": tokens,
                "cost": cost,
                "artifact_ids": artifact_ids,
                "asset_version_ids": asset_ids,
                "relation_version_ids": relation_ids,
            },
        )
        self._checkpoints[run_key] = checkpoint

        return WholeBookStageResult(
            stage_key=stage_key,
            status=StageStatus.COMPLETED,
            output_artifact_ids=_dedupe_ids(artifact_ids),
            created_asset_version_ids=_dedupe_ids(asset_ids),
            created_relation_version_ids=_dedupe_ids(relation_ids),
            conflict_ids=_dedupe_ids(conflict_ids),
            checkpoint=checkpoint,
            token_usage=tokens,
            cost=cost,
            warnings=tuple(warnings),
            message="mock stage completed (no model; synthetic/non-production)",
            metrics=self._base_metrics(stage_key, status="completed"),
        )

    def _write_mock_candidates(
        self, context: WholeBookStageContext
    ) -> tuple[list[int], list[int], list[int]]:
        asset_writer = context.asset_writer
        relation_writer = context.relation_writer
        if relation_writer is None:
            # Compatibility: older test fixtures may still stash via extra.
            relation_writer = context.extra.get("relation_writer")

        structure = asset_writer.write_asset_candidate(
            {
                "book_id": context.book_id,
                "run_id": context.run_id,
                "book_snapshot_id": context.book_snapshot_id,
                "asset_type": AssetType.STRUCTURE_STAGE.value,
                "title": "Mock Structure Stage",
                "summary": "mock/synthetic/non-production structure_stage candidate",
                "origin_type": OriginType.SYSTEM.value,
                "source_fingerprint": mock_source_fingerprint(
                    "structure_stage", context.run_id
                ),
                "identity_fingerprint": mock_source_fingerprint(
                    "structure", context.book_id, context.run_id
                ),
            }
        )
        structure_asset_id = getattr(asset_writer, "last_asset_id", None)
        storyline = asset_writer.write_asset_candidate(
            {
                "book_id": context.book_id,
                "run_id": context.run_id,
                "book_snapshot_id": context.book_snapshot_id,
                "asset_type": AssetType.STORYLINE.value,
                "title": "Mock Storyline",
                "summary": "mock/synthetic/non-production storyline candidate",
                "origin_type": OriginType.SYSTEM.value,
                "source_fingerprint": mock_source_fingerprint("storyline", context.run_id),
                "identity_fingerprint": mock_source_fingerprint(
                    "storyline", context.book_id, context.run_id
                ),
            }
        )
        storyline_asset_id = getattr(asset_writer, "last_asset_id", None)
        event = asset_writer.write_asset_candidate(
            {
                "book_id": context.book_id,
                "run_id": context.run_id,
                "book_snapshot_id": context.book_snapshot_id,
                "asset_type": AssetType.EVENT.value,
                "title": "Mock Event",
                "summary": "mock/synthetic/non-production event candidate",
                "origin_type": OriginType.SYSTEM.value,
                "source_fingerprint": mock_source_fingerprint("event", context.run_id),
                "identity_fingerprint": mock_source_fingerprint(
                    "event", context.book_id, context.run_id
                ),
            }
        )
        asset_ids = [int(structure), int(storyline), int(event)]
        relation_ids: list[int] = []
        conflict_ids: list[int] = []

        source_asset_id = context.extra.get("mock_source_asset_id", structure_asset_id)
        target_asset_id = context.extra.get("mock_target_asset_id", storyline_asset_id)
        if (
            relation_writer is not None
            and source_asset_id is not None
            and target_asset_id is not None
            and int(source_asset_id) != int(target_asset_id)
        ):
            rel_version_id = relation_writer.write_relation_candidate(
                {
                    "book_id": context.book_id,
                    "run_id": context.run_id,
                    "book_snapshot_id": context.book_snapshot_id,
                    "source_asset_id": int(source_asset_id),
                    "target_asset_id": int(target_asset_id),
                    "relation_type": RelationType.BELONGS_TO.value,
                    "summary": "mock/synthetic/non-production belongs_to",
                    "origin_type": OriginType.SYSTEM.value,
                    "source_fingerprint": mock_source_fingerprint(
                        "belongs_to", context.run_id
                    ),
                }
            )
            relation_ids.append(int(rel_version_id))

        sink = context.conflict_sink
        if sink is not None and context.extra.get("emit_mock_conflict"):
            from app.narrative_core.enums import ConflictRefType, ConflictType
            from app.narrative_core.services.conflict_service import ConflictCreateRequest

            conflict_id = sink.record_conflict(
                ConflictCreateRequest(
                    book_id=int(context.book_id),
                    conflict_type=ConflictType.CANDIDATE_CONTRADICTION.value,
                    left_ref_type=ConflictRefType.ASSET_VERSION.value,
                    left_ref_id=str(structure),
                    right_ref_type=ConflictRefType.ASSET_VERSION.value,
                    right_ref_id=str(storyline),
                    description="mock/synthetic candidate contradiction",
                    run_id=int(context.run_id),
                    book_snapshot_id=int(context.book_snapshot_id),
                )
            )
            conflict_ids.append(int(conflict_id))

        return asset_ids, relation_ids, conflict_ids

    def _make_checkpoint(
        self,
        context: WholeBookStageContext,
        *,
        status: str,
        note: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "schema": "narrative_run_stage_checkpoint",
            "version": "1",
            "status": status,
            "note": note,
            "engine_id": MOCK_ENGINE_ID,
            "engine_version": MOCK_ENGINE_VERSION,
            "stage_key": str(context.stage_key),
            "mock": True,
            "synthetic": True,
            "non_production": True,
            "checked_at": _utc_now_iso(),
        }
        if extra:
            payload.update(extra)
        # Preserve prior checkpoint keys when resuming.
        prior = dict(context.checkpoint or {})
        prior.update(payload)
        return prior

    def _base_metrics(self, stage_key: WholeBookStageKey, *, status: str) -> dict[str, Any]:
        return {
            "engine": MOCK_ENGINE_ID,
            "engine_version": MOCK_ENGINE_VERSION,
            "mock": True,
            "synthetic": True,
            "non_production": True,
            "stage_key": stage_key.value,
            "status": status,
        }


__all__ = [
    "MOCK_ENGINE_ID",
    "MOCK_ENGINE_VERSION",
    "MockWholeBookAnalysisEngine",
]
