"""Automatic consistency checks for Engine Planning vs Product Result Dependencies.

Product Result Dependencies must be a subset of Engine Planning Closure for every
formal Module. Stage/Module keys must come from unified registries.
"""

from __future__ import annotations

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.product_contract.keys import (
    PRODUCT_MODULE_STAGE_DEPENDENCIES,
    WHOLE_BOOK_MODULE_KEYS,
)
from app.narrative_core.services.whole_book_stage_plan import (
    ENGINE_MODULE_PLANNING_STAGES,
    build_whole_book_stage_plan,
)
from app.narrative_core.whole_book_stages import WHOLE_BOOK_STAGE_CATALOG

_CATALOG_KEYS = frozenset(stage.stage_key for stage in WHOLE_BOOK_STAGE_CATALOG)
_MODULE_KEYS = frozenset(WHOLE_BOOK_MODULE_KEYS)


def engine_planning_closure_for_module(
    module: WholeBookModuleKey,
    *,
    mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE,
) -> frozenset[WholeBookStageKey]:
    """Stages that would be scheduled when only ``module`` is requested."""

    plan = build_whole_book_stage_plan(mode=mode, requested_modules=(module,))
    return frozenset(stage.stage_key for stage in plan.stages)


def validate_module_stage_mapping_consistency() -> list[str]:
    """Return human-readable violation messages (empty = ok)."""

    errors: list[str] = []

    planning_modules = frozenset(ENGINE_MODULE_PLANNING_STAGES)
    product_modules = frozenset(PRODUCT_MODULE_STAGE_DEPENDENCIES)

    missing_planning = _MODULE_KEYS - planning_modules
    missing_product = _MODULE_KEYS - product_modules
    if missing_planning:
        errors.append(f"ENGINE_MODULE_PLANNING_STAGES missing modules: {sorted(m.value for m in missing_planning)}")
    if missing_product:
        errors.append(
            f"PRODUCT_MODULE_STAGE_DEPENDENCIES missing modules: {sorted(m.value for m in missing_product)}"
        )
    extra_planning = planning_modules - _MODULE_KEYS
    extra_product = product_modules - _MODULE_KEYS
    if extra_planning:
        errors.append(
            f"ENGINE_MODULE_PLANNING_STAGES unknown modules: {sorted(m.value for m in extra_planning)}"
        )
    if extra_product:
        errors.append(
            f"PRODUCT_MODULE_STAGE_DEPENDENCIES unknown modules: {sorted(m.value for m in extra_product)}"
        )

    for module, stages in ENGINE_MODULE_PLANNING_STAGES.items():
        unknown = [s for s in stages if s not in _CATALOG_KEYS]
        if unknown:
            errors.append(
                f"ENGINE planning for {module.value} has unknown stages: "
                + ", ".join(s.value for s in unknown)
            )

    for module, stages in PRODUCT_MODULE_STAGE_DEPENDENCIES.items():
        unknown = [s for s in stages if s not in _CATALOG_KEYS]
        if unknown:
            errors.append(
                f"PRODUCT deps for {module.value} have unknown stages: "
                + ", ".join(s.value for s in unknown)
            )
        if module not in ENGINE_MODULE_PLANNING_STAGES:
            continue
        closure = engine_planning_closure_for_module(module)
        outside = [s for s in stages if s not in closure]
        if outside:
            errors.append(
                f"PRODUCT deps for {module.value} not in Engine Planning Closure: "
                + ", ".join(s.value for s in outside)
            )

    return errors


def assert_module_stage_mapping_consistency() -> None:
    errors = validate_module_stage_mapping_consistency()
    if errors:
        raise AssertionError(
            "Module/Stage mapping consistency failed:\n- " + "\n- ".join(errors)
        )


__all__ = [
    "assert_module_stage_mapping_consistency",
    "engine_planning_closure_for_module",
    "validate_module_stage_mapping_consistency",
]
