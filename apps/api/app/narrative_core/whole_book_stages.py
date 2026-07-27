"""Frozen WholeBook stage catalog (Phase 1C-P DAG).

These are runtime protocol stages — not implemented analysis algorithms.
"""

from __future__ import annotations

from app.narrative_core.contracts.stage import WholeBookStageDefinition
from app.narrative_core.enums import CostClass, WholeBookStageKey

WHOLE_BOOK_STAGE_CATALOG: tuple[WholeBookStageDefinition, ...] = (
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        display_name="Build fulltext index",
        order=10,
        description="Index snapshot paragraphs for downstream analysis.",
        depends_on=(),
        estimated_cost_class=CostClass.LOW,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.RESOLVE_ENTITIES,
        display_name="Resolve entities",
        order=20,
        description="Extract and reconcile narrative entities.",
        depends_on=(WholeBookStageKey.BUILD_FULLTEXT_INDEX,),
        estimated_cost_class=CostClass.MEDIUM,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.ANALYZE_STRUCTURE,
        display_name="Analyze structure",
        order=30,
        description="Book-level structure and chapter functions.",
        depends_on=(WholeBookStageKey.RESOLVE_ENTITIES,),
        estimated_cost_class=CostClass.MEDIUM,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.ANALYZE_STORYLINES,
        display_name="Analyze storylines",
        order=40,
        description="Identify and track storylines.",
        depends_on=(WholeBookStageKey.ANALYZE_STRUCTURE,),
        estimated_cost_class=CostClass.HIGH,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.ANALYZE_CHARACTERS,
        display_name="Analyze characters",
        order=50,
        description="Character presence and arc staging.",
        depends_on=(WholeBookStageKey.RESOLVE_ENTITIES,),
        estimated_cost_class=CostClass.HIGH,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.ANALYZE_HOOKS,
        display_name="Analyze hooks and payoffs",
        order=60,
        description="Foreshadowing, hooks, and payoff chains.",
        depends_on=(
            WholeBookStageKey.ANALYZE_STRUCTURE,
            WholeBookStageKey.ANALYZE_CHARACTERS,
        ),
        estimated_cost_class=CostClass.HIGH,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,
        display_name="Analyze causality and timeline",
        order=70,
        description="Causal chain and basic timeline.",
        depends_on=(
            WholeBookStageKey.ANALYZE_STORYLINES,
            WholeBookStageKey.ANALYZE_HOOKS,
        ),
        estimated_cost_class=CostClass.HIGH,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.GENERATE_DIAGNOSTICS,
        display_name="Generate diagnostics",
        order=80,
        description="Consolidate module outputs into diagnostics.",
        depends_on=(WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE,),
        estimated_cost_class=CostClass.MEDIUM,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.VERIFY_EVIDENCE,
        display_name="Verify evidence",
        order=90,
        description="Validate paragraph evidence bindings.",
        depends_on=(WholeBookStageKey.GENERATE_DIAGNOSTICS,),
        estimated_cost_class=CostClass.LOW,
    ),
    WholeBookStageDefinition(
        stage_key=WholeBookStageKey.PERSIST_NARRATIVE_ASSETS,
        display_name="Persist narrative assets",
        order=100,
        description="Write candidate assets via NarrativeAssetWriter (never auto-confirm).",
        depends_on=(WholeBookStageKey.VERIFY_EVIDENCE,),
        estimated_cost_class=CostClass.LOW,
    ),
)

ORDERED_STAGE_KEYS: tuple[WholeBookStageKey, ...] = tuple(
    stage.stage_key for stage in WHOLE_BOOK_STAGE_CATALOG
)
