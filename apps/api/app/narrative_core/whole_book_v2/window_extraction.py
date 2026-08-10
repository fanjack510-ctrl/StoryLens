"""Real Provider window extraction — evidence catalog + structured primitives.

Deterministic code builds evidence IDs/excerpts. The Provider returns only
``evidence_ids`` plus short semantic fields. Scaffold extractors are not
production formal results.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import EvidenceRef
from .pipeline import WindowExtractionAsset, WindowPlan

ORIGIN_REAL = "real_provider"
ORIGIN_SCAFFOLD = "deterministic_scaffold"
ORIGIN_FIXTURE = "fixture"
ORIGIN_MOCK = "mock"

SCAFFOLD_MARKERS = (
    "悬念@",
    "阶段起点",
    "围绕目标、阻力与选择形成完整阶段",
    "推进核心目标",
    "外部阻力与内部犹豫",
    "承担代价以换取推进",
    "失去既有安全",
    "获得新线索或能力",
)


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderWindowExtractionPayload(M):
    """Provider-facing window schema. Evidence text is never model-authored."""

    events: list[str] = Field(default_factory=list)
    event_causality: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    character_states: list[str] = Field(default_factory=list)
    character_changes: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    protagonist_goals: list[str] = Field(default_factory=list)
    protagonist_obstacles: list[str] = Field(default_factory=list)
    protagonist_choices: list[str] = Field(default_factory=list)
    cost_paid: list[str] = Field(default_factory=list)
    gain_received: list[str] = Field(default_factory=list)
    ability_changes: list[str] = Field(default_factory=list)
    identity_changes: list[str] = Field(default_factory=list)
    belief_value_changes: list[str] = Field(default_factory=list)
    suspense_hooks: list[str] = Field(default_factory=list)
    hook_progression: list[str] = Field(default_factory=list)
    hook_payoff: list[str] = Field(default_factory=list)
    story_signals: list[str] = Field(default_factory=list)
    pacing_signals: dict[str, float] = Field(default_factory=dict)
    chapter_functions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


def build_window_evidence_catalog(
    window: WindowPlan,
    chapters: list[Any],
    *,
    excerpt_chars: int = 48,
) -> list[EvidenceRef]:
    """Deterministic evidence rows for one window. Provider may only cite these IDs."""
    by_id = {int(c.chapter_id): c for c in chapters}
    catalog: list[EvidenceRef] = []
    for cid in window.chapter_ids:
        c = by_id.get(int(cid))
        if c is None:
            continue
        text = str(getattr(c, "text", "") or "")
        excerpt = text[: min(excerpt_chars, len(text))]
        catalog.append(
            EvidenceRef(
                evidence_id=f"E-{c.chapter_id}-0",
                snapshot_id=int(c.snapshot_id),
                revision_hash=str(c.revision_hash),
                chapter_id=int(c.chapter_id),
                chapter_index=int(c.chapter_index),
                chapter_title=str(c.title),
                start_offset=0,
                end_offset=len(excerpt),
                quote_or_excerpt=excerpt,
                reason="window evidence catalog",
            )
        )
    return catalog


def validate_evidence_ids(evidence_ids: list[str], catalog: list[EvidenceRef]) -> None:
    known = {e.evidence_id for e in catalog}
    missing = [x for x in evidence_ids if x not in known]
    if missing:
        raise ValueError(f"unknown evidence_ids: {missing[:5]}")


def contains_scaffold_semantics(payload: dict[str, Any] | ProviderWindowExtractionPayload | WindowExtractionAsset) -> bool:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json")
    else:
        data = dict(payload)
    blob = " ".join(
        str(x)
        for key, value in data.items()
        if key not in {"evidence", "pacing_signals", "window_id", "origin", "availability"}
        for x in (value if isinstance(value, list) else [value])
    )
    return any(marker in blob for marker in SCAFFOLD_MARKERS)


def materialize_window_asset_from_provider(
    *,
    window: WindowPlan,
    catalog: list[EvidenceRef],
    payload: ProviderWindowExtractionPayload | dict[str, Any],
    provider: str,
    model: str,
    origin: Literal["real_provider", "fixture", "mock"] = ORIGIN_REAL,
    provider_request_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> WindowExtractionAsset:
    parsed = (
        payload
        if isinstance(payload, ProviderWindowExtractionPayload)
        else ProviderWindowExtractionPayload.model_validate(payload)
    )
    validate_evidence_ids(list(parsed.evidence_ids), catalog)
    if not parsed.evidence_ids:
        # Require at least one catalog citation so empty hallucinated assets fail closed.
        raise ValueError("window extraction requires evidence_ids from catalog")
    # Persist the full deterministic catalog on the asset so later synthesis can cite
    # any chapter in the window. Provider may only return evidence_ids for claims.
    evidence = list(catalog)
    asset = WindowExtractionAsset(
        window_id=window.window_id,
        events=list(parsed.events)[:40],
        event_causality=list(parsed.event_causality)[:40],
        characters=list(parsed.characters)[:40],
        character_states=list(parsed.character_states)[:40],
        character_changes=list(parsed.character_changes)[:40],
        relationships=list(parsed.relationships)[:40],
        relationship_changes=list(parsed.relationship_changes)[:40],
        protagonist_goals=list(parsed.protagonist_goals)[:20],
        protagonist_obstacles=list(parsed.protagonist_obstacles)[:20],
        protagonist_choices=list(parsed.protagonist_choices)[:20],
        cost_paid=list(parsed.cost_paid)[:20],
        gain_received=list(parsed.gain_received)[:20],
        ability_changes=list(parsed.ability_changes)[:20],
        identity_changes=list(parsed.identity_changes)[:20],
        belief_value_changes=list(parsed.belief_value_changes)[:20],
        suspense_hooks=list(parsed.suspense_hooks)[:20],
        hook_progression=list(parsed.hook_progression)[:20],
        hook_payoff=list(parsed.hook_payoff)[:20],
        story_signals=list(parsed.story_signals)[:20],
        pacing_signals=dict(list(parsed.pacing_signals.items())[:12]),
        chapter_functions=list(parsed.chapter_functions)[:40],
        evidence=evidence,
        start_chapter_index=window.start_chapter_index,
        end_chapter_index=window.end_chapter_index,
        origin=origin,
        provider=provider,
        model=model,
        provider_request_id=provider_request_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    if contains_scaffold_semantics(asset):
        raise ValueError("provider window extraction looks like deterministic scaffold")
    return asset


def parse_provider_window_payload(raw: dict[str, Any]) -> ProviderWindowExtractionPayload:
    try:
        return ProviderWindowExtractionPayload.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"window extraction schema mismatch: {exc}") from exc


def is_reusable_real_provider_intermediate(value: Any) -> bool:
    origin = getattr(value, "origin", None)
    if origin is None and isinstance(value, dict):
        origin = value.get("origin")
    return origin == ORIGIN_REAL


__all__ = [
    "ORIGIN_FIXTURE",
    "ORIGIN_MOCK",
    "ORIGIN_REAL",
    "ORIGIN_SCAFFOLD",
    "ProviderWindowExtractionPayload",
    "build_window_evidence_catalog",
    "contains_scaffold_semantics",
    "is_reusable_real_provider_intermediate",
    "materialize_window_asset_from_provider",
    "parse_provider_window_payload",
    "validate_evidence_ids",
]
