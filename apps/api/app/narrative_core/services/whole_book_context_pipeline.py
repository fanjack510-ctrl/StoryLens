"""Whole-book Snapshot Context Pipeline (Agent Q / CHG-038).

Completed Snapshot is the sole fact source. No model calls, prompts, FTS5,
vector DB, Neo4j, or new tables. Temporary caches are not recovery facts.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshot,
    NarrativeAsset,
    NarrativeAssetVersion,
    ReaderJourneyRun,
    Scene,
)
from app.narrative_core.enums import ReviewStatus, SnapshotStatus, WholeBookAnalysisMode
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.private_engine_contract.context import (
    CONTEXT_PIPELINE_VERSION,
    CONTEXT_SCHEMA,
    CONTEXT_SCHEMA_VERSION,
    ContextBundle,
    ContextLevel,
    ContextUnitType,
    WholeBookContextUnit,
    sort_context_units_deterministically,
)
from app.narrative_core.private_engine_contract.errors import PrivateEngineErrorCode
from app.narrative_core.private_engine_contract.module_spec import (
    WholeBookModuleExecutionSpec,
    get_module_spec,
)
from app.narrative_core.private_engine_contract.quality import WholeBookQualityProfile
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_context_units import (
    ChapterNormalizeRecord,
    ContextUnitBuilder,
    SnapshotTextRef,
    SnapshotTextResolver,
    UnitBuildConfig,
    assert_snapshot_completed,
    chapter_record_from_orm,
    estimate_tokens,
)

logger = logging.getLogger(__name__)

CONTEXT_INDEX_PERSISTENCE = "non-persistent"
CONTEXT_INDEX_FACT_SOURCE = False


class ContextMode(StrEnum):
    NATIVE = "native"
    ENHANCED = "enhanced"


@dataclass(frozen=True, slots=True)
class ContextCoverage:
    chapter_units: int
    scene_units: int
    paragraph_group_units: int
    evidence_window_units: int
    derived_summary_units: int
    levels_included: tuple[int, ...]
    degraded: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HierarchicalContextPlan:
    required_levels: tuple[int, ...]
    selected_levels: tuple[int, ...]
    selected_unit_ids: tuple[str, ...]
    estimated_characters: int
    estimated_tokens: int
    provider_context_limit: int
    budget_policy_key: str
    downgraded: bool
    warnings: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class WholeBookContextBundle:
    """Service-layer bundle: contract ContextBundle + planning metadata."""

    schema: str
    schema_version: str
    pipeline_version: str
    book_id: int
    book_snapshot_id: int
    snapshot_content_hash: str
    chapter_hashes: tuple[str, ...]
    paragraph_hashes: tuple[str, ...]
    context_unit_refs: tuple[str, ...]
    units: tuple[WholeBookContextUnit, ...]
    requested_modules: tuple[str, ...]
    resolved_modules: tuple[str, ...]
    configuration_fingerprint: str
    bundle_hash: str
    mode: ContextMode
    analysis_mode: str
    quality_profile_key: str
    source_language: str
    token_estimate: int
    character_estimate: int
    coverage: ContextCoverage
    warnings: tuple[str, ...] = ()
    plan: HierarchicalContextPlan | None = None

    def to_contract_bundle(self) -> ContextBundle:
        return ContextBundle(
            book_id=self.book_id,
            book_snapshot_id=self.book_snapshot_id,
            snapshot_content_hash=self.snapshot_content_hash,
            chapter_hashes=self.chapter_hashes,
            paragraph_hashes=self.paragraph_hashes,
            context_schema=self.schema,
            context_schema_version=self.schema_version,
            pipeline_version=self.pipeline_version,
            configuration_fingerprint=self.configuration_fingerprint,
            units=self.units,
            bundle_hash=self.bundle_hash,
        )

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize without full text / credentials / prompts."""
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "pipeline_version": self.pipeline_version,
            "book_id": self.book_id,
            "book_snapshot_id": self.book_snapshot_id,
            "snapshot_content_hash": self.snapshot_content_hash,
            "chapter_hashes": list(self.chapter_hashes),
            "paragraph_hashes_count": len(self.paragraph_hashes),
            "context_unit_refs": list(self.context_unit_refs),
            "requested_modules": list(self.requested_modules),
            "resolved_modules": list(self.resolved_modules),
            "configuration_fingerprint": self.configuration_fingerprint,
            "bundle_hash": self.bundle_hash,
            "mode": self.mode.value,
            "analysis_mode": self.analysis_mode,
            "quality_profile_key": self.quality_profile_key,
            "source_language": self.source_language,
            "token_estimate": self.token_estimate,
            "character_estimate": self.character_estimate,
            "coverage": asdict(self.coverage),
            "warnings": list(self.warnings),
            "units": [
                {
                    "unit_id": u.unit_id,
                    "unit_type": u.unit_type.value,
                    "text_ref": u.text_ref,
                    "content_hash": u.content_hash,
                    "character_count": u.character_count,
                    "token_estimate": u.token_estimate,
                    "derived": u.derived,
                }
                for u in self.units
            ],
        }


