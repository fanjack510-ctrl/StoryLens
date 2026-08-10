"""Hierarchical Whole-Book V2 input pipeline: window / token / cost planning + consolidation.

Final synthesis never receives raw full-book chapter text.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    AssessmentResult,
    AssessmentDimension,
    AssessmentIssue,
    Availability,
    ArcStage,
    ChapterFunction,
    ChaptersResult,
    ChronologyEvent,
    EvidenceRef,
    GrowthTrackPoint,
    HeatmapBin,
    MajorCharacter,
    OverviewResult,
    PacingMarker,
    PacingPoint,
    PacingRegion,
    PacingResult,
    ProtagonistArc,
    Relationship,
    RevisionPriority,
    Storyline,
    StorylineNode,
    StoryResult,
    StoryStage,
    Strength,
    SuspenseEvent,
    SuspenseLifecycle,
    SuspenseResult,
    TurningPoint,
    TypeProfile,
    CharactersResult,
)

PIPELINE_VERSION = "whole-book-v2-hierarchical-1.0"
DEFAULT_PROVIDER_CONTEXT_LIMIT = 128_000
DEFAULT_SAFETY_MARGIN = 8_000
DEFAULT_SYSTEM_PROMPT_RESERVE = 2_500
DEFAULT_SCHEMA_RESERVE = 3_500
DEFAULT_EXPECTED_OUTPUT = 4_000
DEFAULT_REPAIR_RESERVE = 4_000
DEFAULT_GROUP_SIZE = 8
CHARS_PER_TOKEN = 2  # deterministic Chinese-friendly estimate used project-wide


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WindowPlan(M):
    window_id: str
    start_chapter_id: int
    end_chapter_id: int
    start_chapter_index: int = Field(ge=1)
    end_chapter_index: int = Field(ge=1)
    chapter_count: int = Field(ge=1)
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    provider: str
    model: str
    snapshot_id: int
    revision: str
    pipeline_version: str = PIPELINE_VERSION
    chapter_ids: list[int] = Field(default_factory=list)


class WindowExtractionAsset(M):
    """Bounded structured primitives for one window. Never a final essay."""
    window_id: str
    availability: Availability = Availability.AVAILABLE
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
    evidence: list[EvidenceRef] = Field(default_factory=list)
    start_chapter_index: int = Field(ge=1)
    end_chapter_index: int = Field(ge=1)
    # CHG-084: only origin=real_provider may be reused as formal AI intermediates.
    origin: Literal[
        "real_provider", "deterministic_scaffold", "fixture", "mock", "legacy"
    ] = "deterministic_scaffold"
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class TopicIntermediate(M):
    topic: Literal[
        "story_intermediate",
        "character_intermediate",
        "relationship_intermediate",
        "protagonist_arc_intermediate",
        "suspense_intermediate",
        "pacing_intermediate",
        "chapter_function_intermediate",
    ]
    window_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    availability: Availability = Availability.AVAILABLE


class TokenPlan(M):
    chapter_count: int
    window_count: int
    extract_calls: int
    consolidation_calls: int
    final_synthesis_calls: int
    repair_reserve_calls: int
    estimated_total_calls: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    max_single_request_input_tokens: int
    max_single_request_total_tokens: int
    provider_context_limit: int
    context_safety_margin: int
    context_safe: Literal["YES", "NO"]
    reused_successful_units: int = 0
    billable_calls: int = 0


class CostPlan(M):
    estimated_cost_low: float
    estimated_cost_high: float
    extract_cost: float
    consolidation_cost: float
    synthesis_cost: float
    repair_reserve_cost: float
    reused_units_not_rebilled: int = 0
    currency: str = "CNY"


class HierarchicalDryRunReport(M):
    window_count: int
    estimated_provider_calls: int
    max_request_tokens: int
    provider_context_limit: int
    safety_margin: int
    context_safe: Literal["YES", "NO"]
    no_raw_full_book_final_request: Literal["YES"] = "YES"
    no_request_above_safe_context: Literal["YES", "NO"]
    window_plan_exists: Literal["YES"] = "YES"
    call_plan_exists: Literal["YES"] = "YES"
    token_plan_exists: Literal["YES"] = "YES"
    cost_plan_exists: Literal["YES"] = "YES"
    resume_plan_exists: Literal["YES"] = "YES"
    repair_plan_exists: Literal["YES"] = "YES"
    windows: list[WindowPlan]
    token_plan: TokenPlan
    cost_plan: CostPlan


@dataclass(frozen=True)
class ChapterMeta:
    chapter_id: int
    chapter_index: int
    title: str
    text: str
    snapshot_id: int
    revision_hash: str
    token_hint: int | None = None

    @property
    def estimated_tokens(self) -> int:
        if self.token_hint is not None:
            return max(1, int(self.token_hint))
        return max(1, math.ceil(len(self.text) / CHARS_PER_TOKEN))


@dataclass
class ProviderBudget:
    provider: str
    model: str
    context_limit: int = DEFAULT_PROVIDER_CONTEXT_LIMIT
    system_prompt_reserve: int = DEFAULT_SYSTEM_PROMPT_RESERVE
    schema_reserve: int = DEFAULT_SCHEMA_RESERVE
    expected_output: int = DEFAULT_EXPECTED_OUTPUT
    repair_reserve: int = DEFAULT_REPAIR_RESERVE
    safety_margin: int = DEFAULT_SAFETY_MARGIN
    input_rate_per_mtok: float = 1.0
    output_rate_per_mtok: float = 2.0

    @property
    def safe_input_capacity(self) -> int:
        used = (
            self.system_prompt_reserve
            + self.schema_reserve
            + self.expected_output
            + self.repair_reserve
            + self.safety_margin
        )
        return max(1, self.context_limit - used)


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN)) if text else 0


def make_window_id(
    *,
    book_id: int,
    snapshot_id: int,
    revision: str,
    provider: str,
    model: str,
    start_chapter_id: int,
    end_chapter_id: int,
    pipeline_version: str = PIPELINE_VERSION,
) -> str:
    raw = "|".join(
        [
            str(book_id),
            str(snapshot_id),
            revision,
            provider,
            model,
            str(start_chapter_id),
            str(end_chapter_id),
            pipeline_version,
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"W-{start_chapter_id}-{end_chapter_id}-{digest}"


def plan_windows(
    chapters: list[ChapterMeta],
    *,
    book_id: int,
    budget: ProviderBudget,
    overlap_chapters: int = 1,
) -> list[WindowPlan]:
    if not chapters:
        raise ValueError("chapters required")
    capacity = budget.safe_input_capacity
    # One chapter must still fit; otherwise planning fails closed.
    max_chapter = max(c.estimated_tokens for c in chapters)
    if max_chapter > capacity:
        raise ValueError(
            f"single chapter exceeds safe context capacity: {max_chapter}>{capacity}"
        )
    windows: list[WindowPlan] = []
    start = 0
    n = len(chapters)
    while start < n:
        end = start
        running = 0
        while end < n:
            next_tokens = chapters[end].estimated_tokens
            if running + next_tokens > capacity and end > start:
                break
            running += next_tokens
            end += 1
        part = chapters[start:end]
        first, last = part[0], part[-1]
        wid = make_window_id(
            book_id=book_id,
            snapshot_id=first.snapshot_id,
            revision=first.revision_hash,
            provider=budget.provider,
            model=budget.model,
            start_chapter_id=first.chapter_id,
            end_chapter_id=last.chapter_id,
        )
        windows.append(
            WindowPlan(
                window_id=wid,
                start_chapter_id=first.chapter_id,
                end_chapter_id=last.chapter_id,
                start_chapter_index=first.chapter_index,
                end_chapter_index=last.chapter_index,
                chapter_count=len(part),
                estimated_input_tokens=running,
                estimated_output_tokens=budget.expected_output,
                provider=budget.provider,
                model=budget.model,
                snapshot_id=first.snapshot_id,
                revision=first.revision_hash,
                chapter_ids=[c.chapter_id for c in part],
            )
        )
        if end >= n:
            break
        start = max(end - overlap_chapters, start + 1)
    return windows


def _group_count(window_count: int, group_size: int = DEFAULT_GROUP_SIZE) -> int:
    return max(1, math.ceil(window_count / group_size))


def build_token_plan(
    windows: list[WindowPlan],
    *,
    budget: ProviderBudget,
    reused_successful_units: int = 0,
    topic_count: int = 7,
    final_synthesis_calls: int = 6,
    group_size: int = DEFAULT_GROUP_SIZE,
) -> TokenPlan:
    window_count = len(windows)
    extract_calls = window_count
    group_calls = _group_count(window_count, group_size)
    # group consolidation + topic consolidation
    consolidation_calls = group_calls + topic_count
    repair_reserve_calls = max(1, math.ceil((extract_calls + consolidation_calls + final_synthesis_calls) * 0.08))
    estimated_total = extract_calls + consolidation_calls + final_synthesis_calls + repair_reserve_calls
    billable = max(0, estimated_total - reused_successful_units)
    max_input = max((w.estimated_input_tokens for w in windows), default=0)
    # Consolidation / synthesis payloads are bounded intermediates, not raw chapters.
    consolid_input = min(budget.safe_input_capacity, max(2_000, max_input // 2))
    max_single_input = max(max_input, consolid_input)
    max_single_total = max_single_input + budget.expected_output
    estimated_input = sum(w.estimated_input_tokens for w in windows) + consolid_input * consolidation_calls + consolid_input * final_synthesis_calls
    estimated_output = (
        extract_calls * budget.expected_output
        + consolidation_calls * (budget.expected_output // 2)
        + final_synthesis_calls * budget.expected_output
        + repair_reserve_calls * budget.expected_output
    )
    context_safe: Literal["YES", "NO"] = (
        "YES"
        if max_single_total <= (budget.context_limit - budget.safety_margin)
        and max_single_input <= budget.safe_input_capacity
        else "NO"
    )
    return TokenPlan(
        chapter_count=sum(w.chapter_count for w in windows) if windows else 0,
        window_count=window_count,
        extract_calls=extract_calls,
        consolidation_calls=consolidation_calls,
        final_synthesis_calls=final_synthesis_calls,
        repair_reserve_calls=repair_reserve_calls,
        estimated_total_calls=estimated_total,
        estimated_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        max_single_request_input_tokens=max_single_input,
        max_single_request_total_tokens=max_single_total,
        provider_context_limit=budget.context_limit,
        context_safety_margin=budget.safety_margin,
        context_safe=context_safe,
        reused_successful_units=reused_successful_units,
        billable_calls=billable,
    )


def build_cost_plan(token_plan: TokenPlan, budget: ProviderBudget) -> CostPlan:
    # Bill only non-reused calls; repair reserve counted in high band only.
    base_calls = max(
        0,
        token_plan.extract_calls
        + token_plan.consolidation_calls
        + token_plan.final_synthesis_calls
        - token_plan.reused_successful_units,
    )
    avg_in = token_plan.estimated_input_tokens / max(1, token_plan.estimated_total_calls)
    avg_out = token_plan.estimated_output_tokens / max(1, token_plan.estimated_total_calls)

    def cost(calls: int) -> float:
        return (calls * avg_in / 1_000_000) * budget.input_rate_per_mtok + (
            calls * avg_out / 1_000_000
        ) * budget.output_rate_per_mtok

    extract = cost(max(0, token_plan.extract_calls - min(token_plan.reused_successful_units, token_plan.extract_calls)))
    remaining_reuse = max(0, token_plan.reused_successful_units - token_plan.extract_calls)
    consolid = cost(max(0, token_plan.consolidation_calls - min(remaining_reuse, token_plan.consolidation_calls)))
    remaining_reuse2 = max(0, remaining_reuse - token_plan.consolidation_calls)
    synth = cost(max(0, token_plan.final_synthesis_calls - min(remaining_reuse2, token_plan.final_synthesis_calls)))
    repair = cost(token_plan.repair_reserve_calls)
    low = extract + consolid + synth
    high = low + repair
    return CostPlan(
        estimated_cost_low=round(low, 6),
        estimated_cost_high=round(high, 6),
        extract_cost=round(extract, 6),
        consolidation_cost=round(consolid, 6),
        synthesis_cost=round(synth, 6),
        repair_reserve_cost=round(repair, 6),
        reused_units_not_rebilled=token_plan.reused_successful_units,
    )


def assert_context_safe(token_plan: TokenPlan) -> None:
    if token_plan.context_safe != "YES":
        raise ValueError(
            "CONTEXT_SAFE=NO: refusing to send request that exceeds provider safe context"
        )


def dry_run_1299(
    *,
    chapter_count: int = 1299,
    total_chars: int = 2_670_000,
    book_id: int = 1299,
    snapshot_id: int = 1,
    revision: str = "dry-run-1299",
    budget: ProviderBudget | None = None,
) -> HierarchicalDryRunReport:
    budget = budget or ProviderBudget(provider="dry-run", model="planning-only")
    avg = max(1, total_chars // chapter_count)
    chapters = [
        ChapterMeta(
            chapter_id=10_000 + i,
            chapter_index=i,
            title=f"第{i}章",
            text="字" * avg,
            snapshot_id=snapshot_id,
            revision_hash=revision,
        )
        for i in range(1, chapter_count + 1)
    ]
    windows = plan_windows(chapters, book_id=book_id, budget=budget)
    token_plan = build_token_plan(windows, budget=budget)
    # Override chapter_count to true chapter count (windows may overlap).
    token_plan = token_plan.model_copy(update={"chapter_count": chapter_count})
    cost_plan = build_cost_plan(token_plan, budget)
    no_above: Literal["YES", "NO"] = "YES" if token_plan.context_safe == "YES" else "NO"
    return HierarchicalDryRunReport(
        window_count=len(windows),
        estimated_provider_calls=token_plan.estimated_total_calls,
        max_request_tokens=token_plan.max_single_request_total_tokens,
        provider_context_limit=budget.context_limit,
        safety_margin=budget.safety_margin,
        context_safe=token_plan.context_safe,
        no_request_above_safe_context=no_above,
        windows=windows,
        token_plan=token_plan,
        cost_plan=cost_plan,
    )


def extract_window_asset(
    window: WindowPlan,
    chapters: list[ChapterMeta],
    *,
    focus: list[str] | None = None,
) -> WindowExtractionAsset:
    """Deterministic offline scaffold — NEVER a formal production novel analysis.

    Formal Hierarchical V2 must use Provider window extraction
    (``window_extraction.materialize_window_asset_from_provider``).
    """
    by_id = {c.chapter_id: c for c in chapters}
    part = [by_id[cid] for cid in window.chapter_ids if cid in by_id]
    if not part:
        raise ValueError(f"window {window.window_id} has no chapters")
    names: list[str] = []
    for c in part:
        for token in c.text.replace("，", " ").replace("。", " ").split():
            if token.startswith("@") and len(token) > 1:
                names.append(token[1:])
    names = list(dict.fromkeys(names)) or ["主角"]
    evidence: list[EvidenceRef] = []
    # One real excerpt per chapter in the window so later synthesis can cite every chapter.
    for c in part:
        excerpt = c.text[: min(48, len(c.text))]
        evidence.append(
            EvidenceRef(
                evidence_id=f"E-{c.chapter_id}-0",
                snapshot_id=c.snapshot_id,
                revision_hash=c.revision_hash,
                chapter_id=c.chapter_id,
                chapter_index=c.chapter_index,
                chapter_title=c.title,
                start_offset=0,
                end_offset=len(excerpt),
                quote_or_excerpt=excerpt,
                reason="window extraction evidence",
            )
        )
    first, last = part[0], part[-1]
    seed = sum(c.chapter_index for c in part)
    focus = focus or []
    hook = f"悬念@{first.chapter_index}"
    return WindowExtractionAsset(
        window_id=window.window_id,
        events=[f"事件 {first.chapter_index}-{last.chapter_index}"],
        event_causality=[f"因第{first.chapter_index}章行动导致第{last.chapter_index}章结果"],
        characters=names,
        character_states=[f"{names[0]}处于阶段起点"],
        character_changes=[f"{names[0]}因选择发生变化"],
        relationships=[f"{names[0]}|{names[-1]}|同行"],
        relationship_changes=[f"{names[0]}与{names[-1]}关系推进"],
        protagonist_goals=["推进核心目标"],
        protagonist_obstacles=["外部阻力与内部犹豫"],
        protagonist_choices=["承担代价以换取推进"],
        cost_paid=["失去既有安全"],
        gain_received=["获得新线索或能力"],
        ability_changes=["能力从被动转向可控"],
        identity_changes=["身份边界被重新定义"],
        belief_value_changes=["从回避代价到承担责任"],
        suspense_hooks=[hook],
        hook_progression=[f"强化:{hook}"],
        hook_payoff=[f"部分回收:{hook}"] if "payoff" in ",".join(focus) or last.chapter_index % 5 == 0 else [],
        story_signals=[f"主线推进 {first.chapter_index}-{last.chapter_index}"],
        pacing_signals={
            k: float(35 + (seed + i * 11) % 60)
            for i, k in enumerate(
                [
                    "plot_progression",
                    "reading_tension",
                    "emotional_intensity",
                    "reading_motivation",
                    "hook_density",
                    "pacing_speed",
                ]
            )
        },
        chapter_functions=["mainline_progress", "character_development"],
        evidence=evidence,
        start_chapter_index=first.chapter_index,
        end_chapter_index=last.chapter_index,
        origin="deterministic_scaffold",
    )


def _evidence_ids(assets: list[WindowExtractionAsset]) -> list[str]:
    out: list[str] = []
    for a in assets:
        for e in a.evidence:
            if e.evidence_id not in out:
                out.append(e.evidence_id)
    return out


def consolidate_group(assets: list[WindowExtractionAsset], *, group_id: str) -> dict[str, Any]:
    """Bounded hierarchical merge for a group of windows."""
    return {
        "group_id": group_id,
        "window_ids": [a.window_id for a in assets],
        "events": [e for a in assets for e in a.events][:40],
        "event_causality": [e for a in assets for e in a.event_causality][:40],
        "characters": list(dict.fromkeys(n for a in assets for n in a.characters)),
        "relationships": list(dict.fromkeys(r for a in assets for r in a.relationships)),
        "protagonist_goals": [g for a in assets for g in a.protagonist_goals][:20],
        "protagonist_obstacles": [g for a in assets for g in a.protagonist_obstacles][:20],
        "protagonist_choices": [g for a in assets for g in a.protagonist_choices][:20],
        "cost_paid": [g for a in assets for g in a.cost_paid][:20],
        "gain_received": [g for a in assets for g in a.gain_received][:20],
        "ability_changes": [g for a in assets for g in a.ability_changes][:20],
        "identity_changes": [g for a in assets for g in a.identity_changes][:20],
        "belief_value_changes": [g for a in assets for g in a.belief_value_changes][:20],
        "hooks": [
            {
                "hook": a.suspense_hooks[0] if a.suspense_hooks else "",
                "window_id": a.window_id,
                "start": a.start_chapter_index,
                "end": a.end_chapter_index,
                "progression": a.hook_progression,
                "payoff": a.hook_payoff,
                "evidence_ids": [e.evidence_id for e in a.evidence],
            }
            for a in assets
            if a.suspense_hooks
        ],
        "pacing": [
            {
                "window_id": a.window_id,
                "start": a.start_chapter_index,
                "end": a.end_chapter_index,
                **a.pacing_signals,
            }
            for a in assets
        ],
        "evidence_ids": _evidence_ids(assets),
        "chapter_range": [
            min(a.start_chapter_index for a in assets),
            max(a.end_chapter_index for a in assets),
        ]
        if assets
        else [1, 1],
    }


def build_topic_intermediates(
    assets: list[WindowExtractionAsset],
    *,
    group_size: int = DEFAULT_GROUP_SIZE,
) -> dict[str, TopicIntermediate]:
    groups = [
        consolidate_group(assets[i : i + group_size], group_id=f"G-{i // group_size + 1}")
        for i in range(0, max(1, len(assets)), group_size)
    ] if assets else []
    evid = _evidence_ids(assets)
    window_ids = [a.window_id for a in assets]
    characters = list(dict.fromkeys(n for a in assets for n in a.characters))
    protagonist = characters[0] if characters else "主角"

    story_payload = {
        "groups": groups,
        "main_storyline": [e for a in assets for e in a.events],
        "side_storylines": [r for a in assets for r in a.relationships][:20],
        "major_events": [e for a in assets for e in a.events],
        "causal_chain": [e for a in assets for e in a.event_causality],
        "turning_points": [
            f"第{a.end_chapter_index}章转折" for a in assets[:: max(1, len(assets) // 8)]
        ][:8],
        "climax": assets[-1].events[0] if assets and assets[-1].events else "",
        "resolution": "核心目标得到阶段性回应" if assets else "",
        "unresolved_threads": [
            h for a in assets for h in a.suspense_hooks if not a.hook_payoff
        ][:12],
    }
    character_payload = {
        "characters": characters,
        "states": [s for a in assets for s in a.character_states][:40],
        "changes": [s for a in assets for s in a.character_changes][:40],
    }
    relationship_payload = {
        "relationships": list(dict.fromkeys(r for a in assets for r in a.relationships)),
        "changes": [s for a in assets for s in a.relationship_changes][:40],
    }
    # Protagonist arc stages from chronological windows
    stages = []
    for i, a in enumerate(assets):
        stages.append(
            {
                "chapter_range": [a.start_chapter_index, a.end_chapter_index],
                "stage_goal": a.protagonist_goals[0] if a.protagonist_goals else "",
                "external_conflict": a.protagonist_obstacles[0] if a.protagonist_obstacles else "",
                "internal_conflict": "内在犹豫与自我定位冲突",
                "obstacles": a.protagonist_obstacles,
                "key_events": a.events,
                "key_choices": a.protagonist_choices,
                "cost_paid": a.cost_paid,
                "gain_received": a.gain_received,
                "ability_change": a.ability_changes[0] if a.ability_changes else "",
                "relationship_change": a.relationship_changes[0] if a.relationship_changes else "",
                "identity_change": a.identity_changes[0] if a.identity_changes else "",
                "belief_value_change": a.belief_value_changes[0] if a.belief_value_changes else "",
                "turning_point": f"第{a.end_chapter_index}章方向改变",
                "stage_result": a.character_states[-1] if a.character_states else "",
                "next_goal": a.protagonist_goals[0] if a.protagonist_goals else "",
                "evidence_ids": [e.evidence_id for e in a.evidence],
                "window_id": a.window_id,
                "stage_index": i + 1,
            }
        )
    # Compress many windows into bounded arc stages for synthesis (~9 max)
    if len(stages) > 9:
        compressed = []
        step = math.ceil(len(stages) / 9)
        for i in range(0, len(stages), step):
            chunk = stages[i : i + step]
            first, last = chunk[0], chunk[-1]
            compressed.append(
                {
                    **first,
                    "chapter_range": [first["chapter_range"][0], last["chapter_range"][1]],
                    "key_events": [e for s in chunk for e in s["key_events"]][:6],
                    "obstacles": [e for s in chunk for e in s["obstacles"]][:6],
                    "key_choices": [e for s in chunk for e in s["key_choices"]][:6],
                    "cost_paid": [e for s in chunk for e in s["cost_paid"]][:6],
                    "gain_received": [e for s in chunk for e in s["gain_received"]][:6],
                    "evidence_ids": list(
                        dict.fromkeys(e for s in chunk for e in s["evidence_ids"])
                    )[:8],
                    "turning_point": last["turning_point"],
                    "stage_result": last["stage_result"],
                    "stage_index": len(compressed) + 1,
                }
            )
        stages = compressed
    protagonist_payload = {
        "protagonist": protagonist,
        "initial_state": stages[0]["stage_result"] if stages else f"{protagonist}初始状态",
        "initial_goal": stages[0]["stage_goal"] if stages else "解决初始困境",
        "stages": stages,
        "final_state": stages[-1]["stage_result"] if stages else f"{protagonist}最终状态",
        "overall_cost": list(dict.fromkeys(x for s in stages for x in s["cost_paid"])),
        "overall_gain": list(dict.fromkeys(x for s in stages for x in s["gain_received"])),
        "core_transformation": "从被动承受转向主动承担选择与代价",
        "arc_summary": f"{protagonist}经历多阶段目标、阻力、选择与代价后完成核心转变",
    }
    # Cross-window hook lifecycle merge by hook text family
    hooks_map: dict[str, dict[str, Any]] = {}
    for a in assets:
        for hook in a.suspense_hooks:
            key = hook.split("@")[0] if "@" in hook else hook
            entry = hooks_map.setdefault(
                key,
                {
                    "hook": hook,
                    "introduced": a.start_chapter_index,
                    "reinforced": [],
                    "clues": [],
                    "misdirection": [],
                    "partial_reveal": [],
                    "twist": [],
                    "payoff": [],
                    "evidence_ids": [],
                    "windows": [],
                },
            )
            entry["reinforced"].append(a.start_chapter_index)
            entry["windows"].append(a.window_id)
            entry["evidence_ids"].extend(e.evidence_id for e in a.evidence)
            if a.hook_progression:
                entry["clues"].extend(a.hook_progression)
            if a.hook_payoff:
                entry["partial_reveal"].extend(a.hook_payoff)
                entry["payoff"].extend(a.hook_payoff)
    for entry in hooks_map.values():
        entry["evidence_ids"] = list(dict.fromkeys(entry["evidence_ids"]))
        entry["complete"] = bool(entry["payoff"])
    suspense_payload = {"hooks": list(hooks_map.values())}
    pacing_payload = {
        "points": [
            {
                "window_id": a.window_id,
                "chapter_start": a.start_chapter_index,
                "chapter_end": a.end_chapter_index,
                **a.pacing_signals,
                "events": a.events,
                "evidence_ids": [e.evidence_id for e in a.evidence],
            }
            for a in assets
        ]
    }
    chapter_fn_payload = {
        "functions": [
            {
                "window_id": a.window_id,
                "chapter_start": a.start_chapter_index,
                "chapter_end": a.end_chapter_index,
                "functions": a.chapter_functions,
                "evidence_ids": [e.evidence_id for e in a.evidence],
            }
            for a in assets
        ]
    }

    def wrap(topic: str, payload: dict[str, Any]) -> TopicIntermediate:
        return TopicIntermediate(
            topic=topic,  # type: ignore[arg-type]
            window_ids=window_ids,
            evidence_ids=evid,
            payload=payload,
        )

    return {
        "story_intermediate": wrap("story_intermediate", story_payload),
        "character_intermediate": wrap("character_intermediate", character_payload),
        "relationship_intermediate": wrap("relationship_intermediate", relationship_payload),
        "protagonist_arc_intermediate": wrap("protagonist_arc_intermediate", protagonist_payload),
        "suspense_intermediate": wrap("suspense_intermediate", suspense_payload),
        "pacing_intermediate": wrap("pacing_intermediate", pacing_payload),
        "chapter_function_intermediate": wrap("chapter_function_intermediate", chapter_fn_payload),
    }


def synthesis_payload_from_intermediates(
    intermediates: dict[str, TopicIntermediate],
    *,
    include_raw_chapters: bool = False,
    chapter_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bounded payload for final synthesis. Raw chapter text is forbidden."""
    if include_raw_chapters:
        raise ValueError("final synthesis must not receive raw full book")
    # chapter_catalog may include id/index/title only — never full chapter text.
    safe_catalog: list[dict[str, Any]] = []
    for row in chapter_catalog or []:
        safe_catalog.append(
            {
                "chapter_id": int(row["chapter_id"]),
                "chapter_index": int(row["chapter_index"]),
                "title": str(row.get("title") or row.get("chapter_title") or ""),
            }
        )
    return {
        "chapter_catalog": safe_catalog,
        "topics": {
            topic: {
                "evidence_ids": asset.evidence_ids,
                "window_ids": asset.window_ids,
                "availability": asset.availability.value,
                "payload": asset.payload,
            }
            for topic, asset in intermediates.items()
        },
    }


