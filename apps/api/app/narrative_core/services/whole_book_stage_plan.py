"""WholeBook stage plan builder — stable order, module trim, dependency close.

Uses frozen WHOLE_BOOK_STAGE_CATALOG only. Does not rename stages or invent
parallel stage keys.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from app.narrative_core.contracts.stage import WholeBookStageDefinition, WholeBookStagePlan
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.whole_book_stages import WHOLE_BOOK_STAGE_CATALOG

# Pipeline scaffolding always retained even when modules are trimmed.
REQUIRED_SCAFFOLD_STAGES: frozenset[WholeBookStageKey] = frozenset(
    {
        WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        WholeBookStageKey.RESOLVE_ENTITIES,
        WholeBookStageKey.VERIFY_EVIDENCE,
        WholeBookStageKey.PERSIST_NARRATIVE_ASSETS,
    }
)

# ---------------------------------------------------------------------------
# Dual mapping contract (do not collapse into one table):
#
# 1) ENGINE_MODULE_PLANNING_STAGES
#    Engine planning seeds — primary *analysis* stages to schedule when a
#    module is requested. Scaffold + DAG close applied in build_whole_book_stage_plan.
#
# 2) PRODUCT_MODULE_STAGE_DEPENDENCIES (product_contract.keys)
#    Product result dependencies — stages that gate module status / viewability.
#    Must be a subset of Engine Planning Closure (validated in mapping_consistency).
#
# Result projection MUST use PRODUCT_MODULE_STAGE_DEPENDENCIES.
# Engine plan builders MUST use ENGINE_MODULE_PLANNING_STAGES.
# ---------------------------------------------------------------------------

# Module → analysis stage seeds (scaffold stages added separately).
ENGINE_MODULE_PLANNING_STAGES: Mapping[WholeBookModuleKey, tuple[WholeBookStageKey, ...]] = {
    WholeBookModuleKey.BOOK_OVERVIEW: (WholeBookStageKey.ANALYZE_STRUCTURE,),
    WholeBookModuleKey.STRUCTURE_STAGES: (WholeBookStageKey.ANALYZE_STRUCTURE,),
    WholeBookModuleKey.CHAPTER_FUNCTIONS: (WholeBookStageKey.ANALYZE_STRUCTURE,),
    WholeBookModuleKey.STORYLINES: (WholeBookStageKey.ANALYZE_STORYLINES,),
    WholeBookModuleKey.CHARACTERS: (WholeBookStageKey.ANALYZE_CHARACTERS,),
    WholeBookModuleKey.CHARACTER_ARCS: (WholeBookStageKey.ANALYZE_CHARACTERS,),
    WholeBookModuleKey.RELATIONSHIPS: (
        WholeBookStageKey.ANALYZE_CHARACTERS,
        WholeBookStageKey.ANALYZE_HOOKS,
    ),
    WholeBookModuleKey.HOOKS_PAYOFFS: (WholeBookStageKey.ANALYZE_HOOKS,),
    WholeBookModuleKey.CAUSAL_CHAIN: (WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,),
    WholeBookModuleKey.BASIC_TIMELINE: (WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,),
    WholeBookModuleKey.DIAGNOSTICS: (WholeBookStageKey.GENERATE_DIAGNOSTICS,),
}

# Deprecated alias — prefer ENGINE_MODULE_PLANNING_STAGES.
MODULE_TO_STAGES = ENGINE_MODULE_PLANNING_STAGES

_CATALOG_BY_KEY: dict[WholeBookStageKey, WholeBookStageDefinition] = {
    stage.stage_key: stage for stage in WHOLE_BOOK_STAGE_CATALOG
}


def detect_dependency_cycle(
    definitions: Sequence[WholeBookStageDefinition],
) -> list[WholeBookStageKey]:
    """Return one cycle path if the dependency graph has a cycle; else []."""

    deps: dict[WholeBookStageKey, tuple[WholeBookStageKey, ...]] = {
        d.stage_key: d.depends_on for d in definitions
    }
    visiting: set[WholeBookStageKey] = set()
    visited: set[WholeBookStageKey] = set()
    stack: list[WholeBookStageKey] = []

    def dfs(node: WholeBookStageKey) -> list[WholeBookStageKey] | None:
        if node in visited:
            return None
        if node in visiting:
            if node in stack:
                idx = stack.index(node)
                return stack[idx:] + [node]
            return [node, node]
        visiting.add(node)
        stack.append(node)
        for dep in deps.get(node, ()):
            found = dfs(dep)
            if found is not None:
                return found
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for key in deps:
        cycle = dfs(key)
        if cycle:
            return cycle
    return []


def _normalize_module(raw: WholeBookModuleKey | str) -> WholeBookModuleKey:
    if isinstance(raw, WholeBookModuleKey):
        return raw
    try:
        return WholeBookModuleKey(str(raw))
    except ValueError as exc:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED,
            f"unsupported module: {raw}",
        ) from exc


def _close_dependencies(selected: set[WholeBookStageKey]) -> set[WholeBookStageKey]:
    closed = set(selected)
    changed = True
    while changed:
        changed = False
        for key in list(closed):
            definition = _CATALOG_BY_KEY.get(key)
            if definition is None:
                continue
            for dep in definition.depends_on:
                if dep not in closed:
                    closed.add(dep)
                    changed = True
    return closed


def stage_definitions_to_run_stage_keys(
    stages: Sequence[WholeBookStageDefinition],
) -> list[str]:
    """Convert ordered plan definitions into AnalysisRunStage initialization keys."""

    return [stage.stage_key.value for stage in stages]


def build_whole_book_stage_plan(
    *,
    mode: WholeBookAnalysisMode,
    requested_modules: Sequence[WholeBookModuleKey | str] = (),
    supported_modules: Iterable[WholeBookModuleKey] | None = None,
) -> WholeBookStagePlan:
    """Build a stable-ordered, dependency-closed stage plan.

    Empty ``requested_modules`` → full frozen catalog.
    Unsupported modules raise ``WHOLE_BOOK_MODULE_NOT_SUPPORTED``.
    """

    supported = set(supported_modules) if supported_modules is not None else set(WholeBookModuleKey)
    selected: set[WholeBookStageKey] = set()

    if not requested_modules:
        selected = {stage.stage_key for stage in WHOLE_BOOK_STAGE_CATALOG}
    else:
        for raw in requested_modules:
            module = _normalize_module(raw)
            if module not in supported:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED,
                    f"engine does not support module: {module.value}",
                )
            selected.update(ENGINE_MODULE_PLANNING_STAGES.get(module, ()))
        selected |= REQUIRED_SCAFFOLD_STAGES
        # Catalog entries marked required stay even if not mapped from modules.
        for stage in WHOLE_BOOK_STAGE_CATALOG:
            if stage.required and stage.stage_key in REQUIRED_SCAFFOLD_STAGES:
                selected.add(stage.stage_key)

    selected = _close_dependencies(selected)

    ordered = tuple(
        stage for stage in WHOLE_BOOK_STAGE_CATALOG if stage.stage_key in selected
    )
    cycle = detect_dependency_cycle(ordered)
    if cycle:
        path = " -> ".join(k.value for k in cycle)
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
            f"stage dependency cycle detected: {path}",
        )

    return WholeBookStagePlan(mode=mode, stages=ordered)


__all__ = [
    "REQUIRED_SCAFFOLD_STAGES",
    "ENGINE_MODULE_PLANNING_STAGES",
    "MODULE_TO_STAGES",
    "build_whole_book_stage_plan",
    "detect_dependency_cycle",
    "stage_definitions_to_run_stage_keys",
]