@dataclass
class WholeBookContextIndex:
    """Process-local / computational index. Non-persistent. Not a fact source."""

    book_id: int
    book_snapshot_id: int
    snapshot_content_hash: str
    units: tuple[WholeBookContextUnit, ...]
    persistence: str = CONTEXT_INDEX_PERSISTENCE
    is_fact_source: bool = CONTEXT_INDEX_FACT_SOURCE
    _by_id: dict[str, WholeBookContextUnit] = field(default_factory=dict, repr=False)
    _paragraph_locate: dict[int, WholeBookContextUnit] = field(default_factory=dict, repr=False)
    _resolver: SnapshotTextResolver | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        ordered = sort_context_units_deterministically(self.units)
        object.__setattr__(self, "units", ordered)
        by_id = {u.unit_id: u for u in ordered}
        object.__setattr__(self, "_by_id", by_id)
        locate: dict[int, WholeBookContextUnit] = {}
        for unit in ordered:
            if unit.unit_type in (
                ContextUnitType.PARAGRAPH_GROUP,
                ContextUnitType.EVIDENCE_WINDOW,
                ContextUnitType.CHAPTER,
                ContextUnitType.SCENE,
            ):
                for pid in unit.snapshot_paragraph_ids:
                    locate.setdefault(pid, unit)
        object.__setattr__(self, "_paragraph_locate", locate)

    def bind_resolver(self, resolver: SnapshotTextResolver) -> None:
        self._resolver = resolver

    def get_unit(self, unit_id: str) -> WholeBookContextUnit | None:
        return self._by_id.get(unit_id)

    def list_units(self) -> tuple[WholeBookContextUnit, ...]:
        return self.units

    def list_chapter_units(self) -> tuple[WholeBookContextUnit, ...]:
        return tuple(u for u in self.units if u.unit_type == ContextUnitType.CHAPTER)

    def list_scene_units(self) -> tuple[WholeBookContextUnit, ...]:
        return tuple(u for u in self.units if u.unit_type == ContextUnitType.SCENE)

    def resolve_text(self, text_ref: str | SnapshotTextRef) -> str:
        if self._resolver is None:
            raise RuntimeError("SnapshotTextResolver not bound; index is non-persistent")
        return self._resolver.resolve(text_ref)

    def locate_paragraph(self, snapshot_paragraph_id: int) -> WholeBookContextUnit | None:
        return self._paragraph_locate.get(snapshot_paragraph_id)

    def locate_evidence_window(
        self,
        *,
        snapshot_paragraph_id: int,
        start_offset: int,
        end_offset: int,
    ) -> WholeBookContextUnit | None:
        for unit in self.units:
            if unit.unit_type != ContextUnitType.EVIDENCE_WINDOW:
                continue
            if snapshot_paragraph_id not in unit.snapshot_paragraph_ids:
                continue
            meta = unit.metadata or {}
            if int(meta.get("start_offset", -1)) == start_offset and int(
                meta.get("end_offset", -1)
            ) == end_offset:
                return unit
        return None

    def calculate_hash(self) -> str:
        payload = {
            "book_id": self.book_id,
            "book_snapshot_id": self.book_snapshot_id,
            "snapshot_content_hash": self.snapshot_content_hash,
            "unit_ids": [u.unit_id for u in self.units],
            "unit_hashes": [u.content_hash for u in self.units],
        }
        return calculate_text_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))

    def coverage(self) -> ContextCoverage:
        return ContextCoverage(
            chapter_units=sum(1 for u in self.units if u.unit_type == ContextUnitType.CHAPTER),
            scene_units=sum(1 for u in self.units if u.unit_type == ContextUnitType.SCENE),
            paragraph_group_units=sum(
                1 for u in self.units if u.unit_type == ContextUnitType.PARAGRAPH_GROUP
            ),
            evidence_window_units=sum(
                1 for u in self.units if u.unit_type == ContextUnitType.EVIDENCE_WINDOW
            ),
            derived_summary_units=sum(
                1 for u in self.units if u.unit_type == ContextUnitType.DERIVED_SUMMARY
            ),
            levels_included=(),
        )


def configuration_fingerprint(
    *,
    pipeline_version: str,
    module_specs: Sequence[WholeBookModuleExecutionSpec],
    quality_profile: WholeBookQualityProfile | Mapping[str, Any],
    budget_policy_key: str,
    provider_context_limit: int,
    source_language: str,
    analysis_mode: str,
    mode: ContextMode,
    grouping: Mapping[str, Any] | None = None,
) -> str:
    if isinstance(quality_profile, WholeBookQualityProfile):
        qp = {
            "profile_key": quality_profile.profile_key.value,
            "context_strategy_key": quality_profile.context_strategy_key,
            "evidence_policy_key": quality_profile.evidence_policy_key,
            "budget_policy_key": quality_profile.budget_policy_key,
        }
    else:
        qp = dict(quality_profile)
    payload = {
        "pipeline_version": pipeline_version,
        "modules": [
            {"key": s.module_key.value, "version": s.module_version, "levels": list(s.required_context_levels)}
            for s in sorted(module_specs, key=lambda s: s.module_key.value)
        ],
        "quality_profile": qp,
        "budget_policy_key": budget_policy_key,
        "provider_context_limit": provider_context_limit,
        "source_language": source_language,
        "analysis_mode": analysis_mode,
        "mode": mode.value,
        "grouping": dict(grouping or {}),
    }
    return calculate_text_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def compute_bundle_hash(
    *,
    snapshot_content_hash: str,
    chapter_hashes: Sequence[str],
    unit_ids: Sequence[str],
    configuration_fingerprint_value: str,
    pipeline_version: str,
) -> str:
    payload = {
        "snapshot_content_hash": snapshot_content_hash,
        "chapter_hashes": list(chapter_hashes),
        "unit_ids": list(unit_ids),
        "configuration_fingerprint": configuration_fingerprint_value,
        "pipeline_version": pipeline_version,
        "schema": CONTEXT_SCHEMA,
        "schema_version": CONTEXT_SCHEMA_VERSION,
    }
    return calculate_text_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))


