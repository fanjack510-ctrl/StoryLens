"""Whole-book result index / module projection (Phase 1D Agent K).

Read-only projection over RunStage, Artifact, Asset, Relation, Evidence, Conflict.
Does not call models, mutate Narrative Assets, switch canonical, confirm, or resolve conflicts.
No new DB tables — in-memory / computed projection only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AnalysisArtifact,
    AnalysisConflict,
    AnalysisRun,
    AnalysisRunStage,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    NarrativeEntityAlias,
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    AssetLifecycleStatus,
    AssetType,
    ConflictSeverity,
    ConflictStatus,
    RelationLifecycleStatus,
    RelationType,
    ReviewStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.product_contract.enums import WholeBookModuleStatus
from app.narrative_core.product_contract.keys import (
    MODULE_STAGE_DEPENDENCIES,
    WHOLE_BOOK_MODULE_KEYS,
)
from app.narrative_core.product_contract.module_results import (
    MODULE_RESULT_DTO_BY_KEY,
    BasicTimelineResultDto,
    BookOverviewResultDto,
    CausalChainResultDto,
    CharacterArcsResultDto,
    CharactersResultDto,
    ChapterFunctionsResultDto,
    DiagnosticsResultDto,
    EvidenceRefLite,
    HooksPayoffsResultDto,
    RelationshipsResultDto,
    StorylinesResultDto,
    StructureStagesResultDto,
    TimelineItemDto,
    StructureStageItemDto,
    DiagnosticItemDto,
    assert_payload_keys_for_module,
)
from app.narrative_core.product_contract.result_envelope import (
    RESULT_ENVELOPE_SCHEMA,
    RESULT_ENVELOPE_VERSION,
    ConfidenceSummaryDto,
    ReviewSummaryDto,
    WholeBookResultEnvelope,
)
from app.narrative_core.services.whole_book_stage_plan import (
    ENGINE_MODULE_PLANNING_STAGES,
)

# ---------------------------------------------------------------------------
# Public mapping aliases (Engine planning vs Product result dependencies)
# ---------------------------------------------------------------------------

# Product result dependency mapping — authoritative for module status / Envelope.
PRODUCT_MODULE_STAGE_DEPENDENCIES: Mapping[
    WholeBookModuleKey, tuple[WholeBookStageKey, ...]
] = MODULE_STAGE_DEPENDENCIES

# Re-export Engine planning mapping for callers that need both sides documented.
# Values live in whole_book_stage_plan (Phase 1C); do not duplicate rows here.

ViewMode = Literal["canonical", "candidate"]

MAX_VISIBLE_ASSETS = 100
MAX_VISIBLE_RELATIONS = 250
MAX_PAYLOAD_ITEMS = 250
MAX_CHAPTER_FUNCTION_ITEMS = 1000

# Modules whose Envelope.payload is a list container of item DTOs.
_ITEM_COLLECTION_MODULES: frozenset[WholeBookModuleKey] = frozenset(
    {
        WholeBookModuleKey.CHAPTER_FUNCTIONS,
        WholeBookModuleKey.STORYLINES,
        WholeBookModuleKey.CHARACTERS,
        WholeBookModuleKey.CHARACTER_ARCS,
        WholeBookModuleKey.RELATIONSHIPS,
        WholeBookModuleKey.HOOKS_PAYOFFS,
        WholeBookModuleKey.CAUSAL_CHAIN,
    }
)

_CAUSAL_RELATION_TYPES: frozenset[str] = frozenset(
    {
        RelationType.CAUSES.value,
        RelationType.ENABLES.value,
        RelationType.BLOCKS.value,
        RelationType.ESCALATES.value,
        RelationType.RESOLVES.value,
        RelationType.PRECEDES.value,
    }
)

_HOOK_ASSET_TYPES: frozenset[str] = frozenset(
    {
        AssetType.HOOK.value,
        AssetType.CLUE.value,
        AssetType.FORESHADOWING.value,
        AssetType.PARTIAL_PAYOFF.value,
        AssetType.FINAL_PAYOFF.value,
        AssetType.REVEAL.value,
    }
)


@dataclass(frozen=True, slots=True)
class ModuleIndexEntry:
    module_key: WholeBookModuleKey
    module_status: WholeBookModuleStatus
    stale: bool
    partial: bool
    source_stage_keys: tuple[str, ...]
    evidence_count: int
    conflict_count: int
    available: bool


@dataclass(frozen=True, slots=True)
class WholeBookResultIndex:
    schema: str
    version: str
    run_id: int
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    generated_at: str
    requested_modules: tuple[str, ...]
    available_modules: tuple[str, ...]
    modules: tuple[ModuleIndexEntry, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionAssetRow:
    asset_id: int
    asset_key: str
    version_id: int
    asset_type: str
    title: str
    summary: str
    narrative_function: str
    attributes: dict[str, Any]
    confidence: float
    review_status: str
    is_canonical: bool
    is_locked: bool
    lifecycle_status: str
    stale: bool
    evidence_count: int
    chapter_range: tuple[int | None, int | None]
    entity_ids: tuple[int, ...]
    storyline_ids: tuple[int, ...]
    book_snapshot_id: int | None
    run_id: int | None


@dataclass(frozen=True, slots=True)
class ProjectionRelationRow:
    relation_id: int
    relation_key: str
    version_id: int
    relation_type: str
    source_asset_id: int
    target_asset_id: int
    confidence: float
    review_status: str
    is_canonical: bool
    is_locked: bool
    lifecycle_status: str
    stale: bool
    evidence_count: int
    attributes: dict[str, Any]
    book_snapshot_id: int | None
    run_id: int | None


@dataclass(frozen=True, slots=True)
class EvidenceIndexEntry:
    evidence_id: int
    evidence_type: str
    target_version_id: int
    book_snapshot_id: int
    evidence_role: str
    paragraph_content_hash: str
    # No full paragraph body — refs only.


@dataclass(frozen=True, slots=True)
class ConflictSummaryDto:
    total: int = 0
    open: int = 0
    blocking: int = 0
    warning: int = 0
    info: int = 0
    conflict_ids: tuple[int, ...] = ()


@dataclass
class _QueryCounter:
    """Optional repository/query call counter for N+1 boundary tests."""

    count: int = 0

    def tick(self, n: int = 1) -> None:
        self.count += n


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        loaded = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_id_list(attrs: dict[str, Any], key: str) -> tuple[int, ...]:
    raw = attrs.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return ()
    ids: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            ids.append(int(item.strip()))
    return tuple(sorted(set(ids)))


def _chapter_range_from_attrs(attrs: dict[str, Any]) -> tuple[int | None, int | None]:
    cr = attrs.get("chapter_range")
    if isinstance(cr, (list, tuple)) and len(cr) >= 2:
        a = int(cr[0]) if cr[0] is not None and str(cr[0]).isdigit() else None
        b = int(cr[1]) if cr[1] is not None and str(cr[1]).isdigit() else None
        return (a, b)
    start = attrs.get("start_chapter") or attrs.get("setup_chapter")
    end = attrs.get("end_chapter")
    def _as_int(v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        return None

    return (_as_int(start), _as_int(end))


def _dto_to_dict(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj) and not isinstance(obj, type):
        data = asdict(obj)
    elif isinstance(obj, dict):
        data = dict(obj)
    else:
        raise TypeError(f"unsupported dto type: {type(obj)!r}")

    def _normalize(value: Any) -> Any:
        if isinstance(value, tuple):
            return [_normalize(v) for v in value]
        if isinstance(value, list):
            return [_normalize(v) for v in value]
        if isinstance(value, dict):
            return {k: _normalize(v) for k, v in value.items()}
        return value

    return _normalize(data)


def empty_payload_for_module(module_key: WholeBookModuleKey) -> dict[str, Any]:
    """Legal empty module payload — never invents novel conclusions."""

    if module_key in _ITEM_COLLECTION_MODULES:
        return {"items": []}
    if module_key == WholeBookModuleKey.BOOK_OVERVIEW:
        return _dto_to_dict(
            BookOverviewResultDto(
                logline="",
                premise="",
                central_question="",
                primary_conflict="",
                protagonist_asset_id=None,
                major_storyline_ids=(),
                structure_summary="",
                ending_state="",
                evidence_refs=(),
                confidence=None,
            )
        )
    if module_key == WholeBookModuleKey.STRUCTURE_STAGES:
        return _dto_to_dict(
            StructureStagesResultDto(
                stages=(),
                turning_points=(),
                act_or_phase_labels=(),
                chapter_ranges=(),
                narrative_function="",
                evidence_refs=(),
                confidence=None,
            )
        )
    if module_key == WholeBookModuleKey.BASIC_TIMELINE:
        return _dto_to_dict(
            BasicTimelineResultDto(
                timeline_items=(),
                story_time=None,
                narrative_order=(),
                chapter_id=None,
                event_asset_ids=(),
                certainty="unknown",
                evidence_refs=(),
            )
        )
    if module_key == WholeBookModuleKey.DIAGNOSTICS:
        return _dto_to_dict(
            DiagnosticsResultDto(diagnostic_items=())
        )
    return {"items": []}


def validate_module_payload(module_key: WholeBookModuleKey, payload: dict[str, Any]) -> None:
    if module_key in _ITEM_COLLECTION_MODULES:
        if "items" not in payload or not isinstance(payload["items"], list):
            raise ValueError(f"{module_key.value} payload requires items: list")
        dto_cls = MODULE_RESULT_DTO_BY_KEY[module_key]
        required = getattr(dto_cls, "__dataclass_fields__", {})
        for idx, item in enumerate(payload["items"]):
            if not isinstance(item, dict):
                raise ValueError(f"{module_key.value} items[{idx}] must be object")
            missing = [name for name in required if name not in item]
            if missing:
                raise ValueError(
                    f"{module_key.value} items[{idx}] missing fields: {missing}"
                )
        return
    assert_payload_keys_for_module(module_key, payload)


def resolve_analysis_mode(run: AnalysisRun) -> WholeBookAnalysisMode:
    raw = getattr(run, "analysis_type", None) or getattr(run, "analysis_mode", None)
    if raw in (AnalysisType.WHOLE_BOOK_NATIVE.value, WholeBookAnalysisMode.NATIVE.value):
        return WholeBookAnalysisMode.NATIVE
    if raw in (AnalysisType.WHOLE_BOOK_ENHANCED.value, WholeBookAnalysisMode.ENHANCED.value):
        return WholeBookAnalysisMode.ENHANCED
    try:
        return WholeBookAnalysisMode.from_analysis_type(str(raw))
    except ValueError:
        return WholeBookAnalysisMode.NATIVE


def _extract_requested_modules_from_blob(blob: dict[str, Any]) -> tuple[WholeBookModuleKey, ...] | None:
    for key in ("requested_modules", "resolved_modules"):
        raw = blob.get(key)
        if raw is None and isinstance(blob.get("whole_book_request"), dict):
            raw = blob["whole_book_request"].get(key)
        if raw is None:
            continue
        if not isinstance(raw, (list, tuple)):
            continue
        modules: list[WholeBookModuleKey] = []
        for item in raw:
            try:
                modules.append(WholeBookModuleKey(str(item)))
            except ValueError:
                continue
        return tuple(dict.fromkeys(modules))
    return None


def infer_requested_modules(
    run: AnalysisRun,
    stages: Sequence[AnalysisRunStage],
) -> tuple[WholeBookModuleKey, ...]:
    """Resolve requested modules without schema changes.

    Priority:
    1) validated_output / raw_output JSON
    2) first stage checkpoint_json
    3) infer from Engine planning stages present on the run
    """

    for raw in (run.validated_output, run.raw_output):
        found = _extract_requested_modules_from_blob(_parse_json_object(raw))
        if found is not None:
            return found

    for stage in stages:
        found = _extract_requested_modules_from_blob(_parse_json_object(stage.checkpoint_json))
        if found is not None:
            return found

    planned = {str(s.stage_key) for s in stages}
    if not planned:
        return ()

    inferred: list[WholeBookModuleKey] = []
    for module, planning in ENGINE_MODULE_PLANNING_STAGES.items():
        if any(stage.value in planned for stage in planning):
            inferred.append(module)
    return tuple(inferred)


def aggregate_module_status(
    *,
    module_key: WholeBookModuleKey,
    requested: set[WholeBookModuleKey],
    stage_status: Mapping[str, StageStatus],
    has_usable_output: bool,
    stale: bool,
    blocking_conflict: bool,
) -> WholeBookModuleStatus:
    """Aggregate module status from many-to-many MODULE_STAGE_DEPENDENCIES."""

    if module_key not in requested:
        return WholeBookModuleStatus.NOT_REQUESTED

    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[module_key]
    statuses = [stage_status.get(dep.value) for dep in deps]
    present = [s for s in statuses if s is not None]
    missing = len(present) < len(deps)

    if blocking_conflict and not (
        present
        and all(s == StageStatus.COMPLETED for s in present)
        and not missing
        and has_usable_output
    ):
        # Blocking conflict gates incomplete modules; completed readable results stay readable.
        if missing or any(
            s in (StageStatus.PENDING, StageStatus.PAUSED, StageStatus.INTERRUPTED)
            for s in present
        ):
            return WholeBookModuleStatus.BLOCKED

    if any(s == StageStatus.RUNNING for s in present):
        return WholeBookModuleStatus.RUNNING

    failed = [s for s in present if s == StageStatus.FAILED]
    if failed:
        if has_usable_output:
            return WholeBookModuleStatus.PARTIAL
        return WholeBookModuleStatus.FAILED

    cancelled = [s for s in present if s == StageStatus.CANCELLED]
    if cancelled and not has_usable_output:
        return WholeBookModuleStatus.FAILED

    completed_like = {
        StageStatus.COMPLETED,
        StageStatus.SKIPPED,
    }
    if present and all(s in completed_like for s in present) and not missing:
        if stale:
            return WholeBookModuleStatus.STALE
        return WholeBookModuleStatus.COMPLETED

    if has_usable_output and any(s == StageStatus.COMPLETED for s in present):
        return WholeBookModuleStatus.PARTIAL

    if missing and any(s == StageStatus.COMPLETED for s in present):
        return WholeBookModuleStatus.PARTIAL if has_usable_output else WholeBookModuleStatus.BLOCKED

    if missing and not present:
        return WholeBookModuleStatus.BLOCKED

    if not present or all(s == StageStatus.PENDING for s in present):
        return WholeBookModuleStatus.PENDING

    if any(s in (StageStatus.PAUSED, StageStatus.INTERRUPTED) for s in present):
        return WholeBookModuleStatus.BLOCKED

    return WholeBookModuleStatus.PENDING


class WholeBookResultIndexService:
    """Read-only whole-book result index and module envelope projection."""

    def __init__(
        self,
        session: Session,
        *,
        query_counter: _QueryCounter | None = None,
        max_assets: int = MAX_VISIBLE_ASSETS,
        max_relations: int = MAX_VISIBLE_RELATIONS,
    ) -> None:
        self._session = session
        self._counter = query_counter or _QueryCounter()
        self._max_assets = int(max_assets)
        self._max_relations = int(max_relations)
        self._cache: dict[int, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_result_index(self, run_id: int) -> WholeBookResultIndex:
        ctx = self._load_run_context(int(run_id))
        entries: list[ModuleIndexEntry] = []
        available: list[str] = []
        for module in WHOLE_BOOK_MODULE_KEYS:
            status = ctx["module_status"][module]
            entry = ModuleIndexEntry(
                module_key=module,
                module_status=status,
                stale=bool(ctx["module_stale"][module]),
                partial=status == WholeBookModuleStatus.PARTIAL,
                source_stage_keys=tuple(
                    s.value for s in PRODUCT_MODULE_STAGE_DEPENDENCIES[module]
                ),
                evidence_count=int(ctx["module_evidence_count"].get(module, 0)),
                conflict_count=int(ctx["module_conflict_count"].get(module, 0)),
                available=status
                not in (
                    WholeBookModuleStatus.NOT_REQUESTED,
                    WholeBookModuleStatus.PENDING,
                ),
            )
            entries.append(entry)
            if entry.available or status in (
                WholeBookModuleStatus.COMPLETED,
                WholeBookModuleStatus.PARTIAL,
                WholeBookModuleStatus.STALE,
                WholeBookModuleStatus.FAILED,
                WholeBookModuleStatus.BLOCKED,
                WholeBookModuleStatus.RUNNING,
            ):
                if module in ctx["requested"]:
                    available.append(module.value)

        return WholeBookResultIndex(
            schema="whole_book_result_index",
            version="1",
            run_id=ctx["run"].id,
            book_id=int(ctx["run"].book_id),
            book_snapshot_id=int(ctx["run"].book_snapshot_id),
            analysis_mode=ctx["analysis_mode"],
            generated_at=_utc_now_iso(),
            requested_modules=tuple(m.value for m in ctx["requested"]),
            available_modules=tuple(available),
            modules=tuple(entries),
            warnings=tuple(ctx["warnings"]),
        )

    def list_available_modules(self, run_id: int) -> tuple[WholeBookModuleKey, ...]:
        index = self.get_result_index(run_id)
        return tuple(WholeBookModuleKey(m) for m in index.available_modules)

    def get_module_status(self, run_id: int, module_key: WholeBookModuleKey | str) -> WholeBookModuleStatus:
        module = self._normalize_module(module_key)
        ctx = self._load_run_context(int(run_id))
        return ctx["module_status"][module]

    def get_module_result(
        self,
        run_id: int,
        module_key: WholeBookModuleKey | str,
        *,
        view: ViewMode = "canonical",
    ) -> WholeBookResultEnvelope:
        module = self._normalize_module(module_key)
        ctx = self._load_run_context(int(run_id))
        return self._build_envelope(ctx, module, view=view)

    def refresh_projection(self, run_id: int) -> WholeBookResultIndex:
        """Drop in-memory cache and rebuild index (still read-only; no DB writes)."""
        self._cache.pop(int(run_id), None)
        return self.get_result_index(int(run_id))

    # ------------------------------------------------------------------
    # Pattern projection inputs (Agent L)
    # ------------------------------------------------------------------

    def get_canonical_assets_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionAssetRow, ...]:
        return self._load_assets(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
            view="canonical",
            limit=limit or self._max_assets,
        )

    def get_candidate_assets_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionAssetRow, ...]:
        return self._load_assets(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
            view="candidate",
            limit=limit or self._max_assets,
        )

    def get_canonical_relations_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionRelationRow, ...]:
        return self._load_relations(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
            view="canonical",
            limit=limit or self._max_relations,
        )

    def get_candidate_relations_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionRelationRow, ...]:
        return self._load_relations(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
            view="candidate",
            limit=limit or self._max_relations,
        )

    def get_evidence_index(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        asset_version_ids: Sequence[int] = (),
        relation_version_ids: Sequence[int] = (),
        limit: int = 500,
    ) -> tuple[EvidenceIndexEntry, ...]:
        """Lazy evidence index — hashes/roles only, never paragraph body text."""

        entries: list[EvidenceIndexEntry] = []
        snap = int(book_snapshot_id)
        if asset_version_ids:
            self._counter.tick()
            rows = self._session.scalars(
                select(NarrativeAssetEvidence)
                .where(
                    NarrativeAssetEvidence.book_snapshot_id == snap,
                    NarrativeAssetEvidence.asset_version_id.in_(
                        [int(x) for x in asset_version_ids]
                    ),
                )
                .limit(int(limit))
            ).all()
            for row in rows:
                entries.append(
                    EvidenceIndexEntry(
                        evidence_id=int(row.id),
                        evidence_type="asset_evidence",
                        target_version_id=int(row.asset_version_id),
                        book_snapshot_id=int(row.book_snapshot_id),
                        evidence_role=str(row.evidence_role),
                        paragraph_content_hash=str(row.paragraph_content_hash or ""),
                    )
                )
        if relation_version_ids and len(entries) < limit:
            self._counter.tick()
            rows = self._session.scalars(
                select(NarrativeRelationEvidence)
                .where(
                    NarrativeRelationEvidence.book_snapshot_id == snap,
                    NarrativeRelationEvidence.relation_version_id.in_(
                        [int(x) for x in relation_version_ids]
                    ),
                )
                .limit(int(limit) - len(entries))
            ).all()
            for row in rows:
                entries.append(
                    EvidenceIndexEntry(
                        evidence_id=int(row.id),
                        evidence_type="relation_evidence",
                        target_version_id=int(row.relation_version_id),
                        book_snapshot_id=int(row.book_snapshot_id),
                        evidence_role=str(row.evidence_role),
                        paragraph_content_hash=str(row.paragraph_content_hash or ""),
                    )
                )
        # book_id retained for API symmetry / future filters; snapshot isolates rows.
        del book_id
        return tuple(entries)

    def get_review_summary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
    ) -> ReviewSummaryDto:
        assets = self._load_assets(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
            view="candidate",
            limit=self._max_assets,
            include_rejected=True,
        )
        relations = self._load_relations(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
            view="candidate",
            limit=self._max_relations,
            include_rejected=True,
        )
        return self._review_summary_from_rows(assets, relations)

    def get_conflict_summary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
    ) -> ConflictSummaryDto:
        conflicts = self._load_conflicts(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            run_id=run_id,
        )
        return self._conflict_summary(conflicts)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _normalize_module(self, module_key: WholeBookModuleKey | str) -> WholeBookModuleKey:
        if isinstance(module_key, WholeBookModuleKey):
            return module_key
        try:
            return WholeBookModuleKey(str(module_key))
        except ValueError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED,
                f"unknown module: {module_key}",
            ) from exc

    def _require_book_scope_run(self, run_id: int) -> AnalysisRun:
        self._counter.tick()
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"run not found: {run_id}",
            )
        scope = getattr(run, "scope_type", None)
        if scope != AnalysisScopeType.BOOK.value:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                f"result projection requires book scope; got scope_type={scope!r}",
            )
        if run.book_id is None or run.book_snapshot_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
                "book_id and book_snapshot_id are required for result projection",
            )
        return run

    def _load_run_context(self, run_id: int) -> dict[str, Any]:
        cached = self._cache.get(run_id)
        if cached is not None:
            return cached

        run = self._require_book_scope_run(run_id)
        self._counter.tick()
        stages = list(
            self._session.scalars(
                select(AnalysisRunStage)
                .where(AnalysisRunStage.run_id == int(run_id))
                .order_by(AnalysisRunStage.stage_order.asc(), AnalysisRunStage.id.asc())
            ).all()
        )
        stage_status = {
            str(s.stage_key): StageStatus(s.status)
            for s in stages
            if s.status in {x.value for x in StageStatus}
        }
        # Fallback for unexpected free-form status strings.
        for s in stages:
            if s.stage_key not in stage_status:
                try:
                    stage_status[str(s.stage_key)] = StageStatus(str(s.status))
                except ValueError:
                    stage_status[str(s.stage_key)] = StageStatus.PENDING

        artifact_ids, artifact_payloads = self._load_stage_artifacts(stages)
        requested = set(infer_requested_modules(run, stages))
        analysis_mode = resolve_analysis_mode(run)

        assets_canonical = self._load_assets(
            book_id=int(run.book_id),
            book_snapshot_id=int(run.book_snapshot_id),
            run_id=int(run.id),
            view="canonical",
            limit=self._max_assets,
        )
        assets_candidate = self._load_assets(
            book_id=int(run.book_id),
            book_snapshot_id=int(run.book_snapshot_id),
            run_id=int(run.id),
            view="candidate",
            limit=self._max_assets,
        )
        relations_canonical = self._load_relations(
            book_id=int(run.book_id),
            book_snapshot_id=int(run.book_snapshot_id),
            run_id=int(run.id),
            view="canonical",
            limit=self._max_relations,
        )
        relations_candidate = self._load_relations(
            book_id=int(run.book_id),
            book_snapshot_id=int(run.book_snapshot_id),
            run_id=int(run.id),
            view="candidate",
            limit=self._max_relations,
        )
        conflicts = self._load_conflicts(
            book_id=int(run.book_id),
            book_snapshot_id=int(run.book_snapshot_id),
            run_id=int(run.id),
        )
        entities = self._load_entities(int(run.book_id))

        warnings: list[str] = []
        if not assets_canonical and assets_candidate:
            warnings.append("canonical_empty_using_candidate_summary")

        module_status: dict[WholeBookModuleKey, WholeBookModuleStatus] = {}
        module_stale: dict[WholeBookModuleKey, bool] = {}
        module_evidence: dict[WholeBookModuleKey, int] = {}
        module_conflicts: dict[WholeBookModuleKey, int] = {}

        blocking_open = any(
            c.severity == ConflictSeverity.BLOCKING.value
            and c.status == ConflictStatus.OPEN.value
            for c in conflicts
        )

        for module in WHOLE_BOOK_MODULE_KEYS:
            usable_assets = self._assets_for_module(module, assets_canonical) or self._assets_for_module(
                module, assets_candidate
            )
            usable_relations = self._relations_for_module(
                module, relations_canonical
            ) or self._relations_for_module(module, relations_candidate)
            has_output = bool(usable_assets or usable_relations or self._artifact_covers_module(module, artifact_payloads))
            stale = self._module_stale(module, usable_assets, usable_relations, stages)
            status = aggregate_module_status(
                module_key=module,
                requested=requested,
                stage_status=stage_status,
                has_usable_output=has_output,
                stale=stale,
                blocking_conflict=blocking_open,
            )
            module_status[module] = status
            module_stale[module] = stale
            module_evidence[module] = sum(a.evidence_count for a in usable_assets) + sum(
                r.evidence_count for r in usable_relations
            )
            module_conflicts[module] = len(conflicts) if module in requested else 0

        ctx = {
            "run": run,
            "stages": stages,
            "stage_status": stage_status,
            "requested": requested,
            "analysis_mode": analysis_mode,
            "artifact_ids": artifact_ids,
            "artifact_payloads": artifact_payloads,
            "assets_canonical": assets_canonical,
            "assets_candidate": assets_candidate,
            "relations_canonical": relations_canonical,
            "relations_candidate": relations_candidate,
            "conflicts": conflicts,
            "entities": entities,
            "module_status": module_status,
            "module_stale": module_stale,
            "module_evidence_count": module_evidence,
            "module_conflict_count": module_conflicts,
            "warnings": warnings,
            "query_count": self._counter.count,
        }
        self._cache[run_id] = ctx
        return ctx

    def _load_stage_artifacts(
        self, stages: Sequence[AnalysisRunStage]
    ) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
        ids = [int(s.output_artifact_id) for s in stages if s.output_artifact_id is not None]
        if not ids:
            return (), []
        self._counter.tick()
        rows = self._session.scalars(
            select(AnalysisArtifact).where(AnalysisArtifact.id.in_(ids))
        ).all()
        payloads: list[dict[str, Any]] = []
        id_strs: list[str] = []
        for row in rows:
            id_strs.append(str(row.id))
            payload = _parse_json_object(row.payload_json)
            payloads.append(payload)
        return tuple(id_strs), payloads

    def _load_conflicts(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None,
    ) -> list[AnalysisConflict]:
        self._counter.tick()
        stmt = select(AnalysisConflict).where(AnalysisConflict.book_id == int(book_id))
        rows = list(self._session.scalars(stmt.order_by(AnalysisConflict.id.asc())).all())
        filtered: list[AnalysisConflict] = []
        for row in rows:
            if row.book_snapshot_id is not None and int(row.book_snapshot_id) != int(
                book_snapshot_id
            ):
                continue
            if run_id is not None and row.run_id is not None and int(row.run_id) != int(run_id):
                continue
            filtered.append(row)
        return filtered

    def _load_entities(self, book_id: int) -> list[NarrativeEntity]:
        self._counter.tick()
        return list(
            self._session.scalars(
                select(NarrativeEntity)
                .where(NarrativeEntity.book_id == int(book_id))
                .options(selectinload(NarrativeEntity.aliases))
                .order_by(NarrativeEntity.id.asc())
                .limit(self._max_assets)
            ).all()
        )

    def _load_assets(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None,
        view: ViewMode,
        limit: int,
        include_rejected: bool = False,
    ) -> tuple[ProjectionAssetRow, ...]:
        self._counter.tick()
        stmt = (
            select(NarrativeAssetVersion)
            .join(NarrativeAsset, NarrativeAssetVersion.asset_id == NarrativeAsset.id)
            .where(NarrativeAsset.book_id == int(book_id))
            .options(
                selectinload(NarrativeAssetVersion.asset),
                selectinload(NarrativeAssetVersion.evidence),
            )
            .order_by(NarrativeAsset.id.asc(), NarrativeAssetVersion.id.desc())
        )
        if view == "canonical":
            stmt = stmt.where(NarrativeAssetVersion.is_canonical.is_(True))
        versions = list(self._session.scalars(stmt).all())

        # Evidence counts without loading paragraph bodies (relationship already counted).
        rows: list[ProjectionAssetRow] = []
        seen_assets: set[int] = set()
        for version in versions:
            asset = version.asset
            if asset is None:
                continue
            aid = int(asset.id)
            if aid in seen_assets and view == "candidate":
                # Prefer newest non-rejected candidate per asset.
                continue
            if version.book_snapshot_id is not None and int(version.book_snapshot_id) != int(
                book_snapshot_id
            ):
                continue
            if run_id is not None and version.run_id is not None and int(version.run_id) != int(
                run_id
            ):
                # Allow book-level canonical without run_id; skip other-run candidates.
                if view == "candidate":
                    continue
            review = str(version.review_status)
            if review == ReviewStatus.REJECTED.value and not include_rejected:
                continue
            if view == "candidate" and version.is_canonical and review == ReviewStatus.CONFIRMED.value:
                # Candidate view still may include non-canonical only when explicit;
                # keep confirmed canonical out of pure candidate listing.
                if not include_rejected:
                    # include as candidate only if not canonical — skip canonical here.
                    continue
            attrs = _parse_json_object(version.attributes_json)
            evidence = list(version.evidence or [])
            # Snapshot isolation for evidence counts.
            evidence = [
                e
                for e in evidence
                if int(e.book_snapshot_id) == int(book_snapshot_id)
            ]
            stale = (
                str(asset.lifecycle_status) == AssetLifecycleStatus.STALE.value
                or asset.stale_at is not None
            )
            rows.append(
                ProjectionAssetRow(
                    asset_id=aid,
                    asset_key=str(asset.asset_key),
                    version_id=int(version.id),
                    asset_type=str(version.asset_type),
                    title=str(version.title or ""),
                    summary=str(version.summary or ""),
                    narrative_function=str(version.narrative_function or ""),
                    attributes=attrs,
                    confidence=float(version.confidence or 0.0),
                    review_status=review,
                    is_canonical=bool(version.is_canonical),
                    is_locked=bool(asset.is_locked),
                    lifecycle_status=str(asset.lifecycle_status),
                    stale=stale,
                    evidence_count=len(evidence),
                    chapter_range=_chapter_range_from_attrs(attrs),
                    entity_ids=_parse_id_list(attrs, "entity_ids"),
                    storyline_ids=_parse_id_list(attrs, "storyline_ids"),
                    book_snapshot_id=(
                        None
                        if version.book_snapshot_id is None
                        else int(version.book_snapshot_id)
                    ),
                    run_id=None if version.run_id is None else int(version.run_id),
                )
            )
            seen_assets.add(aid)
            if len(rows) >= int(limit):
                break
        return tuple(rows)

    def _load_relations(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None,
        view: ViewMode,
        limit: int,
        include_rejected: bool = False,
    ) -> tuple[ProjectionRelationRow, ...]:
        self._counter.tick()
        stmt = (
            select(NarrativeRelationVersion)
            .join(NarrativeRelation, NarrativeRelationVersion.relation_id == NarrativeRelation.id)
            .where(NarrativeRelation.book_id == int(book_id))
            .options(
                selectinload(NarrativeRelationVersion.relation),
                selectinload(NarrativeRelationVersion.evidence),
            )
            .order_by(NarrativeRelation.id.asc(), NarrativeRelationVersion.id.desc())
        )
        if view == "canonical":
            stmt = stmt.where(NarrativeRelationVersion.is_canonical.is_(True))
        versions = list(self._session.scalars(stmt).all())

        rows: list[ProjectionRelationRow] = []
        seen: set[int] = set()
        for version in versions:
            relation = version.relation
            if relation is None:
                continue
            rid = int(relation.id)
            if rid in seen and view == "candidate":
                continue
            if version.book_snapshot_id is not None and int(version.book_snapshot_id) != int(
                book_snapshot_id
            ):
                continue
            if (
                run_id is not None
                and version.run_id is not None
                and int(version.run_id) != int(run_id)
                and view == "candidate"
            ):
                continue
            review = str(version.review_status)
            if review == ReviewStatus.REJECTED.value and not include_rejected:
                continue
            if view == "candidate" and version.is_canonical:
                continue
            attrs = _parse_json_object(getattr(version, "attributes_json", None) or "{}")
            evidence = [
                e
                for e in list(version.evidence or [])
                if int(e.book_snapshot_id) == int(book_snapshot_id)
            ]
            stale = str(relation.lifecycle_status) == RelationLifecycleStatus.STALE.value
            rows.append(
                ProjectionRelationRow(
                    relation_id=rid,
                    relation_key=str(relation.relation_key),
                    version_id=int(version.id),
                    relation_type=str(version.relation_type),
                    source_asset_id=int(relation.source_asset_id),
                    target_asset_id=int(relation.target_asset_id),
                    confidence=float(version.confidence or 0.0),
                    review_status=review,
                    is_canonical=bool(version.is_canonical),
                    is_locked=bool(relation.is_locked),
                    lifecycle_status=str(relation.lifecycle_status),
                    stale=stale,
                    evidence_count=len(evidence),
                    attributes=attrs,
                    book_snapshot_id=(
                        None
                        if version.book_snapshot_id is None
                        else int(version.book_snapshot_id)
                    ),
                    run_id=None if version.run_id is None else int(version.run_id),
                )
            )
            seen.add(rid)
            if len(rows) >= int(limit):
                break
        return tuple(rows)

    def _assets_for_module(
        self, module: WholeBookModuleKey, assets: Sequence[ProjectionAssetRow]
    ) -> tuple[ProjectionAssetRow, ...]:
        type_map: dict[WholeBookModuleKey, frozenset[str]] = {
            WholeBookModuleKey.STRUCTURE_STAGES: frozenset({AssetType.STRUCTURE_STAGE.value}),
            WholeBookModuleKey.CHAPTER_FUNCTIONS: frozenset({AssetType.CHAPTER_FUNCTION.value}),
            WholeBookModuleKey.STORYLINES: frozenset({AssetType.STORYLINE.value}),
            WholeBookModuleKey.CHARACTER_ARCS: frozenset({AssetType.CHARACTER_ARC_STAGE.value}),
            WholeBookModuleKey.HOOKS_PAYOFFS: _HOOK_ASSET_TYPES,
            WholeBookModuleKey.BASIC_TIMELINE: frozenset({AssetType.EVENT.value}),
            WholeBookModuleKey.DIAGNOSTICS: frozenset({AssetType.DIAGNOSIS_INPUT.value}),
            WholeBookModuleKey.BOOK_OVERVIEW: frozenset(
                {
                    AssetType.STORYLINE.value,
                    AssetType.STRUCTURE_STAGE.value,
                    AssetType.CONFLICT.value,
                    AssetType.EVENT.value,
                }
            ),
            WholeBookModuleKey.CHARACTERS: frozenset(
                {
                    AssetType.GOAL.value,
                    AssetType.CONFLICT.value,
                    AssetType.CHOICE.value,
                    AssetType.CONSEQUENCE.value,
                    AssetType.CHARACTER_ARC_STAGE.value,
                }
            ),
            WholeBookModuleKey.RELATIONSHIPS: frozenset(),
            WholeBookModuleKey.CAUSAL_CHAIN: frozenset(),
        }
        allowed = type_map.get(module, frozenset())
        if not allowed:
            return ()
        return tuple(a for a in assets if a.asset_type in allowed)

    def _relations_for_module(
        self, module: WholeBookModuleKey, relations: Sequence[ProjectionRelationRow]
    ) -> tuple[ProjectionRelationRow, ...]:
        if module == WholeBookModuleKey.CAUSAL_CHAIN:
            return tuple(r for r in relations if r.relation_type in _CAUSAL_RELATION_TYPES)
        if module == WholeBookModuleKey.RELATIONSHIPS:
            return tuple(
                r
                for r in relations
                if r.relation_type
                in {
                    RelationType.CHANGES_RELATIONSHIP.value,
                    RelationType.BELONGS_TO.value,
                    RelationType.PARALLELS.value,
                }
            )
        if module == WholeBookModuleKey.HOOKS_PAYOFFS:
            return tuple(
                r
                for r in relations
                if r.relation_type
                in {RelationType.PAYS_OFF.value, RelationType.FORESHADOWS.value}
            )
        if module == WholeBookModuleKey.STORYLINES:
            return tuple(
                r
                for r in relations
                if r.relation_type
                in {RelationType.BELONGS_TO.value, RelationType.ADVANCES.value}
            )
        return ()

    def _artifact_covers_module(
        self, module: WholeBookModuleKey, payloads: Sequence[dict[str, Any]]
    ) -> bool:
        key = module.value
        for payload in payloads:
            produced = payload.get("checkpoint_summary", {}).get("produced_module_keys")
            if isinstance(produced, list) and key in produced:
                return True
            refs = payload.get("output_refs")
            if isinstance(refs, list) and any(key in str(r) for r in refs):
                return True
        return False

    def _module_stale(
        self,
        module: WholeBookModuleKey,
        assets: Sequence[ProjectionAssetRow],
        relations: Sequence[ProjectionRelationRow],
        stages: Sequence[AnalysisRunStage],
    ) -> bool:
        if any(a.stale for a in assets) or any(r.stale for r in relations):
            return True
        # Stage-level stale hint via checkpoint.
        deps = {s.value for s in PRODUCT_MODULE_STAGE_DEPENDENCIES[module]}
        for stage in stages:
            if stage.stage_key not in deps:
                continue
            blob = _parse_json_object(stage.checkpoint_json)
            if blob.get("stale") is True:
                return True
        return False

    def _review_summary_from_rows(
        self,
        assets: Sequence[ProjectionAssetRow],
        relations: Sequence[ProjectionRelationRow],
    ) -> ReviewSummaryDto:
        statuses = [a.review_status for a in assets] + [r.review_status for r in relations]
        locked = sum(1 for a in assets if a.is_locked) + sum(1 for r in relations if r.is_locked)
        return ReviewSummaryDto(
            candidate_count=sum(1 for s in statuses if s == ReviewStatus.CANDIDATE.value),
            confirmed_count=sum(1 for s in statuses if s == ReviewStatus.CONFIRMED.value),
            corrected_count=sum(1 for s in statuses if s == ReviewStatus.CORRECTED.value),
            rejected_count=sum(1 for s in statuses if s == ReviewStatus.REJECTED.value),
            locked_count=locked,
            conflict_count=0,
        )

    def _conflict_summary(self, conflicts: Sequence[AnalysisConflict]) -> ConflictSummaryDto:
        open_rows = [c for c in conflicts if c.status == ConflictStatus.OPEN.value]
        return ConflictSummaryDto(
            total=len(conflicts),
            open=len(open_rows),
            blocking=sum(1 for c in open_rows if c.severity == ConflictSeverity.BLOCKING.value),
            warning=sum(1 for c in open_rows if c.severity == ConflictSeverity.WARNING.value),
            info=sum(1 for c in open_rows if c.severity == ConflictSeverity.INFO.value),
            conflict_ids=tuple(int(c.id) for c in conflicts),
        )

    def _confidence_summary(
        self,
        assets: Sequence[ProjectionAssetRow],
        relations: Sequence[ProjectionRelationRow],
    ) -> ConfidenceSummaryDto:
        values = [a.confidence for a in assets] + [r.confidence for r in relations]
        if not values:
            return ConfidenceSummaryDto()
        return ConfidenceSummaryDto(
            mean=sum(values) / len(values),
            min=min(values),
            max=max(values),
            labeled_counts={"scored": len(values)},
        )

    def _select_view_rows(
        self, ctx: dict[str, Any], *, view: ViewMode
    ) -> tuple[tuple[ProjectionAssetRow, ...], tuple[ProjectionRelationRow, ...], bool]:
        """Default canonical; candidate must be explicit. Fallback marks candidate_summary."""

        if view == "candidate":
            return ctx["assets_candidate"], ctx["relations_candidate"], True
        assets = ctx["assets_canonical"]
        relations = ctx["relations_canonical"]
        used_candidate = False
        if not assets and ctx["assets_candidate"]:
            assets = ctx["assets_candidate"]
            used_candidate = True
        if not relations and ctx["relations_candidate"]:
            relations = ctx["relations_candidate"]
            used_candidate = True
        return assets, relations, used_candidate

    def _build_envelope(
        self,
        ctx: dict[str, Any],
        module: WholeBookModuleKey,
        *,
        view: ViewMode,
    ) -> WholeBookResultEnvelope:
        run: AnalysisRun = ctx["run"]
        status = ctx["module_status"][module]
        assets_all, relations_all, used_candidate = self._select_view_rows(ctx, view=view)
        assets = self._assets_for_module(module, assets_all)
        relations = self._relations_for_module(module, relations_all)
        # Characters also need entities even when asset types empty.
        entities: list[NarrativeEntity] = ctx["entities"]

        payload = self._project_module_payload(
            module,
            assets=assets,
            relations=relations,
            entities=entities,
            used_candidate=used_candidate or view == "candidate",
        )
        validate_module_payload(module, payload)

        review = self._review_summary_from_rows(assets, relations)
        conflicts = ctx["conflicts"]
        conflict_summary = self._conflict_summary(conflicts)
        review = ReviewSummaryDto(
            candidate_count=review.candidate_count,
            confirmed_count=review.confirmed_count,
            corrected_count=review.corrected_count,
            rejected_count=review.rejected_count,
            locked_count=review.locked_count,
            conflict_count=conflict_summary.open,
        )

        warnings: list[str] = list(ctx["warnings"])
        if used_candidate and view == "canonical":
            warnings.append("payload_from_candidate_summary")
        if view == "candidate":
            warnings.append("explicit_candidate_view")

        stale = bool(ctx["module_stale"][module])
        partial = status == WholeBookModuleStatus.PARTIAL

        return WholeBookResultEnvelope(
            schema=RESULT_ENVELOPE_SCHEMA,
            version=RESULT_ENVELOPE_VERSION,
            run_id=int(run.id),
            book_id=int(run.book_id),
            book_snapshot_id=int(run.book_snapshot_id),
            analysis_mode=ctx["analysis_mode"],
            module_key=module,
            module_status=status,
            generated_at=_utc_now_iso(),
            source_stage_keys=tuple(
                s.value for s in PRODUCT_MODULE_STAGE_DEPENDENCIES[module]
            ),
            source_artifact_ids=tuple(ctx["artifact_ids"]),
            asset_ids=tuple(a.asset_id for a in assets),
            asset_version_ids=tuple(a.version_id for a in assets),
            relation_ids=tuple(r.relation_id for r in relations),
            relation_version_ids=tuple(r.version_id for r in relations),
            conflict_ids=conflict_summary.conflict_ids,
            evidence_count=sum(a.evidence_count for a in assets)
            + sum(r.evidence_count for r in relations),
            confidence_summary=self._confidence_summary(assets, relations),
            review_summary=review,
            stale=stale,
            partial=partial,
            warnings=tuple(warnings),
            payload=payload,
        )

    def _evidence_refs_from_assets(
        self, assets: Sequence[ProjectionAssetRow]
    ) -> tuple[EvidenceRefLite, ...]:
        # Refs only — ids are version-scoped placeholders until lazy evidence fetch.
        refs: list[EvidenceRefLite] = []
        for asset in assets:
            if asset.evidence_count <= 0:
                continue
            refs.append(
                EvidenceRefLite(
                    evidence_id=f"asset_version:{asset.version_id}",
                    evidence_role="support",
                )
            )
            if len(refs) >= 50:
                break
        return tuple(refs)

    def _project_module_payload(
        self,
        module: WholeBookModuleKey,
        *,
        assets: Sequence[ProjectionAssetRow],
        relations: Sequence[ProjectionRelationRow],
        entities: Sequence[NarrativeEntity],
        used_candidate: bool,
    ) -> dict[str, Any]:
        if module == WholeBookModuleKey.BOOK_OVERVIEW:
            storylines = [a for a in assets if a.asset_type == AssetType.STORYLINE.value]
            conflicts = [a for a in assets if a.asset_type == AssetType.CONFLICT.value]
            dto = BookOverviewResultDto(
                logline="",
                premise="",
                central_question="",
                primary_conflict=conflicts[0].title if conflicts else "",
                protagonist_asset_id=None,
                major_storyline_ids=tuple(a.asset_id for a in storylines[:10]),
                structure_summary="",
                ending_state="",
                evidence_refs=self._evidence_refs_from_assets(assets),
                confidence=(
                    sum(a.confidence for a in assets) / len(assets) if assets else None
                ),
            )
            payload = _dto_to_dict(dto)
            if used_candidate:
                payload["view"] = "candidate_summary"
            return payload

        if module == WholeBookModuleKey.STRUCTURE_STAGES:
            stages = []
            ranges = []
            for idx, asset in enumerate(assets[:MAX_PAYLOAD_ITEMS]):
                stages.append(
                    StructureStageItemDto(
                        stage_id=str(asset.asset_id),
                        label=asset.title or asset.asset_key,
                        chapter_range=asset.chapter_range,
                        narrative_function=asset.narrative_function,
                        order=idx,
                    )
                )
                ranges.append(asset.chapter_range)
            dto = StructureStagesResultDto(
                stages=tuple(stages),
                turning_points=(),
                act_or_phase_labels=tuple(s.label for s in stages),
                chapter_ranges=tuple(ranges),
                narrative_function="",
                evidence_refs=self._evidence_refs_from_assets(assets),
                confidence=(
                    sum(a.confidence for a in assets) / len(assets) if assets else None
                ),
            )
            return _dto_to_dict(dto)

        if module == WholeBookModuleKey.CHAPTER_FUNCTIONS:
            items = []
            for asset in assets[:MAX_CHAPTER_FUNCTION_ITEMS]:
                order = asset.chapter_range[0] or 0
                items.append(
                    _dto_to_dict(
                        ChapterFunctionsResultDto(
                            chapter_id=int(asset.attributes.get("chapter_id") or order or asset.asset_id),
                            chapter_order=int(asset.attributes.get("chapter_order") or order or 0),
                            function_labels=(
                                tuple(asset.attributes.get("function_labels") or ())
                                if isinstance(asset.attributes.get("function_labels"), list)
                                else (
                                    (asset.narrative_function,)
                                    if asset.narrative_function
                                    else ()
                                )
                            ),
                            primary_storyline_ids=asset.storyline_ids,
                            character_focus_ids=asset.entity_ids,
                            hook_ids=_parse_id_list(asset.attributes, "hook_ids"),
                            payoff_ids=_parse_id_list(asset.attributes, "payoff_ids"),
                            change_summary=asset.summary,
                            evidence_refs=self._evidence_refs_from_assets((asset,)),
                        )
                    )
                )
            return {"items": items}

        if module == WholeBookModuleKey.STORYLINES:
            items = []
            for asset in assets[:MAX_PAYLOAD_ITEMS]:
                items.append(
                    _dto_to_dict(
                        StorylinesResultDto(
                            storyline_asset_id=asset.asset_id,
                            title=asset.title,
                            summary=asset.summary,
                            storyline_type=str(
                                asset.attributes.get("storyline_type") or "unknown"
                            ),
                            chapter_range=asset.chapter_range,
                            key_event_ids=_parse_id_list(asset.attributes, "key_event_ids"),
                            involved_entity_ids=asset.entity_ids,
                            relation_ids=tuple(
                                r.relation_id
                                for r in relations
                                if r.source_asset_id == asset.asset_id
                                or r.target_asset_id == asset.asset_id
                            ),
                            status=asset.lifecycle_status,
                            evidence_refs=self._evidence_refs_from_assets((asset,)),
                        )
                    )
                )
            return {"items": items}

        if module in (WholeBookModuleKey.CHARACTERS, WholeBookModuleKey.CHARACTER_ARCS):
            items = []
            # Prefer entity projection; attach related asset ids by type.
            goals = {a.asset_id: a for a in assets if a.asset_type == AssetType.GOAL.value}
            conflicts_a = {
                a.asset_id: a for a in assets if a.asset_type == AssetType.CONFLICT.value
            }
            choices = {a.asset_id: a for a in assets if a.asset_type == AssetType.CHOICE.value}
            consequences = {
                a.asset_id: a for a in assets if a.asset_type == AssetType.CONSEQUENCE.value
            }
            arcs = {
                a.asset_id: a
                for a in assets
                if a.asset_type == AssetType.CHARACTER_ARC_STAGE.value
            }
            source_entities = list(entities)[:MAX_PAYLOAD_ITEMS]
            if not source_entities and arcs:
                # Fall back to arc assets without inventing names beyond stored title.
                for asset in list(arcs.values())[:MAX_PAYLOAD_ITEMS]:
                    cls = (
                        CharacterArcsResultDto
                        if module == WholeBookModuleKey.CHARACTER_ARCS
                        else CharactersResultDto
                    )
                    items.append(
                        _dto_to_dict(
                            cls(
                                entity_id=asset.entity_ids[0] if asset.entity_ids else asset.asset_id,
                                canonical_name=asset.title,
                                aliases=(),
                                role=str(asset.attributes.get("role") or ""),
                                goal_asset_ids=(),
                                conflict_asset_ids=(),
                                choice_asset_ids=(),
                                consequence_asset_ids=(),
                                arc_stage_ids=(asset.asset_id,),
                                chapter_range=asset.chapter_range,
                                evidence_refs=self._evidence_refs_from_assets((asset,)),
                            )
                        )
                    )
                return {"items": items}

            for entity in source_entities:
                aliases = tuple(
                    str(a.alias_text)
                    for a in (entity.aliases or [])
                    if str(getattr(a, "review_status", "candidate"))
                    != ReviewStatus.REJECTED.value
                )
                eid = int(entity.id)
                related = [a for a in assets if eid in a.entity_ids]
                cls = (
                    CharacterArcsResultDto
                    if module == WholeBookModuleKey.CHARACTER_ARCS
                    else CharactersResultDto
                )
                items.append(
                    _dto_to_dict(
                        cls(
                            entity_id=eid,
                            canonical_name=str(entity.canonical_name),
                            aliases=aliases,
                            role=str(getattr(entity, "entity_type", "") or ""),
                            goal_asset_ids=tuple(
                                a.asset_id for a in related if a.asset_id in goals
                            ),
                            conflict_asset_ids=tuple(
                                a.asset_id for a in related if a.asset_id in conflicts_a
                            ),
                            choice_asset_ids=tuple(
                                a.asset_id for a in related if a.asset_id in choices
                            ),
                            consequence_asset_ids=tuple(
                                a.asset_id for a in related if a.asset_id in consequences
                            ),
                            arc_stage_ids=tuple(
                                a.asset_id for a in related if a.asset_id in arcs
                            ),
                            chapter_range=(None, None),
                            evidence_refs=self._evidence_refs_from_assets(tuple(related)),
                        )
                    )
                )
            return {"items": items}

        if module == WholeBookModuleKey.RELATIONSHIPS:
            items = []
            for rel in relations[:MAX_PAYLOAD_ITEMS]:
                items.append(
                    _dto_to_dict(
                        RelationshipsResultDto(
                            source_entity_id=int(
                                rel.attributes.get("source_entity_id") or rel.source_asset_id
                            ),
                            target_entity_id=int(
                                rel.attributes.get("target_entity_id") or rel.target_asset_id
                            ),
                            relationship_stage=str(
                                rel.attributes.get("relationship_stage") or rel.relation_type
                            ),
                            relation_asset_ids=(rel.relation_id,),
                            changes=(),
                            chapter_range=_chapter_range_from_attrs(rel.attributes),
                            evidence_refs=(
                                EvidenceRefLite(
                                    evidence_id=f"relation_version:{rel.version_id}",
                                    evidence_role="support",
                                ),
                            )
                            if rel.evidence_count
                            else (),
                        )
                    )
                )
            return {"items": items}

        if module == WholeBookModuleKey.HOOKS_PAYOFFS:
            items = []
            hooks = [a for a in assets if a.asset_type == AssetType.HOOK.value] or list(assets)
            for asset in hooks[:MAX_PAYLOAD_ITEMS]:
                payoff_ids = _parse_id_list(asset.attributes, "payoff_asset_ids")
                if not payoff_ids:
                    payoff_ids = tuple(
                        r.target_asset_id
                        for r in relations
                        if r.source_asset_id == asset.asset_id
                        and r.relation_type == RelationType.PAYS_OFF.value
                    )
                items.append(
                    _dto_to_dict(
                        HooksPayoffsResultDto(
                            hook_asset_id=asset.asset_id,
                            hook_type=str(asset.attributes.get("hook_type") or asset.asset_type),
                            setup_chapter=asset.chapter_range[0],
                            payoff_asset_ids=payoff_ids,
                            payoff_status=str(asset.attributes.get("payoff_status") or "unknown"),
                            payoff_chapters=tuple(
                                int(x)
                                for x in (asset.attributes.get("payoff_chapters") or [])
                                if isinstance(x, int)
                                or (isinstance(x, str) and x.isdigit())
                            ),
                            delay=(
                                int(asset.attributes["delay"])
                                if isinstance(asset.attributes.get("delay"), int)
                                else None
                            ),
                            evidence_refs=self._evidence_refs_from_assets((asset,)),
                        )
                    )
                )
            return {"items": items}

        if module == WholeBookModuleKey.CAUSAL_CHAIN:
            items = []
            for rel in relations[:MAX_PAYLOAD_ITEMS]:
                items.append(
                    _dto_to_dict(
                        CausalChainResultDto(
                            source_asset_id=rel.source_asset_id,
                            target_asset_id=rel.target_asset_id,
                            relation_id=rel.relation_id,
                            causal_type=rel.relation_type,
                            strength=rel.confidence,
                            evidence_refs=(
                                EvidenceRefLite(
                                    evidence_id=f"relation_version:{rel.version_id}",
                                    evidence_role="support",
                                ),
                            )
                            if rel.evidence_count
                            else (),
                        )
                    )
                )
            return {"items": items}

        if module == WholeBookModuleKey.BASIC_TIMELINE:
            timeline_items = []
            event_ids = []
            for idx, asset in enumerate(assets[:MAX_PAYLOAD_ITEMS]):
                event_ids.append(asset.asset_id)
                timeline_items.append(
                    TimelineItemDto(
                        item_id=str(asset.asset_id),
                        story_time=(
                            str(asset.attributes["story_time"])
                            if asset.attributes.get("story_time") is not None
                            else None
                        ),
                        narrative_order=int(asset.attributes.get("narrative_order") or idx),
                        chapter_id=asset.chapter_range[0],
                        event_asset_ids=(asset.asset_id,),
                        certainty=str(asset.attributes.get("certainty") or "unknown"),
                        summary=asset.summary,
                    )
                )
            dto = BasicTimelineResultDto(
                timeline_items=tuple(timeline_items),
                story_time=None,
                narrative_order=tuple(i.narrative_order for i in timeline_items),
                chapter_id=None,
                event_asset_ids=tuple(event_ids),
                certainty="unknown",
                evidence_refs=self._evidence_refs_from_assets(assets),
            )
            return _dto_to_dict(dto)

        if module == WholeBookModuleKey.DIAGNOSTICS:
            items = []
            for asset in assets[:MAX_PAYLOAD_ITEMS]:
                items.append(
                    DiagnosticItemDto(
                        diagnostic_id=str(asset.asset_id),
                        category=str(asset.attributes.get("category") or asset.asset_type),
                        severity=str(asset.attributes.get("severity") or "info"),
                        affected_asset_ids=_parse_id_list(asset.attributes, "affected_asset_ids"),
                        affected_chapters=tuple(
                            x
                            for x in (
                                asset.chapter_range[0],
                                asset.chapter_range[1],
                            )
                            if x is not None
                        ),
                        evidence_refs=self._evidence_refs_from_assets((asset,)),
                        explanation=asset.summary or asset.title,
                        user_actionable=bool(asset.attributes.get("user_actionable", False)),
                        recommendation=str(asset.attributes.get("recommendation") or ""),
                    )
                )
            dto = DiagnosticsResultDto(diagnostic_items=tuple(items))
            return _dto_to_dict(dto)

        return empty_payload_for_module(module)


def envelope_to_dict(envelope: WholeBookResultEnvelope) -> dict[str, Any]:
    """Serialize envelope for HTTP — no prompt/credential/body fields."""

    payload = dict(envelope.payload)
    # Hard strip accidental body-like keys.
    for banned in ("full_text", "body", "prompt", "credential", "api_key", "raw_model_json"):
        payload.pop(banned, None)

    return {
        "schema": envelope.schema,
        "version": envelope.version,
        "run_id": envelope.run_id,
        "book_id": envelope.book_id,
        "book_snapshot_id": envelope.book_snapshot_id,
        "analysis_mode": envelope.analysis_mode.value
        if hasattr(envelope.analysis_mode, "value")
        else str(envelope.analysis_mode),
        "module_key": envelope.module_key.value
        if hasattr(envelope.module_key, "value")
        else str(envelope.module_key),
        "module_status": envelope.module_status.value
        if hasattr(envelope.module_status, "value")
        else str(envelope.module_status),
        "generated_at": envelope.generated_at,
        "source_stage_keys": list(envelope.source_stage_keys),
        "source_artifact_ids": list(envelope.source_artifact_ids),
        "asset_ids": list(envelope.asset_ids),
        "asset_version_ids": list(envelope.asset_version_ids),
        "relation_ids": list(envelope.relation_ids),
        "relation_version_ids": list(envelope.relation_version_ids),
        "conflict_ids": list(envelope.conflict_ids),
        "evidence_count": envelope.evidence_count,
        "confidence_summary": _dto_to_dict(envelope.confidence_summary),
        "review_summary": _dto_to_dict(envelope.review_summary),
        "stale": envelope.stale,
        "partial": envelope.partial,
        "warnings": list(envelope.warnings),
        "payload": payload,
    }


def result_index_to_dict(index: WholeBookResultIndex) -> dict[str, Any]:
    return {
        "schema": index.schema,
        "version": index.version,
        "run_id": index.run_id,
        "book_id": index.book_id,
        "book_snapshot_id": index.book_snapshot_id,
        "analysis_mode": index.analysis_mode.value,
        "generated_at": index.generated_at,
        "requested_modules": list(index.requested_modules),
        "available_modules": list(index.available_modules),
        "modules": [
            {
                "module_key": e.module_key.value,
                "module_status": e.module_status.value,
                "stale": e.stale,
                "partial": e.partial,
                "source_stage_keys": list(e.source_stage_keys),
                "evidence_count": e.evidence_count,
                "conflict_count": e.conflict_count,
                "available": e.available,
            }
            for e in index.modules
        ],
        "warnings": list(index.warnings),
    }


__all__ = [
    "ENGINE_MODULE_PLANNING_STAGES",
    "PRODUCT_MODULE_STAGE_DEPENDENCIES",
    "MAX_VISIBLE_ASSETS",
    "MAX_VISIBLE_RELATIONS",
    "ConflictSummaryDto",
    "EvidenceIndexEntry",
    "ModuleIndexEntry",
    "ProjectionAssetRow",
    "ProjectionRelationRow",
    "WholeBookResultIndex",
    "WholeBookResultIndexService",
    "aggregate_module_status",
    "empty_payload_for_module",
    "envelope_to_dict",
    "infer_requested_modules",
    "result_index_to_dict",
    "validate_module_payload",
    "_QueryCounter",
]
