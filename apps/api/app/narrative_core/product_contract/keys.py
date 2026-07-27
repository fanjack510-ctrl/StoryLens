"""Shared product keys and module→stage dependency contract (Phase 1D-P / 1D Integration).

UI module keys must never be used as Engine Stage keys.
Module ↔ Stage is many-to-many; resolution auto-closes required stages.

Two intentional mappings (do not collapse):
- ENGINE_MODULE_PLANNING_STAGES (whole_book_stage_plan) — execution plan seeds
- PRODUCT_MODULE_STAGE_DEPENDENCIES (this module) — result status / viewability
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.narrative_core.enums import WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.product_contract.enums import ResultNavSectionKey

WHOLE_BOOK_MODULE_KEYS: tuple[WholeBookModuleKey, ...] = tuple(WholeBookModuleKey)

# Product Result Dependencies — which stages gate module result status / Envelope.
# Must remain a subset of Engine Planning Closure (see mapping_consistency).
PRODUCT_MODULE_STAGE_DEPENDENCIES: dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]] = {
    WholeBookModuleKey.BOOK_OVERVIEW: (
        WholeBookStageKey.BUILD_FULLTEXT_INDEX,
    ),
    WholeBookModuleKey.STRUCTURE_STAGES: (
        WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.ANALYZE_STRUCTURE,
    ),
    WholeBookModuleKey.CHAPTER_FUNCTIONS: (
        WholeBookStageKey.ANALYZE_STRUCTURE,
    ),
    WholeBookModuleKey.STORYLINES: (
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.ANALYZE_STRUCTURE,
        WholeBookStageKey.ANALYZE_STORYLINES,
    ),
    WholeBookModuleKey.CHARACTERS: (
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.ANALYZE_CHARACTERS,
    ),
    WholeBookModuleKey.CHARACTER_ARCS: (
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.ANALYZE_CHARACTERS,
        WholeBookStageKey.ANALYZE_STORYLINES,
    ),
    WholeBookModuleKey.RELATIONSHIPS: (
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.ANALYZE_CHARACTERS,
        WholeBookStageKey.ANALYZE_STORYLINES,
    ),
    WholeBookModuleKey.HOOKS_PAYOFFS: (
        WholeBookStageKey.ANALYZE_STRUCTURE,
        WholeBookStageKey.ANALYZE_STORYLINES,
        WholeBookStageKey.ANALYZE_HOOKS,
    ),
    WholeBookModuleKey.CAUSAL_CHAIN: (
        WholeBookStageKey.ANALYZE_STORYLINES,
        WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,
    ),
    WholeBookModuleKey.BASIC_TIMELINE: (
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,
    ),
    WholeBookModuleKey.DIAGNOSTICS: (
        WholeBookStageKey.ANALYZE_STRUCTURE,
        WholeBookStageKey.ANALYZE_STORYLINES,
        WholeBookStageKey.ANALYZE_CHARACTERS,
        WholeBookStageKey.ANALYZE_HOOKS,
        WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,
        WholeBookStageKey.VERIFY_EVIDENCE,
    ),
}

# Deprecated alias — prefer PRODUCT_MODULE_STAGE_DEPENDENCIES.
MODULE_STAGE_DEPENDENCIES = PRODUCT_MODULE_STAGE_DEPENDENCIES

# Result page navigation (product IA). Module keys map into sections.
RESULT_NAV_SECTIONS: tuple[tuple[ResultNavSectionKey, tuple[WholeBookModuleKey, ...]], ...] = (
    (ResultNavSectionKey.OVERVIEW, (WholeBookModuleKey.BOOK_OVERVIEW,)),
    (
        ResultNavSectionKey.STRUCTURE,
        (WholeBookModuleKey.STRUCTURE_STAGES, WholeBookModuleKey.CHAPTER_FUNCTIONS),
    ),
    (ResultNavSectionKey.STORYLINES, (WholeBookModuleKey.STORYLINES,)),
    (
        ResultNavSectionKey.CHARACTERS,
        (WholeBookModuleKey.CHARACTERS, WholeBookModuleKey.CHARACTER_ARCS),
    ),
    (ResultNavSectionKey.RELATIONSHIPS, (WholeBookModuleKey.RELATIONSHIPS,)),
    (ResultNavSectionKey.HOOKS_PAYOFFS, (WholeBookModuleKey.HOOKS_PAYOFFS,)),
    (
        ResultNavSectionKey.CAUSAL_TIMELINE,
        (WholeBookModuleKey.CAUSAL_CHAIN, WholeBookModuleKey.BASIC_TIMELINE),
    ),
    (ResultNavSectionKey.DIAGNOSTICS, (WholeBookModuleKey.DIAGNOSTICS,)),
    (ResultNavSectionKey.EVIDENCE_CONFLICTS, ()),
    (ResultNavSectionKey.STRUCTURE_MAP, ()),
)

FUTURE_API_ROUTES: tuple[str, ...] = (
    "POST /api/v1/books/{book_id}/whole-book-runs",
    "GET /api/v1/whole-book-runs/{run_id}",
    "GET /api/v1/whole-book-runs/{run_id}/stages",
    "POST /api/v1/whole-book-runs/{run_id}/pause",
    "POST /api/v1/whole-book-runs/{run_id}/resume",
    "POST /api/v1/whole-book-runs/{run_id}/cancel",
    "POST /api/v1/whole-book-runs/{run_id}/stages/{stage_key}/retry",
    "GET /api/v1/narrative-assets/{asset_id}/evidence",
    "POST /api/v1/narrative-review-actions",
    "GET /api/v1/books/{book_id}/analysis-conflicts",
)

EXISTING_API_ROUTES: tuple[str, ...] = (
    "GET /api/v1/capabilities",
    "GET /api/v1/capabilities/{key}",
    "POST /api/v1/books/{book_id}/whole-book-runs/preflight",
    "GET /api/v1/whole-book-runs/{run_id}/results",
    "GET /api/v1/whole-book-runs/{run_id}/results/{module_key}",
)


def _normalize_module(raw: WholeBookModuleKey | str) -> WholeBookModuleKey:
    if isinstance(raw, WholeBookModuleKey):
        return raw
    return WholeBookModuleKey(str(raw))


def resolve_modules_with_dependencies(
    requested: Sequence[WholeBookModuleKey | str],
) -> tuple[tuple[WholeBookModuleKey, ...], tuple[WholeBookStageKey, ...], tuple[str, ...]]:
    """Resolve requested modules → unique modules + required stages + user-facing notes.

    Users cannot cancel required dependency stages. Auto-filled stages are explained
    via ``auto_fill_notes``.
    """

    if not requested:
        modules = tuple(WHOLE_BOOK_MODULE_KEYS)
    else:
        seen: list[WholeBookModuleKey] = []
        for raw in requested:
            module = _normalize_module(raw)
            if module not in seen:
                seen.append(module)
        modules = tuple(seen)

    stages: list[WholeBookStageKey] = []
    for module in modules:
        for stage in PRODUCT_MODULE_STAGE_DEPENDENCIES[module]:
            if stage not in stages:
                stages.append(stage)

    notes: list[str] = []
    for module in modules:
        deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[module]
        notes.append(
            f"module {module.value} requires stages: "
            + ", ".join(s.value for s in deps)
        )
    return modules, tuple(stages), tuple(notes)


def stages_for_modules(modules: Iterable[WholeBookModuleKey | str]) -> tuple[WholeBookStageKey, ...]:
    _, stages, _ = resolve_modules_with_dependencies(tuple(modules))
    return stages