class HierarchicalContextPlanner:
    """Generic Level 0–3 selector. No prompts. No model calls. No per-book knobs."""

    def plan(
        self,
        *,
        units: Sequence[WholeBookContextUnit],
        module_specs: Sequence[WholeBookModuleExecutionSpec],
        provider_context_limit: int,
        budget_policy_key: str,
        prefer_evidence: bool = True,
    ) -> HierarchicalContextPlan:
        required: set[int] = set()
        for spec in module_specs:
            required.update(int(x) for x in spec.required_context_levels)
        required_levels = tuple(sorted(required))

        # Budget policy → soft token budget fraction of provider limit.
        budget_fraction = {
            "budget.tight": 0.45,
            "budget.standard": 0.70,
            "budget.relaxed": 0.90,
        }.get(budget_policy_key, 0.70)
        token_budget = max(1, int(provider_context_limit * budget_fraction))

        level_to_types: dict[int, frozenset[ContextUnitType]] = {
            0: frozenset({ContextUnitType.BOOK, ContextUnitType.CHAPTER}),
            1: frozenset({ContextUnitType.CHAPTER, ContextUnitType.DERIVED_SUMMARY}),
            2: frozenset({ContextUnitType.SCENE, ContextUnitType.PARAGRAPH_GROUP}),
            3: frozenset({ContextUnitType.EVIDENCE_WINDOW}),
        }

        selected: list[WholeBookContextUnit] = []
        selected_levels: list[int] = []
        warnings: list[str] = []
        tokens_used = 0
        downgraded = False

        # Always try lower levels first for overview, then evidence if required.
        ordered_levels = sorted(required_levels)
        if prefer_evidence and 3 in ordered_levels:
            # Evidence before unconstrained level-2 dumps when tight.
            if budget_policy_key == "budget.tight":
                ordered_levels = [lvl for lvl in ordered_levels if lvl != 2] + (
                    [2] if 2 in required_levels else []
                )

        for level in ordered_levels:
            types = level_to_types.get(level, frozenset())
            candidates = [u for u in units if u.unit_type in types]
            if level == 1:
                # Prefer chapter refs over derived summaries as evidence substitutes.
                candidates = sorted(
                    candidates,
                    key=lambda u: (0 if u.unit_type == ContextUnitType.CHAPTER else 1, u.unit_id),
                )
            if level == 3 and prefer_evidence:
                candidates = [u for u in candidates if not u.derived]

            level_units: list[WholeBookContextUnit] = []
            for unit in candidates:
                cost = unit.token_estimate or estimate_tokens(unit.character_count)
                if tokens_used + cost > token_budget and level_units:
                    downgraded = True
                    warnings.append(
                        f"level_{level}_truncated_for_budget:{budget_policy_key}"
                    )
                    break
                if tokens_used + cost > token_budget and not level_units and level > 0:
                    # Cannot fit any unit at this level.
                    downgraded = True
                    warnings.append(
                        f"level_{level}_omitted_over_limit:{provider_context_limit}"
                    )
                    break
                if tokens_used + cost > token_budget and not level_units and level == 0:
                    # Level 0 metadata must fit; if not, hard error.
                    return HierarchicalContextPlan(
                        required_levels=required_levels,
                        selected_levels=(),
                        selected_unit_ids=(),
                        estimated_characters=0,
                        estimated_tokens=0,
                        provider_context_limit=provider_context_limit,
                        budget_policy_key=budget_policy_key,
                        downgraded=True,
                        warnings=(
                            PrivateEngineErrorCode.CONTEXT_LIMIT_EXCEEDED.value,
                        ),
                        error_code=PrivateEngineErrorCode.CONTEXT_LIMIT_EXCEEDED.value,
                    )
                level_units.append(unit)
                tokens_used += cost
            if level_units:
                selected.extend(level_units)
                selected_levels.append(level)

        # Evidence requirement: if level 3 required but empty and budget forced omit → warn.
        if 3 in required_levels and 3 not in selected_levels:
            downgraded = True
            warnings.append("evidence_level_unavailable_under_budget")

        chars = sum(u.character_count for u in selected)
        return HierarchicalContextPlan(
            required_levels=required_levels,
            selected_levels=tuple(selected_levels),
            selected_unit_ids=tuple(u.unit_id for u in sort_context_units_deterministically(selected)),
            estimated_characters=chars,
            estimated_tokens=tokens_used,
            provider_context_limit=provider_context_limit,
            budget_policy_key=budget_policy_key,
            downgraded=downgraded,
            warnings=tuple(warnings),
            error_code=None,
        )