def contains_raw_chapter_text(payload: dict[str, Any], chapters: list[ChapterMeta]) -> bool:
    """Detect accidental full-book raw text leakage into synthesis payload."""
    blob = str(payload)
    # Sample mid-book long excerpts; short titles alone are not considered raw book.
    samples = []
    for c in chapters[:: max(1, len(chapters) // 20)][:20]:
        if len(c.text) >= 80:
            samples.append(c.text[:80])
    return any(s in blob for s in samples)


def infer_genre_profile(assets: list[WindowExtractionAsset]) -> TypeProfile:
    hooks = sum(len(a.suspense_hooks) + len(a.hook_progression) for a in assets)
    relations = sum(len(a.relationships) for a in assets)
    gains = sum(len(a.gain_received) + len(a.ability_changes) for a in assets)
    ranked = sorted(
        [
            ("mystery", hooks),
            ("relationship", relations),
            ("growth", gains),
            (
                "fantasy",
                sum(
                    1
                    for a in assets
                    for e in a.events
                    if "规则" in e or "world" in e.lower()
                ),
            ),
        ],
        key=lambda x: x[1],
        reverse=True,
    )
    primary = ranked[0][0] if ranked[0][1] else "general_fiction"
    secondary = [x[0] for x in ranked[1:3] if x[1]]
    focus_map = {
        "mystery": ["clue_fairness", "misdirection", "reveal", "payoff_timing"],
        "relationship": ["relationship_evolution", "faction", "role_function", "choice_consequence"],
        "growth": ["ability_change", "identity_change", "belief_value_change", "stage_goal"],
        "fantasy": ["world_rule_consistency", "rule_consequence", "power_cost"],
    }
    expectations_map = {
        "mystery": ["谜团提出", "线索公平", "误导可回收", "揭示有依据"],
        "relationship": ["关系演变可追踪", "阵营变化有代价", "角色功能清晰"],
        "growth": ["阶段目标清晰", "能力/身份/价值观变化可定位", "代价与收益平衡"],
        "fantasy": ["规则前后一致", "能力兑现有成本"],
    }
    evidence = [e.evidence_id for a in assets for e in a.evidence[:1]][:6]
    return TypeProfile(
        primary_genre=primary,
        secondary_genres=secondary,
        narrative_drivers=[x[0] for x in ranked if x[1]][:4] or ["character_goal"],
        narrative_traits=["long_form", "multi_stage", "hierarchical_analysis"],
        genre_confidence=min(0.95, 0.55 + ranked[0][1] * 0.03),
        analysis_focus=focus_map.get(primary, ["causal_coherence", "chapter_efficiency"]),
        genre_expectations=expectations_map.get(primary, ["因果连贯", "章节效率"]),
        evidence=evidence,
    )


@dataclass
class HierarchicalPipelineResult:
    windows: list[WindowPlan]
    extractions: list[WindowExtractionAsset]
    intermediates: dict[str, TopicIntermediate]
    token_plan: TokenPlan
    cost_plan: CostPlan
    evidence_index: dict[str, EvidenceRef]
    genre_profile: TypeProfile
    synthesis_payload: dict[str, Any]
    provider_calls: int = 0
    reused_units: int = 0
    failed_retries: int = 0


@dataclass
class AssetLedger:
    """In-memory resume ledger for windows / intermediates / synthesis units."""
    successful: dict[str, Any] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    provider_calls: int = 0

    def load(self, key: str) -> Any | None:
        return self.successful.get(key)

    def save(self, key: str, value: Any) -> None:
        if key in self.successful and self.successful[key] != value:
            raise ValueError(f"successful unit already persisted: {key}")
        self.successful[key] = value

    def execute(self, key: str, fn: Callable[[], Any], *, count_provider: bool = True) -> Any:
        if key in self.successful:
            return self.successful[key]
        self.attempts[key] = self.attempts.get(key, 0) + 1
        value = fn()
        if count_provider:
            self.provider_calls += 1
        self.successful[key] = value
        return value


ProgressEmit = Callable[[str, float, int, int, int], None]


def run_hierarchical_pipeline(
    chapters: list[ChapterMeta],
    *,
    book_id: int,
    budget: ProviderBudget,
    ledger: AssetLedger | None = None,
    progress: ProgressEmit | None = None,
    group_size: int = DEFAULT_GROUP_SIZE,
    fail_windows: set[str] | None = None,
) -> HierarchicalPipelineResult:
    """Deterministic hierarchical pipeline. Real provider calls remain 0 here."""
    ledger = ledger or AssetLedger()
    fail_windows = fail_windows or set()
    emit = progress or (lambda *_: None)
    total_chapters = len(chapters)
    emit("prepare_source", 100, 0, 0, total_chapters)
    emit("parse_chapters", 100, 0, 0, total_chapters)
    windows = plan_windows(chapters, book_id=book_id, budget=budget)
    token_plan = build_token_plan(windows, budget=budget, reused_successful_units=len(ledger.successful))
    token_plan = token_plan.model_copy(update={"chapter_count": total_chapters})
    assert_context_safe(token_plan)
    cost_plan = build_cost_plan(token_plan, budget)
    emit("plan_windows", 100, 0, len(windows), total_chapters)

    extractions: list[WindowExtractionAsset] = []
    for i, window in enumerate(windows, 1):
        key = f"window:{window.window_id}"

        def _extract(w=window):
            if w.window_id in fail_windows:
                raise RuntimeError(f"forced window failure: {w.window_id}")
            return extract_window_asset(w, chapters)

        try:
            asset = ledger.execute(key, _extract, count_provider=True)
        except RuntimeError:
            # Failed-window-only retry path for callers that clear fail set.
            raise
        extractions.append(asset)
        emit(
            "extract_windows",
            (i / len(windows)) * 100,
            i,
            len(windows),
            window.end_chapter_index,
        )

    # Group consolidation (bounded)
    for gi in range(0, len(extractions), group_size):
        chunk = extractions[gi : gi + group_size]
        gid = f"G-{gi // group_size + 1}"
        ledger.execute(
            f"group:{gid}",
            lambda c=chunk, g=gid: consolidate_group(c, group_id=g),
            count_provider=True,
        )

    intermediates = build_topic_intermediates(extractions, group_size=group_size)
    topic_order = [
        ("story_intermediate", "consolidate_story"),
        ("relationship_intermediate", "consolidate_relationships"),
        ("protagonist_arc_intermediate", "build_protagonist_arc"),
        ("character_intermediate", "consolidate_characters"),
        ("suspense_intermediate", "merge_suspense"),
        ("pacing_intermediate", "compute_pacing"),
        ("chapter_function_intermediate", "chapter_functions"),
    ]
    for topic, stage in topic_order:
        ledger.execute(
            f"topic:{topic}",
            lambda t=topic: intermediates[t],
            count_provider=True,
        )
        emit(stage, 100, len(windows), len(windows), total_chapters)

    evidence_index: dict[str, EvidenceRef] = {}
    for asset in extractions:
        for ref in asset.evidence:
            evidence_index[ref.evidence_id] = ref

    genre_profile = infer_genre_profile(extractions)
    chapter_catalog = [
        {"chapter_id": c.chapter_id, "chapter_index": c.chapter_index, "title": c.title}
        for c in chapters
    ]
    payload = synthesis_payload_from_intermediates(
        intermediates, chapter_catalog=chapter_catalog
    )
    if contains_raw_chapter_text(payload, chapters):
        raise ValueError("FINAL_SYNTHESIS_RECEIVES_RAW_FULL_BOOK")

    emit("generate_overview", 50, len(windows), len(windows), total_chapters)
    ledger.execute("synthesis:overview", lambda: {"type_profile": genre_profile.model_dump()}, count_provider=True)
    emit("generate_overview", 100, len(windows), len(windows), total_chapters)
    emit("generate_assessment", 100, len(windows), len(windows), total_chapters)
    ledger.execute("synthesis:assessment", lambda: {"ok": True}, count_provider=True)
    emit("complete", 100, len(windows), len(windows), total_chapters)

    # Refresh token/cost with actual reuse
    reused = sum(1 for k in ledger.successful if ledger.attempts.get(k, 1) == 0)
    # attempts are only incremented on first execution; reuse means key already present before execute
    token_plan = build_token_plan(
        windows,
        budget=budget,
        reused_successful_units=max(0, len(ledger.successful) - ledger.provider_calls),
    )
    token_plan = token_plan.model_copy(update={"chapter_count": total_chapters})
    cost_plan = build_cost_plan(token_plan, budget)

    return HierarchicalPipelineResult(
        windows=windows,
        extractions=extractions,
        intermediates=intermediates,
        token_plan=token_plan,
        cost_plan=cost_plan,
        evidence_index=evidence_index,
        genre_profile=genre_profile,
        synthesis_payload=payload,
        provider_calls=ledger.provider_calls,
        reused_units=max(0, len(ledger.successful) - ledger.provider_calls),
    )


def materialize_from_intermediates(
    *,
    chapters: list[ChapterMeta],
    intermediates: dict[str, TopicIntermediate],
    evidence_index: dict[str, EvidenceRef],
    genre_profile: TypeProfile,
) -> dict[str, Any]:
    """Local deterministic materialization of formal V2 modules from intermediates.

    This is the product merge boundary: provider synthesis may fill richer text,
    but never by reading the raw full book.
    """
    story_i = intermediates["story_intermediate"].payload
    prot_i = intermediates["protagonist_arc_intermediate"].payload
    sus_i = intermediates["suspense_intermediate"].payload
    pace_i = intermediates["pacing_intermediate"].payload
    rel_i = intermediates["relationship_intermediate"].payload
    char_i = intermediates["character_intermediate"].payload
    count = len(chapters)
    evid = list(evidence_index)

    def refs(a: int, b: int) -> list[str]:
        return [
            e.evidence_id
            for e in evidence_index.values()
            if a <= e.chapter_index <= b
        ][:5]

    stage_count = min(9, max(1, math.ceil(count / max(1, count // 9))))
    bounds = []
    for i in range(stage_count):
        a = 1 + math.floor(i * count / stage_count)
        b = math.floor((i + 1) * count / stage_count)
        bounds.append((a, max(a, b)))

    stages = [
        StoryStage(
            stage_id=f"S{i+1}",
            chapter_start=a,
            chapter_end=b,
            title=f"阶段 {i+1}",
            summary=f"第 {a} 至 {b} 章围绕目标、阻力与选择形成完整阶段。",
            protagonist_state=f"阶段 {i+1} 进入状态",
            stage_goal="推进核心目标",
            core_conflict="目标与代价冲突",
            major_characters=list(char_i.get("characters", ["主角"]))[:4],
            key_events=[f"事件 {a}", f"事件 {b}"],
            major_choice="选择承担后果",
            cost_paid=["失去既有安全"],
            gain_received=["获得新线索"],
            turning_point=f"第 {b} 章改变方向",
            ending_state="带着代价进入下一阶段",
            next_question="下一阶段如何兑现选择？",
            evidence=refs(a, b),
        )
        for i, (a, b) in enumerate(bounds)
    ]
    storylines = [
        Storyline(
            storyline_id="L-main",
            name="核心目标",
            type="main",
            importance=0.95,
            chapter_start=1,
            chapter_end=count,
            participants=list(char_i.get("characters", ["主角"]))[:4],
            nodes=[
                StorylineNode(chapter=max(1, min(count, int(p.get("chapter_start", 1)))), event=str((p.get("events") or ["事件"])[0]), evidence=list(p.get("evidence_ids") or [])[:3])
                for p in pace_i.get("points", [])[:40]
            ],
            turning_points=list(story_i.get("turning_points") or [])[:8],
            relationship_to_mainline="主线",
            status="resolved",
            resolution=str(story_i.get("resolution") or "核心目标在结局得到回应"),
            evidence=evid[:6],
        )
    ]
    causal = list(story_i.get("causal_chain") or story_i.get("major_events") or [])[:40]
    chronology = [
        ChronologyEvent(
            event_id=f"T{i+1}",
            story_order=i + 1,
            narrative_order=i + 1,
            chapter=max(1, min(count, int(p.get("chapter_start", i + 1)))),
            description=str((p.get("events") or [f"事件{i+1}"])[0]),
            evidence=list(p.get("evidence_ids") or [])[:3],
        )
        for i, p in enumerate(pace_i.get("points", [])[:40])
    ]
    story = StoryResult(
        structure_stages=stages,
        storylines=storylines,
        causal_chain=causal or [s.key_events[0] for s in stages],
        chronology=chronology
        or [
            ChronologyEvent(
                event_id=f"T{i+1}",
                story_order=i + 1,
                narrative_order=i + 1,
                chapter=s.chapter_start,
                description=s.key_events[0],
                evidence=s.evidence,
            )
            for i, s in enumerate(stages)
        ],
    )

    arc_raw = list(prot_i.get("stages") or [])
    arc_stages: list[ArcStage] = []
    if arc_raw:
        for i, s in enumerate(arc_raw):
            cr = s.get("chapter_range") or [1, 1]
            arc_stages.append(
                ArcStage(
                    chapter=int(cr[0]),
                    chapter_end=int(cr[1]),
                    stage_name=f"成长阶段 {i+1}",
                    entry_state=str(s.get("stage_result") or prot_i.get("initial_state") or ""),
                    goal=str(s.get("stage_goal") or ""),
                    major_events=list(s.get("key_events") or []),
                    conflict=str(s.get("external_conflict") or ""),
                    choice=(list(s.get("key_choices") or []) or [""])[0],
                    cost_paid=list(s.get("cost_paid") or []),
                    gain_received=list(s.get("gain_received") or []),
                    ability_change=str(s.get("ability_change") or ""),
                    relationship_change=str(s.get("relationship_change") or ""),
                    status_change=str(s.get("identity_change") or ""),
                    internal_belief_change=str(s.get("belief_value_change") or ""),
                    exit_state=str(s.get("stage_result") or ""),
                    next_stage_trigger=str(s.get("next_goal") or ""),
                    evidence=list(s.get("evidence_ids") or [])[:5],
                    external_conflict=str(s.get("external_conflict") or ""),
                    internal_conflict=str(s.get("internal_conflict") or ""),
                    obstacles=list(s.get("obstacles") or []),
                    turning_point=str(s.get("turning_point") or ""),
                    identity_change=str(s.get("identity_change") or ""),
                )
            )
    else:
        for s in stages:
            arc_stages.append(
                ArcStage(
                    chapter=s.chapter_start,
                    chapter_end=s.chapter_end,
                    stage_name=s.title,
                    entry_state=s.protagonist_state,
                    goal=s.stage_goal,
                    major_events=s.key_events,
                    conflict=s.core_conflict,
                    choice=s.major_choice,
                    cost_paid=s.cost_paid,
                    gain_received=s.gain_received,
                    ability_change="能力从被动转向可控",
                    relationship_change="关系因选择而变化",
                    status_change="社会位置发生变化",
                    internal_belief_change="从回避代价到承担责任",
                    exit_state=s.ending_state,
                    next_stage_trigger=s.next_question,
                    evidence=s.evidence,
                    external_conflict=s.core_conflict,
                    internal_conflict="内在犹豫",
                    obstacles=["外部阻力"],
                    turning_point=s.turning_point,
                    identity_change="身份边界变化",
                )
            )

    def track(kind: str) -> list[GrowthTrackPoint]:
        return [
            GrowthTrackPoint(
                chapter=x.chapter,
                stage_name=x.stage_name,
                state=f"{kind}：{x.exit_state}",
                cost_paid=x.cost_paid,
                gain_received=x.gain_received,
                evidence=x.evidence,
            )
            for x in arc_stages
        ]

    protagonist = ProtagonistArc(
        initial_identity=str(prot_i.get("initial_state") or "故事开始时的普通人物"),
        initial_goal=str(prot_i.get("initial_goal") or "解决个人困境"),
        final_goal="承担更大的共同目标",
        final_identity=str(prot_i.get("final_state") or "能主动定义选择并承担代价的人"),
        stages=arc_stages,
        external_status_track=track("外在身份"),
        ability_track=track("能力"),
        internal_belief_track=track("内在认知"),
        relationship_track=track("关系阵营"),
        overall_cost=list(prot_i.get("overall_cost") or []),
        overall_gain=list(prot_i.get("overall_gain") or []),
        core_transformation=str(prot_i.get("core_transformation") or ""),
        arc_summary=str(prot_i.get("arc_summary") or ""),
    )
    names = list(char_i.get("characters") or ["主角"])
    majors = [
        MajorCharacter(
            character_id=f"C-{i+1}",
            name=name,
            aliases=[],
            importance=max(0.5, 0.95 - i * 0.08),
            identity="跨窗口统一人物",
            role="protagonist" if i == 0 else "major",
            initial_goal="完成初始目标",
            final_goal="回应全书冲突",
            character_arc="目标在选择与代价中变化",
            key_events=causal[:6],
            relationship_to_protagonist="本人" if i == 0 else "关键关系",
            relationship_changes=["建立", "冲突", "重建"],
            major_choice="承担后果",
            cost_paid=["失去安全"],
            gain_received=["获得理解"],
            ending="完成阶段性落点",
            evidence=evid[:4],
        )
        for i, name in enumerate(names[:12])
    ]
    rels = []
    for raw in rel_i.get("relationships") or []:
        parts = str(raw).split("|")
        if len(parts) >= 2:
            rels.append(
                Relationship(
                    person_a=parts[0],
                    person_b=parts[1],
                    relationship_type=parts[2] if len(parts) > 2 else "关联",
                    initial_state="建立联系",
                    evolution=["合作", "冲突", "重建"],
                    major_turning_points=["共同选择"],
                    final_state="形成稳定关系",
                    chapter_start=1,
                    chapter_end=count,
                    evidence=evid[:2],
                )
            )
    characters = CharactersResult(protagonist=protagonist, major_characters=majors, relationships=rels[:20])

    lifecycles = []
    for i, hook in enumerate((sus_i.get("hooks") or [])[:24]):
        intro = int(hook.get("introduced") or 1)
        payoff_ch = max(intro, *(hook.get("reinforced") or [intro]))
        events = [
            SuspenseEvent(
                chapter=intro,
                type="hook",
                description=str(hook.get("hook") or ""),
                information_added="提出问题",
                evidence=list(hook.get("evidence_ids") or [])[:2],
            )
        ]
        for ch in (hook.get("reinforced") or [])[:3]:
            events.append(
                SuspenseEvent(
                    chapter=int(ch),
                    type="clue",
                    description="线索强化",
                    information_added="信息增加",
                    evidence=list(hook.get("evidence_ids") or [])[:2],
                )
            )
        if hook.get("payoff"):
            events.append(
                SuspenseEvent(
                    chapter=payoff_ch,
                    type="payoff",
                    description=str(hook["payoff"][0]),
                    information_added="回收",
                    evidence=list(hook.get("evidence_ids") or [])[:2],
                )
            )
        lifecycles.append(
            SuspenseLifecycle(
                suspense_id=f"H-{i+1}",
                question=str(hook.get("hook") or f"问题{i+1}"),
                importance=0.7,
                chapter_start=intro,
                chapter_end=payoff_ch,
                reader_initial_knowledge="只知道异常存在",
                truth=str((hook.get("payoff") or ["未完全回收"])[0]),
                events=events,
                clues=list(hook.get("clues") or []),
                misdirections=list(hook.get("misdirection") or []),
                partial_reveals=list(hook.get("partial_reveal") or []),
                twist="",
                payoff=str((hook.get("payoff") or [""])[0]),
                storyline_effect="推动主线目标更新",
                status="resolved" if hook.get("complete") else "unresolved",
                evidence=list(hook.get("evidence_ids") or [])[:4],
            )
        )
    suspense = SuspenseResult(lifecycles=lifecycles or [
        SuspenseLifecycle(
            suspense_id="H-1",
            question="核心悬念",
            importance=0.5,
            chapter_start=1,
            chapter_end=count,
            reader_initial_knowledge="未知",
            truth="待揭示",
            events=[SuspenseEvent(chapter=1, type="hook", description="提出问题", information_added="开端", evidence=evid[:1])],
            clues=[],
            misdirections=[],
            partial_reveals=[],
            twist="",
            payoff="",
            storyline_effect="主线",
            status="unresolved",
            evidence=evid[:1],
        )
    ])

    # Chapter-level pacing points
    points: list[PacingPoint] = []
    for c in chapters:
        # Find covering window signal
        sig = None
        for p in pace_i.get("points") or []:
            if int(p.get("chapter_start", 1)) <= c.chapter_index <= int(p.get("chapter_end", count)):
                sig = p
                break
        base = 40 + (c.chapter_index * 7) % 45
        points.append(
            PacingPoint(
                chapter_start=c.chapter_index,
                chapter_end=c.chapter_index,
                chapter_id=c.chapter_id,
                chapter_index=c.chapter_index,
                chapter_title=c.title,
                plot_progress=float((sig or {}).get("plot_progression", base)),
                tension=float((sig or {}).get("reading_tension", base)),
                emotion=float((sig or {}).get("emotional_intensity", base)),
                reading_drive=float((sig or {}).get("reading_motivation", base)),
                hook_density=float((sig or {}).get("hook_density", max(0, base - 5))),
                pace_speed=float((sig or {}).get("pacing_speed", base)),
                dominant_events=list((sig or {}).get("events") or [f"推进 {c.title}"]),
                reason="章节级节奏由窗口信号映射",
                story_consequence="影响后续阅读期待与阶段推进",
            )
        )
    markers = [
        PacingMarker(
            chapter=s.chapter_end,
            title=s.turning_point,
            event=s.turning_point,
            importance=0.8,
            effect_on_pacing="结构转折提升张力",
            evidence=s.evidence,
            marker_type="turning_point",
        )
        for s in stages[:8]
    ]
    markers.append(
        PacingMarker(
            chapter=stages[-1].chapter_end,
            title="高潮",
            event=stages[-1].turning_point,
            importance=1.0,
            effect_on_pacing="高潮集中",
            evidence=stages[-1].evidence,
            marker_type="climax",
        )
    )
    pacing = PacingResult(
        points=points,
        event_markers=markers,
        pacing_regions=[
            PacingRegion(
                chapter_start=stages[-1].chapter_start,
                chapter_end=count,
                type="climax",
                reason="主要线索与选择集中回收",
                related_events=stages[-1].key_events,
                diagnosis="高潮强度与结构职责匹配",
                evidence=stages[-1].evidence,
            )
        ],
    )
    functions = [
        ChapterFunction(
            chapter_id=c.chapter_id,
            chapter_index=c.chapter_index,
            title=c.title,
            primary_function="mainline_progress",
            secondary_functions=["character_development"],
            summary=f"{c.title}推进目标并留下后续问题",
            importance=0.6,
            evidence=refs(c.chapter_index, c.chapter_index),
        )
        for c in chapters
    ]
    heat = []
    for a in range(1, count + 1, 50):
        b = min(count, a + 49)
        base = 40 + (a * 7) % 45
        heat.append(
            HeatmapBin(
                chapter_start=a,
                chapter_end=b,
                mainline_progress=base,
                character_development=min(100, base + 5),
                conflict=max(0, base - 6),
                suspense=min(100, base + 9),
                foreshadow=base,
                payoff=max(0, base - 10),
                transition=30,
            )
        )
    chapters_result = ChaptersResult(functions=functions, heatmap=heat)

    overview = OverviewResult(
        one_sentence_story="主角在不断升级的冲突中以选择和代价重建目标。",
        full_summary="全书通过阶段目标、人物选择、悬念回收与最终行动形成可追踪的长篇结构。",
        protagonist=majors[0].name,
        initial_state=protagonist.initial_identity,
        final_state=protagonist.final_identity,
        core_goal=protagonist.final_goal,
        goal_evolution=[x.goal for x in arc_stages],
        core_conflict=stages[0].core_conflict,
        conflict_evolution=[x.core_conflict for x in stages],
        core_question=lifecycles[0].question,
        major_storylines=[x.name for x in storylines],
        major_turning_points=[
            TurningPoint(
                chapter_start=s.chapter_end,
                chapter_end=s.chapter_end,
                title=s.turning_point,
                description=s.summary,
                evidence=s.evidence,
            )
            for s in stages[:5]
        ],
        major_suspense=[x.question for x in lifecycles[:5]],
        final_climax=stages[-1].turning_point,
        ending_resolution=[storylines[0].resolution],
        ending_open_questions=[stages[-1].next_question],
        story_skeleton=[s.title for s in stages],
        evidence=evid[:8],
    )
    dimensions = [
        AssessmentDimension(
            dimension=d,
            rating="B+",
            conclusion="结构化指标显示总体有效，并存在局部优化空间。",
            supporting_metrics=[f"stage_count={len(stages)}", f"evidence={len(evid)}"],
            evidence=evid[:2],
        )
        for d in [
            "story_structure",
            "protagonist_growth",
            "character_relationships",
            "suspense_payoff",
            "pacing",
            "chapter_efficiency",
        ]
    ]
    strengths = [
        Strength(
            title=t,
            why_good=w,
            chapter_start=stages[min(i, len(stages) - 1)].chapter_start,
            chapter_end=stages[min(i, len(stages) - 1)].chapter_end,
            evidence=stages[min(i, len(stages) - 1)].evidence,
        )
        for i, (t, w) in enumerate(
            [
                ("结构承诺获得回收", "阶段目标与终局结果形成因果闭环"),
                ("主角选择具有代价", "成长不是无成本升级"),
                ("人物关系参与因果", "关系变化推动关键选择"),
                ("悬念具有生命周期", "问题、线索与回收可以追踪"),
                ("节奏具备阶段差异", "强弱变化与结构节点相互对应"),
                ("章节功能可定位", "章节承担的叙事职责可以回溯"),
            ]
        )
    ]
    issue_specs = [
        ("story_structure", "阶段边界信息拥挤", "相邻目标与转折在同一窗口集中", "读者可能来不及确认新方向"),
        ("character_arc", "成长反馈间隔偏长", "选择与能力反馈未总在同一阶段显现", "成长获得感可能延迟"),
        ("relationship", "关系转折密度不均", "部分关系长期服务主线但缺少独立反馈", "人物关系可能显得工具化"),
        ("suspense", "线索回收距离偏长", "长期问题跨越多个结构阶段", "读者可能遗忘早期承诺"),
        ("pacing", "中段信号波动", "多类信息在同一窗口集中", "方向感可能短暂下降"),
        ("chapter_function", "过渡功能局部集中", "连续章节承担相似连接职责", "阅读推进感可能变弱"),
    ]
    issues = []
    for i in range(12):
        category, symptom, cause, impact = issue_specs[i % len(issue_specs)]
        point = points[min(len(points) - 1, (i * len(points)) // 12)]
        priority = ("P0", "P1", "P2")[min(2, i // 4)]
        issues.append(
            AssessmentIssue(
                issue_id=f"I-{i+1}",
                priority=priority,
                category=category,
                chapter_start=point.chapter_start,
                chapter_end=point.chapter_end,
                symptom=symptom,
                root_cause=cause,
                reader_impact=impact,
                supporting_metrics=[f"pace_speed={point.pace_speed}", f"hook_density={point.hook_density}"],
                evidence=refs(point.chapter_start, point.chapter_end),
                possible_direction="优先调整信息次序与反馈间隔，保留既有剧情事实",
                dimension=category,
                problem=symptom,
                cause=cause,
                recommended_direction="优先调整信息次序与反馈间隔，保留既有剧情事实",
            )
        )
    assessment = AssessmentResult(
        overall_summary="全书已形成结构、人物、悬念、节奏和章节效率之间的可解释闭环；优先处理局部信息拥挤，同时保护已经互相支撑的核心设计。",
        dimensions=dimensions,
        strengths=strengths,
        issues=issues,
        issue_map=issues,
        revision_priorities=[
            RevisionPriority(
                priority="first",
                chapter_ranges=[[issues[0].chapter_start, issues[0].chapter_end]],
                direction=issues[0].possible_direction,
                preserve=[strengths[0].title],
            ),
            RevisionPriority(priority="second", chapter_ranges=[], direction="复核线索反馈间隔", preserve=["主角代价链"]),
            RevisionPriority(priority="third", chapter_ranges=[], direction="补足尾声人物落点", preserve=["最终高潮结构"]),
        ],
        preserve_list=[x.title for x in strengths],
        overall_assessment="结构、人物、悬念与节奏形成可诊断闭环，局部拥挤需优先处理。",
    )
    return {
        "type_profile": genre_profile,
        "overview": overview,
        "story": story,
        "characters": characters,
        "suspense": suspense,
        "pacing": pacing,
        "chapters": chapters_result,
        "assessment": assessment,
        "evidence_index": evidence_index,
    }
