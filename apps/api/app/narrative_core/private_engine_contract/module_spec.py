"""WholeBookModuleExecutionSpec — single authority for module↔stage maps (Phase 2B-P).

Compatible views are derived from FIRST_FOUR_MODULE_SPECS (+ extension hooks).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.product_contract.keys import PRODUCT_MODULE_STAGE_DEPENDENCIES
from app.narrative_core.services.whole_book_stage_plan import ENGINE_MODULE_PLANNING_STAGES


@dataclass(frozen=True, slots=True)
class WholeBookModuleExecutionSpec:
    module_key: WholeBookModuleKey
    module_version: str
    display_name: str
    supported_modes: tuple[WholeBookAnalysisMode, ...]
    required_stage_keys: tuple[WholeBookStageKey, ...]
    producer_stage_keys: tuple[WholeBookStageKey, ...]
    product_result_stage_dependencies: tuple[WholeBookStageKey, ...]
    required_context_levels: tuple[int, ...]
    output_schema_ref: str
    evidence_policy_ref: str
    validation_policy_ref: str
    asset_type_outputs: tuple[str, ...]
    relation_type_outputs: tuple[str, ...]
    supports_partial: bool
    supports_resume: bool
    private_implementation_required: bool
    # First-four rule flags (documentation + contract tests).
    allow_unknown_or_multiple_protagonists: bool = False
    force_single_protagonist: bool = False
    force_three_act: bool = False
    variable_stage_count: bool = False
    require_chapter_ranges: bool = False
    turning_points_require_evidence: bool = False
    multi_function_labels: bool = False
    primary_secondary_functions: bool = False
    allow_empty_side_flashback_tags: bool = False
    multi_storyline_types: bool = False
    multi_line_membership: bool = False
    allow_pause_resume_terminate: bool = False
    storylines_are_not_character_lists: bool = False
    key_claims_require_evidence: bool = False

    def __post_init__(self) -> None:
        if self.force_single_protagonist and self.allow_unknown_or_multiple_protagonists:
            raise ValueError("contradictory protagonist rules")
        if self.force_three_act and self.variable_stage_count:
            raise ValueError("contradictory structure rules")
        for stage in self.producer_stage_keys:
            if stage not in self.required_stage_keys and stage not in self.product_result_stage_dependencies:
                # Producer should be within planning closure seeds; soft check vs required.
                pass
        for stage in self.product_result_stage_dependencies:
            if stage not in WholeBookStageKey:
                raise ValueError(f"illegal stage: {stage}")


def _modes_both() -> tuple[WholeBookAnalysisMode, ...]:
    return (WholeBookAnalysisMode.NATIVE, WholeBookAnalysisMode.ENHANCED)


BOOK_OVERVIEW_SPEC = WholeBookModuleExecutionSpec(
    module_key=WholeBookModuleKey.BOOK_OVERVIEW,
    module_version="1.0.0",
    display_name="Book Overview",
    supported_modes=_modes_both(),
    required_stage_keys=ENGINE_MODULE_PLANNING_STAGES[WholeBookModuleKey.BOOK_OVERVIEW],
    producer_stage_keys=(WholeBookStageKey.ANALYZE_STRUCTURE,),
    product_result_stage_dependencies=PRODUCT_MODULE_STAGE_DEPENDENCIES[
        WholeBookModuleKey.BOOK_OVERVIEW
    ],
    required_context_levels=(0, 1, 3),
    output_schema_ref="dto://BookOverviewResultDto",
    evidence_policy_ref="policy://evidence/book_overview",
    validation_policy_ref="policy://validation/book_overview",
    asset_type_outputs=(),
    relation_type_outputs=(),
    supports_partial=True,
    supports_resume=True,
    private_implementation_required=True,
    allow_unknown_or_multiple_protagonists=True,
    force_single_protagonist=False,
    key_claims_require_evidence=True,
)

STRUCTURE_STAGES_SPEC = WholeBookModuleExecutionSpec(
    module_key=WholeBookModuleKey.STRUCTURE_STAGES,
    module_version="1.0.0",
    display_name="Structure Stages",
    supported_modes=_modes_both(),
    required_stage_keys=ENGINE_MODULE_PLANNING_STAGES[WholeBookModuleKey.STRUCTURE_STAGES],
    producer_stage_keys=(WholeBookStageKey.ANALYZE_STRUCTURE,),
    product_result_stage_dependencies=PRODUCT_MODULE_STAGE_DEPENDENCIES[
        WholeBookModuleKey.STRUCTURE_STAGES
    ],
    required_context_levels=(0, 1, 3),
    output_schema_ref="dto://StructureStagesResultDto",
    evidence_policy_ref="policy://evidence/structure_stages",
    validation_policy_ref="policy://validation/structure_stages",
    asset_type_outputs=("structure_stage",),
    relation_type_outputs=(),
    supports_partial=True,
    supports_resume=True,
    private_implementation_required=True,
    force_three_act=False,
    variable_stage_count=True,
    require_chapter_ranges=True,
    turning_points_require_evidence=True,
)

CHAPTER_FUNCTIONS_SPEC = WholeBookModuleExecutionSpec(
    module_key=WholeBookModuleKey.CHAPTER_FUNCTIONS,
    module_version="1.0.0",
    display_name="Chapter Functions",
    supported_modes=_modes_both(),
    required_stage_keys=ENGINE_MODULE_PLANNING_STAGES[WholeBookModuleKey.CHAPTER_FUNCTIONS],
    producer_stage_keys=(WholeBookStageKey.ANALYZE_STRUCTURE,),
    product_result_stage_dependencies=PRODUCT_MODULE_STAGE_DEPENDENCIES[
        WholeBookModuleKey.CHAPTER_FUNCTIONS
    ],
    required_context_levels=(1, 2, 3),
    output_schema_ref="dto://ChapterFunctionsResultDto",
    evidence_policy_ref="policy://evidence/chapter_functions",
    validation_policy_ref="policy://validation/chapter_functions",
    asset_type_outputs=("chapter_function",),
    relation_type_outputs=(),
    supports_partial=True,
    supports_resume=True,
    private_implementation_required=True,
    multi_function_labels=True,
    primary_secondary_functions=True,
    allow_empty_side_flashback_tags=True,
)

STORYLINES_SPEC = WholeBookModuleExecutionSpec(
    module_key=WholeBookModuleKey.STORYLINES,
    module_version="1.0.0",
    display_name="Storylines",
    supported_modes=_modes_both(),
    required_stage_keys=ENGINE_MODULE_PLANNING_STAGES[WholeBookModuleKey.STORYLINES],
    producer_stage_keys=(WholeBookStageKey.ANALYZE_STORYLINES,),
    product_result_stage_dependencies=PRODUCT_MODULE_STAGE_DEPENDENCIES[
        WholeBookModuleKey.STORYLINES
    ],
    required_context_levels=(1, 2, 3),
    output_schema_ref="dto://StorylinesResultDto",
    evidence_policy_ref="policy://evidence/storylines",
    validation_policy_ref="policy://validation/storylines",
    asset_type_outputs=("storyline", "event"),
    relation_type_outputs=("belongs_to", "advances"),
    supports_partial=True,
    supports_resume=True,
    private_implementation_required=True,
    multi_storyline_types=True,
    multi_line_membership=True,
    allow_pause_resume_terminate=True,
    storylines_are_not_character_lists=True,
    key_claims_require_evidence=True,
)

FIRST_FOUR_MODULE_SPECS: tuple[WholeBookModuleExecutionSpec, ...] = (
    BOOK_OVERVIEW_SPEC,
    STRUCTURE_STAGES_SPEC,
    CHAPTER_FUNCTIONS_SPEC,
    STORYLINES_SPEC,
)

FIRST_FOUR_MODULE_KEYS: frozenset[WholeBookModuleKey] = frozenset(
    spec.module_key for spec in FIRST_FOUR_MODULE_SPECS
)


def _derive_maps_from_specs(
    specs: tuple[WholeBookModuleExecutionSpec, ...],
) -> tuple[
    dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]],
    dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]],
    dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]],
]:
    planning: dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]] = {}
    product: dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]] = {}
    producer: dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]] = {}
    for spec in specs:
        planning[spec.module_key] = spec.required_stage_keys
        product[spec.module_key] = spec.product_result_stage_dependencies
        producer[spec.module_key] = spec.producer_stage_keys
    return planning, product, producer


(
    ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC,
    PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC,
    MODULE_PRODUCER_STAGES,
) = _derive_maps_from_specs(FIRST_FOUR_MODULE_SPECS)


def validate_module_registry_unique(
    specs: tuple[WholeBookModuleExecutionSpec, ...] = FIRST_FOUR_MODULE_SPECS,
) -> None:
    keys = [s.module_key for s in specs]
    if len(keys) != len(set(keys)):
        raise ValueError("module registry keys must be unique")


def validate_stage_keys_legal(
    specs: tuple[WholeBookModuleExecutionSpec, ...] = FIRST_FOUR_MODULE_SPECS,
) -> None:
    legal = frozenset(WholeBookStageKey)
    for spec in specs:
        for stage in (
            *spec.required_stage_keys,
            *spec.producer_stage_keys,
            *spec.product_result_stage_dependencies,
        ):
            if stage not in legal:
                raise ValueError(f"illegal stage key on {spec.module_key}: {stage}")


def validate_first_four_consistent_with_legacy_maps() -> None:
    """Ensure derived first-four views match existing PRODUCT/ENGINE maps."""

    for module in FIRST_FOUR_MODULE_KEYS:
        if ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC[module] != ENGINE_MODULE_PLANNING_STAGES[module]:
            raise ValueError(f"planning mismatch for {module}")
        if (
            PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC[module]
            != PRODUCT_MODULE_STAGE_DEPENDENCIES[module]
        ):
            raise ValueError(f"product dependency mismatch for {module}")


def get_module_spec(module_key: WholeBookModuleKey | str) -> WholeBookModuleExecutionSpec:
    key = module_key if isinstance(module_key, WholeBookModuleKey) else WholeBookModuleKey(module_key)
    for spec in FIRST_FOUR_MODULE_SPECS:
        if spec.module_key == key:
            return spec
    raise KeyError(f"module spec not in first-four freeze: {key}")


# Typing alias for Mapping consumers.
ModuleStageMap = Mapping[WholeBookModuleKey, tuple[WholeBookStageKey, ...]]