class DefaultWholeBookContextPipeline:
    """Default Snapshot → Context Units → Index → Bundle pipeline."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_service: BookSnapshotServiceImpl | None = None,
        unit_config: UnitBuildConfig | None = None,
        text_resolver: SnapshotTextResolver | None = None,
    ) -> None:
        self._session = session
        self._snapshots = snapshot_service or BookSnapshotServiceImpl(session)
        self._unit_config = unit_config or UnitBuildConfig()
        self._builder = ContextUnitBuilder(
            source_language=self._unit_config.source_language,
            grouping=self._unit_config.grouping,
        )
        self._resolver = text_resolver or SnapshotTextResolver(
            session, snapshot_service=self._snapshots
        )
        self._prepared: Mapping[str, Any] | None = None
        self._chapters: tuple[ChapterNormalizeRecord, ...] = ()

    @property
    def text_resolver(self) -> SnapshotTextResolver:
        return self._resolver

    def prepare_snapshot(self, book_id: int, book_snapshot_id: int) -> Mapping[str, Any]:
        self._snapshots.validate_snapshot_for_book(book_snapshot_id, book_id)
        snapshot = self._snapshots.get_completed_snapshot(book_snapshot_id)
        assert_snapshot_completed(snapshot)
        # Do not read live Paragraph as substitute.
        self._prepared = {
            "book_id": book_id,
            "book_snapshot_id": snapshot.id,
            "snapshot_content_hash": snapshot.content_hash,
            "chapter_count": snapshot.chapter_count,
            "paragraph_count": snapshot.paragraph_count,
            "character_count": snapshot.character_count,
            "fact_source": "snapshot",
            "snapshot_status": SnapshotStatus.COMPLETED.value,
            "fts5": False,
            "vector_db": False,
            "neo4j": False,
            "new_tables": False,
        }
        return dict(self._prepared)

    def normalize_chapters(
        self, snapshot_ref: Mapping[str, Any] | None = None
    ) -> Sequence[ChapterNormalizeRecord]:
        ref = snapshot_ref or self._prepared
        if ref is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
                "prepare_snapshot required before normalize_chapters",
            )
        book_id = int(ref["book_id"])
        snapshot_id = int(ref["book_snapshot_id"])
        snapshot = self._snapshots.get_completed_snapshot(snapshot_id)
        if snapshot.book_id != book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                "snapshot book mismatch",
            )
        chapters = sorted(snapshot.chapters, key=lambda c: c.chapter_order)
        records = tuple(
            chapter_record_from_orm(
                book_id=book_id,
                snapshot=snapshot,
                chapter=ch,
                source_language=self._unit_config.source_language,
            )
            for ch in chapters
        )
        self._chapters = records
        return records

    def build_chapter_units(
        self, chapters: Sequence[ChapterNormalizeRecord] | None = None
    ) -> Sequence[WholeBookContextUnit]:
        rows = chapters if chapters is not None else self._chapters
        units = [self._builder.build_chapter_unit(ch) for ch in rows]
        return sort_context_units_deterministically(units)

    def build_scene_units(
        self,
        chapters: Sequence[ChapterNormalizeRecord] | None = None,
        *,
        scenes: Sequence[Mapping[str, Any]] = (),
    ) -> Sequence[WholeBookContextUnit]:
        """Native mode: empty unless scenes provided (Enhanced injects mappings)."""
        _ = chapters
        if not scenes:
            return ()
        units: list[WholeBookContextUnit] = []
        for scene in scenes:
            units.append(
                self._builder.build_scene_unit(
                    book_id=int(scene["book_id"]),
                    book_snapshot_id=int(scene["book_snapshot_id"]),
                    snapshot_chapter_id=int(scene["snapshot_chapter_id"]),
                    chapter_order=int(scene["chapter_order"]),
                    scene_id=int(scene["scene_id"]),
                    snapshot_paragraph_ids=tuple(scene.get("snapshot_paragraph_ids", ())),
                    stable_paragraph_ids=tuple(scene.get("stable_paragraph_ids", ())),
                    paragraph_texts_or_hashes=tuple(scene.get("paragraph_hashes", ())),
                    hashes_only=True,
                    stale=bool(scene.get("stale", False)),
                    source_language=str(scene.get("source_language", self._unit_config.source_language)),
                )
            )
        return sort_context_units_deterministically(units)

    def build_paragraph_units(
        self, chapters: Sequence[ChapterNormalizeRecord] | None = None
    ) -> Sequence[WholeBookContextUnit]:
        rows = chapters if chapters is not None else self._chapters
        units: list[WholeBookContextUnit] = []
        for ch in rows:
            units.extend(self._builder.build_paragraph_group_units(ch))
        return sort_context_units_deterministically(units)

    def build_context_index(
        self, units: Sequence[WholeBookContextUnit]
    ) -> WholeBookContextIndex:
        if self._prepared is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
                "prepare_snapshot required before build_context_index",
            )
        index = WholeBookContextIndex(
            book_id=int(self._prepared["book_id"]),
            book_snapshot_id=int(self._prepared["book_snapshot_id"]),
            snapshot_content_hash=str(self._prepared["snapshot_content_hash"]),
            units=tuple(units),
        )
        index.bind_resolver(self._resolver)
        return index

    def build_module_context(
        self,
        *,
        module_key: str,
        units: Sequence[WholeBookContextUnit],
        level: ContextLevel | int,
    ) -> Sequence[WholeBookContextUnit]:
        _ = module_key
        lvl = int(level)
        if lvl == 0:
            filtered = [
                u
                for u in units
                if u.unit_type in (ContextUnitType.BOOK, ContextUnitType.CHAPTER)
            ]
        elif lvl == 1:
            filtered = [
                u
                for u in units
                if u.unit_type in (ContextUnitType.CHAPTER, ContextUnitType.DERIVED_SUMMARY)
            ]
        elif lvl == 2:
            filtered = [
                u
                for u in units
                if u.unit_type in (ContextUnitType.SCENE, ContextUnitType.PARAGRAPH_GROUP)
            ]
        elif lvl == 3:
            filtered = [u for u in units if u.unit_type == ContextUnitType.EVIDENCE_WINDOW]
        else:
            filtered = list(units)
        return sort_context_units_deterministically(filtered)

    def build_context_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        snapshot_content_hash: str,
        units: Sequence[WholeBookContextUnit],
        configuration_fingerprint: str,
    ) -> ContextBundle:
        ordered = sort_context_units_deterministically(units)
        chapter_hashes = tuple(
            u.content_hash for u in ordered if u.unit_type == ContextUnitType.CHAPTER
        )
        paragraph_hashes = tuple(
            h
            for ch in self._chapters
            for h in ch.paragraph_hashes
        )
        bundle_hash = compute_bundle_hash(
            snapshot_content_hash=snapshot_content_hash,
            chapter_hashes=chapter_hashes,
            unit_ids=[u.unit_id for u in ordered],
            configuration_fingerprint_value=configuration_fingerprint,
            pipeline_version=CONTEXT_PIPELINE_VERSION,
        )
        return ContextBundle(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            snapshot_content_hash=snapshot_content_hash,
            chapter_hashes=chapter_hashes,
            paragraph_hashes=paragraph_hashes,
            context_schema=CONTEXT_SCHEMA,
            context_schema_version=CONTEXT_SCHEMA_VERSION,
            pipeline_version=CONTEXT_PIPELINE_VERSION,
            configuration_fingerprint=configuration_fingerprint,
            units=ordered,
            bundle_hash=bundle_hash,
        )

    def validate_context_bundle(self, bundle: ContextBundle | WholeBookContextBundle) -> None:
        if isinstance(bundle, WholeBookContextBundle):
            contract = bundle.to_contract_bundle()
        else:
            contract = bundle
        if contract.context_schema != CONTEXT_SCHEMA:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID.value,
            )
        if not contract.snapshot_content_hash.strip():
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID.value,
            )
        if not contract.bundle_hash.strip():
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID.value,
            )
        for unit in contract.units:
            if unit.book_snapshot_id != contract.book_snapshot_id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_RUN_SNAPSHOT_MISMATCH,
                    PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH.value,
                )
            if unit.book_id is not None and unit.book_id != contract.book_id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                    "context unit crosses book",
                )
            if "full_text" in (unit.metadata or {}) or "novel_body" in (unit.metadata or {}):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                    "full text embedded in context unit",
                )


class WholeBookContextBundleBuilder:
    """Build WholeBookContextBundle from Snapshot + Module Spec + limits."""

    def __init__(
        self,
        session: Session,
        *,
        pipeline: DefaultWholeBookContextPipeline | None = None,
        planner: HierarchicalContextPlanner | None = None,
    ) -> None:
        self._session = session
        self._pipeline = pipeline or DefaultWholeBookContextPipeline(session)
        self._planner = planner or HierarchicalContextPlanner()

    @property
    def pipeline(self) -> DefaultWholeBookContextPipeline:
        return self._pipeline

    def build(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_specs: Sequence[WholeBookModuleExecutionSpec],
        provider_context_limit: int,
        quality_profile: WholeBookQualityProfile,
        budget_policy_key: str | None = None,
        source_language: str = "unknown",
        analysis_mode: WholeBookAnalysisMode | str = WholeBookAnalysisMode.NATIVE,
        mode: ContextMode = ContextMode.NATIVE,
        extra_units: Sequence[WholeBookContextUnit] = (),
        warnings: Sequence[str] = (),
        grouping: Mapping[str, Any] | None = None,
    ) -> WholeBookContextBundle:
        grouping_cfg = dict(grouping) if grouping is not None else dict(self._pipeline._unit_config.grouping)
        self._pipeline._unit_config = UnitBuildConfig(
            source_language=source_language,
            grouping=grouping_cfg,
        )
        self._pipeline._builder = ContextUnitBuilder(
            source_language=source_language,
            grouping=grouping_cfg,
        )

        prepared = self._pipeline.prepare_snapshot(book_id, book_snapshot_id)
        chapters = self._pipeline.normalize_chapters(prepared)
        book_unit = self._pipeline._builder.build_book_unit(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            snapshot_content_hash=str(prepared["snapshot_content_hash"]),
            chapter_count=int(prepared["chapter_count"] or len(chapters)),
            character_count=int(prepared["character_count"] or 0),
        )
        chapter_units = self._pipeline.build_chapter_units(chapters)
        paragraph_units = self._pipeline.build_paragraph_units(chapters)
        all_units = sort_context_units_deterministically(
            (book_unit, *chapter_units, *paragraph_units, *extra_units)
        )

        budget_key = budget_policy_key or quality_profile.budget_policy_key
        analysis_mode_value = (
            analysis_mode.value
            if isinstance(analysis_mode, WholeBookAnalysisMode)
            else str(analysis_mode)
        )
        fp = configuration_fingerprint(
            pipeline_version=CONTEXT_PIPELINE_VERSION,
            module_specs=module_specs,
            quality_profile=quality_profile,
            budget_policy_key=budget_key,
            provider_context_limit=provider_context_limit,
            source_language=source_language,
            analysis_mode=analysis_mode_value,
            mode=mode,
            grouping=self._pipeline._unit_config.grouping,
        )

        plan = self._planner.plan(
            units=all_units,
            module_specs=module_specs,
            provider_context_limit=provider_context_limit,
            budget_policy_key=budget_key,
        )
        if plan.error_code:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_BUDGET_DENIED
                if plan.error_code == PrivateEngineErrorCode.CONTEXT_LIMIT_EXCEEDED.value
                else NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                plan.error_code,
            )

        selected_set = set(plan.selected_unit_ids)
        selected_units = tuple(u for u in all_units if u.unit_id in selected_set)
        # Bundle retains structural chapter units for hash binding even if planner
        # trims some levels — selected refs drive provider payload separately.
        # Default: include selected units only (no unconditional full body).
        bundle_units = selected_units or tuple(
            u for u in all_units if u.unit_type in (ContextUnitType.BOOK, ContextUnitType.CHAPTER)
        )

        chapter_hashes = tuple(
            u.content_hash for u in all_units if u.unit_type == ContextUnitType.CHAPTER
        )
        paragraph_hashes = tuple(h for ch in chapters for h in ch.paragraph_hashes)
        unit_ids = tuple(u.unit_id for u in bundle_units)
        bundle_hash = compute_bundle_hash(
            snapshot_content_hash=str(prepared["snapshot_content_hash"]),
            chapter_hashes=chapter_hashes,
            unit_ids=unit_ids,
            configuration_fingerprint_value=fp,
            pipeline_version=CONTEXT_PIPELINE_VERSION,
        )

        coverage = ContextCoverage(
            chapter_units=sum(1 for u in bundle_units if u.unit_type == ContextUnitType.CHAPTER),
            scene_units=sum(1 for u in bundle_units if u.unit_type == ContextUnitType.SCENE),
            paragraph_group_units=sum(
                1 for u in bundle_units if u.unit_type == ContextUnitType.PARAGRAPH_GROUP
            ),
            evidence_window_units=sum(
                1 for u in bundle_units if u.unit_type == ContextUnitType.EVIDENCE_WINDOW
            ),
            derived_summary_units=sum(
                1 for u in bundle_units if u.unit_type == ContextUnitType.DERIVED_SUMMARY
            ),
            levels_included=plan.selected_levels,
            degraded=plan.downgraded,
            notes=plan.warnings,
        )

        requested = tuple(s.module_key.value for s in module_specs)
        result = WholeBookContextBundle(
            schema=CONTEXT_SCHEMA,
            schema_version=CONTEXT_SCHEMA_VERSION,
            pipeline_version=CONTEXT_PIPELINE_VERSION,
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            snapshot_content_hash=str(prepared["snapshot_content_hash"]),
            chapter_hashes=chapter_hashes,
            paragraph_hashes=paragraph_hashes,
            context_unit_refs=unit_ids,
            units=bundle_units,
            requested_modules=requested,
            resolved_modules=requested,
            configuration_fingerprint=fp,
            bundle_hash=bundle_hash,
            mode=mode,
            analysis_mode=analysis_mode_value,
            quality_profile_key=quality_profile.profile_key.value,
            source_language=source_language,
            token_estimate=plan.estimated_tokens,
            character_estimate=plan.estimated_characters,
            coverage=coverage,
            warnings=tuple(warnings) + plan.warnings,
            plan=plan,
        )
        self._pipeline.validate_context_bundle(result)
        return result


class NativeWholeBookContextProvider:
    """Native mode: Snapshot only. No Scene / Journey / chapter asset requirement."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._builder = WholeBookContextBundleBuilder(session)

    def build_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_keys: Sequence[str],
        provider_context_limit: int,
        quality_profile: WholeBookQualityProfile,
        source_language: str = "unknown",
    ) -> WholeBookContextBundle:
        specs = tuple(get_module_spec(k) for k in module_keys)
        return self._builder.build(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_specs=specs,
            provider_context_limit=provider_context_limit,
            quality_profile=quality_profile,
            source_language=source_language,
            analysis_mode=WholeBookAnalysisMode.NATIVE,
            mode=ContextMode.NATIVE,
        )


@dataclass(frozen=True, slots=True)
class EnhancedAuxAssetRef:
    kind: str
    asset_id: int | None
    review_status: str | None
    book_snapshot_id: int | None
    stale: bool
    excluded: bool
    reason: str = ""


class EnhancedWholeBookContextProvider:
    """Enhanced mode: Snapshot first; aux Scene/Journey/assets may degrade."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._builder = WholeBookContextBundleBuilder(session)
        self._pipeline = self._builder.pipeline

    def build_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_keys: Sequence[str],
        provider_context_limit: int,
        quality_profile: WholeBookQualityProfile,
        source_language: str = "unknown",
    ) -> WholeBookContextBundle:
        warnings: list[str] = []
        extra_units: list[WholeBookContextUnit] = []
        aux_refs: list[EnhancedAuxAssetRef] = []

        prepared = self._pipeline.prepare_snapshot(book_id, book_snapshot_id)
        chapters = self._pipeline.normalize_chapters(prepared)
        chapter_by_source: dict[int, ChapterNormalizeRecord] = {}
        snapshot = self._pipeline._snapshots.get_completed_snapshot(book_snapshot_id)
        for ch in snapshot.chapters:
            if ch.source_chapter_id is not None:
                chapter_by_source[int(ch.source_chapter_id)] = chapter_record_from_orm(
                    book_id=book_id, snapshot=snapshot, chapter=ch, source_language=source_language
                )

        # Scenes (same book only).
        scenes = list(
            self._session.scalars(select(Scene).where(Scene.book_id == book_id).order_by(Scene.ordinal))
        )
        if not scenes:
            warnings.append("enhanced_missing_scenes")
        else:
            stable_to_para: dict[str, tuple[int, str, ChapterNormalizeRecord]] = {}
            for rec in chapters:
                for sid, pid, ph in zip(
                    rec.stable_paragraph_ids,
                    rec.snapshot_paragraph_ids,
                    rec.paragraph_hashes,
                ):
                    stable_to_para[sid] = (pid, ph, rec)

            for scene in scenes:
                start = stable_to_para.get(str(scene.start_paragraph_id))
                end = stable_to_para.get(str(scene.end_paragraph_id))
                rec = chapter_by_source.get(int(scene.chapter_id))
                if rec is None or start is None or end is None:
                    warnings.append(f"enhanced_scene_unmapped:{scene.id}")
                    aux_refs.append(
                        EnhancedAuxAssetRef(
                            kind="scene",
                            asset_id=scene.id,
                            review_status=None,
                            book_snapshot_id=None,
                            stale=True,
                            excluded=True,
                            reason="unmapped_to_snapshot",
                        )
                    )
                    continue
                # Collect paragraphs between start and end within chapter by order.
                try:
                    i0 = rec.stable_paragraph_ids.index(str(scene.start_paragraph_id))
                    i1 = rec.stable_paragraph_ids.index(str(scene.end_paragraph_id))
                except ValueError:
                    warnings.append(f"enhanced_scene_bounds:{scene.id}")
                    continue
                if i1 < i0:
                    i0, i1 = i1, i0
                para_ids = rec.snapshot_paragraph_ids[i0 : i1 + 1]
                stables = rec.stable_paragraph_ids[i0 : i1 + 1]
                hashes = rec.paragraph_hashes[i0 : i1 + 1]
                stale = False
                # Scene content_hash is aux — never overrides Snapshot.
                if scene.content_hash and scene.content_hash not in hashes:
                    # Hash mismatch vs snapshot span → stale aux, still usable as locator only.
                    stale = True
                    warnings.append(f"enhanced_scene_stale:{scene.id}")
                extra_units.append(
                    self._pipeline._builder.build_scene_unit(
                        book_id=book_id,
                        book_snapshot_id=book_snapshot_id,
                        snapshot_chapter_id=rec.snapshot_chapter_id,
                        chapter_order=rec.chapter_order,
                        scene_id=int(scene.id),
                        snapshot_paragraph_ids=para_ids,
                        stable_paragraph_ids=stables,
                        paragraph_texts_or_hashes=hashes,
                        hashes_only=True,
                        stale=stale,
                        source_language=source_language,
                    )
                )
                aux_refs.append(
                    EnhancedAuxAssetRef(
                        kind="scene",
                        asset_id=scene.id,
                        review_status=None,
                        book_snapshot_id=book_snapshot_id,
                        stale=stale,
                        excluded=False,
                        reason="candidate_aux",
                    )
                )

        # Reader Journey (same book).
        journeys = list(
            self._session.scalars(
                select(ReaderJourneyRun).where(ReaderJourneyRun.book_id == book_id)
            )
        )
        if not journeys:
            warnings.append("enhanced_missing_reader_journey")
        else:
            for j in journeys:
                aux_refs.append(
                    EnhancedAuxAssetRef(
                        kind="reader_journey",
                        asset_id=j.id,
                        review_status=str(j.status),
                        book_snapshot_id=None,
                        stale=False,
                        excluded=False,
                        reason="candidate_aux_not_evidence",
                    )
                )

        # Chapter analysis assets — exclude rejected; mark snapshot mismatch stale.
        assets = list(
            self._session.scalars(
                select(NarrativeAsset).where(NarrativeAsset.book_id == book_id)
            )
        )
        if not assets:
            warnings.append("enhanced_missing_chapter_assets")
        for asset in assets:
            versions = list(
                self._session.scalars(
                    select(NarrativeAssetVersion)
                    .where(NarrativeAssetVersion.asset_id == asset.id)
                    .order_by(NarrativeAssetVersion.id)
                )
            )
            for version in versions:
                status = str(version.review_status)
                if status == ReviewStatus.REJECTED.value:
                    aux_refs.append(
                        EnhancedAuxAssetRef(
                            kind="chapter_asset",
                            asset_id=version.id,
                            review_status=status,
                            book_snapshot_id=version.book_snapshot_id,
                            stale=False,
                            excluded=True,
                            reason="rejected",
                        )
                    )
                    continue
                stale = (
                    version.book_snapshot_id is not None
                    and int(version.book_snapshot_id) != book_snapshot_id
                )
                if stale:
                    warnings.append(f"enhanced_asset_stale:{version.id}")
                # derived_summary placeholder only — never final evidence.
                if not stale and status in (
                    ReviewStatus.CANDIDATE.value,
                    ReviewStatus.CONFIRMED.value,
                    ReviewStatus.CORRECTED.value,
                ):
                    extra_units.append(
                        self._pipeline._builder.build_derived_summary_ref(
                            book_id=book_id,
                            book_snapshot_id=book_snapshot_id,
                            summary_ref=f"asset_version://{version.id}",
                            content_hash=calculate_text_hash(
                                f"{version.id}:{version.source_fingerprint}"
                            ),
                        )
                    )
                aux_refs.append(
                    EnhancedAuxAssetRef(
                        kind="chapter_asset",
                        asset_id=version.id,
                        review_status=status,
                        book_snapshot_id=version.book_snapshot_id,
                        stale=stale,
                        excluded=False,
                        reason="canonical" if version.is_canonical else "candidate",
                    )
                )

        specs = tuple(get_module_spec(k) for k in module_keys)
        bundle = self._builder.build(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_specs=specs,
            provider_context_limit=provider_context_limit,
            quality_profile=quality_profile,
            source_language=source_language,
            analysis_mode=WholeBookAnalysisMode.ENHANCED,
            mode=ContextMode.ENHANCED,
            extra_units=extra_units,
            warnings=warnings,
        )
        # Attach aux inventory into coverage notes without embedding bodies.
        enhanced_notes = bundle.coverage.notes + tuple(
            f"aux:{r.kind}:{r.asset_id}:stale={r.stale}:excluded={r.excluded}:{r.reason}"
            for r in aux_refs[:50]
        )
        return WholeBookContextBundle(
            schema=bundle.schema,
            schema_version=bundle.schema_version,
            pipeline_version=bundle.pipeline_version,
            book_id=bundle.book_id,
            book_snapshot_id=bundle.book_snapshot_id,
            snapshot_content_hash=bundle.snapshot_content_hash,
            chapter_hashes=bundle.chapter_hashes,
            paragraph_hashes=bundle.paragraph_hashes,
            context_unit_refs=bundle.context_unit_refs,
            units=bundle.units,
            requested_modules=bundle.requested_modules,
            resolved_modules=bundle.resolved_modules,
            configuration_fingerprint=bundle.configuration_fingerprint,
            bundle_hash=bundle.bundle_hash,
            mode=ContextMode.ENHANCED,
            analysis_mode=bundle.analysis_mode,
            quality_profile_key=bundle.quality_profile_key,
            source_language=bundle.source_language,
            token_estimate=bundle.token_estimate,
            character_estimate=bundle.character_estimate,
            coverage=ContextCoverage(
                chapter_units=bundle.coverage.chapter_units,
                scene_units=bundle.coverage.scene_units,
                paragraph_group_units=bundle.coverage.paragraph_group_units,
                evidence_window_units=bundle.coverage.evidence_window_units,
                derived_summary_units=bundle.coverage.derived_summary_units,
                levels_included=bundle.coverage.levels_included,
                degraded=bundle.coverage.degraded or bool(warnings),
                notes=enhanced_notes,
            ),
            warnings=bundle.warnings,
            plan=bundle.plan,
        )


class InMemoryContextBundleCache:
    """Process-local Context Bundle cache. Not a recovery fact source."""

    def __init__(self, *, max_entries: int = 32) -> None:
        self._max_entries = max(1, max_entries)
        self._store: dict[str, WholeBookContextBundle] = {}

    @staticmethod
    def make_key(
        *,
        snapshot_content_hash: str,
        pipeline_version: str,
        module_spec_versions: Sequence[tuple[str, str]],
        quality_profile_key: str,
        configuration_fingerprint: str,
    ) -> str:
        mods = ",".join(f"{k}@{v}" for k, v in sorted(module_spec_versions))
        raw = "|".join(
            (
                snapshot_content_hash,
                pipeline_version,
                mods,
                quality_profile_key,
                configuration_fingerprint,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> WholeBookContextBundle | None:
        return self._store.get(key)

    def put(self, key: str, bundle: WholeBookContextBundle) -> None:
        # Never cache credentials / prompts — bundle DTO forbids them.
        public = bundle.to_public_dict()
        banned = ("api_key", "credential", "prompt_body", "authorization")
        blob = json.dumps(public, ensure_ascii=False).lower()
        if any(token in blob for token in banned):
            raise ValueError("refusing to cache bundle containing forbidden secrets")
        if len(self._store) >= self._max_entries and key not in self._store:
            oldest = next(iter(self._store))
            self._store.pop(oldest, None)
        self._store[key] = bundle

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)

    def __len__(self) -> int:
        return len(self._store)
