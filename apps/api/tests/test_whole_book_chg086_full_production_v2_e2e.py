"""CHG-086: full production Hierarchical V2 pipeline at real book scale.

These tests run the real production runtime (GatewayWholeBookV2Analyzer, real
contracts, real progress, real evidence validation) against a fake provider
transport shaped like DeepSeek. No network, no scaffold, no mock fallback.

The scale mirrors the reported failure: 542 chapters / ~2.9M chars / 15 windows,
which is what made every synthesis unit exceed the safe provider context.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.model_gateway.base import ModelResponse
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit,
    ChapterFunctionBatchUnit,
    CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit,
    PacingCoreSynthesisUnit,
    StorySynthesisUnit,
    SuspenseSynthesisUnit,
    WholeBookAnalysisV2,
)
from app.narrative_core.whole_book_v2.engine import (
    DeterministicPrimitiveExtractor,
    SourceChapter,
    WholeBookV2Engine,
)
from app.narrative_core.whole_book_v2.pipeline import (
    CHARS_PER_TOKEN,
    ProviderBudget,
    bound_synthesis_payload,
    plan_windows,
    project_synthesis_payload,
)
from app.narrative_core.whole_book_v2.window_extraction import build_window_evidence_catalog
from app.narrative_core.whole_book_v2.provider_engine import (
    UNIT_SCHEMAS,
    CHAPTER_FUNCTION_BATCH_SIZE,
    GatewayWholeBookV2Analyzer,
    build_synthesis_unit_prompt,
    SynthesisUnitError,
    UnitFailureCode,
)

# The real report: 542 chapters, ~2.9M chars, 15 windows.
PRODUCTION_CHAPTERS = 542
CHARS_PER_CHAPTER = 5_350


def production_chapters(count: int = PRODUCTION_CHAPTERS) -> list[SourceChapter]:
    """Book-scale source chapters (synthetic prose, never real novel text)."""
    body = (
        "@Lin faces a costly choice and pays for it. A clue surfaces and the "
        "question of who benefits stays open while the pressure keeps rising. "
    )
    filler = body * (CHARS_PER_CHAPTER // len(body) + 1)
    return [
        SourceChapter(1000 + i, i, f"chapter {i}", f"{filler[:CHARS_PER_CHAPTER]} #{i}", 77, "rev")
        for i in range(1, count + 1)
    ]


# Per-window list sizes tuned against what the failing run actually persisted:
# 15 window assets => ~184KB of topic intermediates => a ~239K-char synthesis
# prompt => 123,368 estimated tokens vs a 120,000 safe context. These values
# reproduce ~208KB of topics, so the fixture is slightly harsher than the real
# failure. Shrinking them stops the test from reproducing the defect at all.
EVENTS_PER_WINDOW = 5
HOOKS_PER_WINDOW = 2
STATES_PER_WINDOW = 4


def window_payload_for(window: Any, chapters: list[SourceChapter]) -> dict[str, Any]:
    """A provider window-extraction response shaped and sized like a real DeepSeek reply."""
    catalog = build_window_evidence_catalog(window, [c.as_meta() for c in chapters])
    ids = [e.evidence_id for e in catalog]
    wid = window.window_id
    span = range(window.start_chapter_index, window.end_chapter_index + 1)

    def phrases(count: int, template: str) -> list[str]:
        return [template.format(wid=wid, n=n) for n in range(1, count + 1)]

    return {
        "events": phrases(
            EVENTS_PER_WINDOW,
            "在{wid}的第{n}个转折里，林做出代价高昂的选择并牵连出新的调查线索",
        ),
        "event_causality": phrases(
            EVENTS_PER_WINDOW,
            "{wid}第{n}处压力迫使林改变原有计划，并直接导致下一阶段的对抗升级",
        ),
        "characters": ["林", "许队", "孙教授"] + phrases(6, "{wid}线人{n}"),
        "character_states": phrases(
            STATES_PER_WINDOW, "{wid}阶段{n}：林处于被动但仍在权衡代价与目标"
        ),
        "character_changes": phrases(
            STATES_PER_WINDOW, "{wid}阶段{n}：林开始承担后果并调整对规则的信任"
        ),
        "relationships": phrases(STATES_PER_WINDOW, "林-{wid}关系{n}"),
        "relationship_changes": phrases(
            STATES_PER_WINDOW, "{wid}关系{n}从合作转为有条件的信任并留下未解的亏欠"
        ),
        "protagonist_goals": phrases(6, "{wid}目标{n}：洗清嫌疑并保住调查资格"),
        "protagonist_obstacles": phrases(6, "{wid}阻力{n}：内部审查与证据链缺口"),
        "protagonist_choices": phrases(6, "{wid}选择{n}：仍然选择出庭作证"),
        "cost_paid": phrases(6, "{wid}代价{n}：失去旧的同盟关系"),
        "gain_received": phrases(6, "{wid}收获{n}：获得一位可信证人"),
        "ability_changes": phrases(4, "{wid}能力{n}：审讯判断速度提升"),
        "identity_changes": phrases(4, "{wid}身份{n}：从嫌疑人转为知情者"),
        "belief_value_changes": phrases(4, "{wid}信念{n}：规则并不天然保护任何人"),
        "suspense_hooks": [
            f"是谁泄露了{wid}的第{n}份卷宗并且为此获利@{wid}-{n}"
            for n in range(1, HOOKS_PER_WINDOW + 1)
        ],
        "hook_progression": phrases(HOOKS_PER_WINDOW, "{wid}线索{n}被部分证实但仍未指向具体的人"),
        "hook_payoff": [],
        "story_signals": phrases(EVENTS_PER_WINDOW, "{wid}信号{n}：主线推进并留下新的开放问题"),
        "pacing_signals": {"tension": 72.0, "plot_progress": 55.0, "hook_density": 40.0},
        "chapter_functions": [f"第{idx}章 主线推进与信息铺垫" for idx in span],
        "evidence_ids": ids,
    }


def synthesis_payloads(chapters: list[SourceChapter]) -> list[dict[str, Any]]:
    """Valid provider responses for every synthesis unit, in production order."""
    reference = WholeBookV2Engine(
        DeterministicPrimitiveExtractor(), window_size=64, overlap=0
    ).run(run_id=1, book_id=1, title="fixture", chapters=chapters)
    return [
        OverviewTypeSynthesisUnit(
            type_profile=reference.type_profile, overview=reference.overview
        ).model_dump(mode="json"),
        StorySynthesisUnit(story=reference.story).model_dump(mode="json"),
        CharactersSynthesisUnit(characters=reference.characters).model_dump(mode="json"),
        SuspenseSynthesisUnit(suspense=reference.suspense).model_dump(mode="json"),
        PacingCoreSynthesisUnit(pacing=reference.pacing).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=reference.assessment).model_dump(mode="json"),
        *[
            ChapterFunctionBatchUnit(
                functions=reference.chapters.functions[i : i + CHAPTER_FUNCTION_BATCH_SIZE]
            ).model_dump(mode="json")
            for i in range(
                0, len(reference.chapters.functions), CHAPTER_FUNCTION_BATCH_SIZE
            )
        ],
    ]


class FakeDeepSeekTransport:
    """Production-shaped provider transport. Records every request; never networks."""

    def __init__(self, items: list[Any], *, context_limit: int = 128_000):
        self.items = list(items)
        self.calls: list[Any] = []
        self.max_observed_input_tokens = 0
        self.context_limit = context_limit
        # Force the real Provider extraction path, not the deterministic scaffold.
        self.deterministic_extraction = False
        self.disallow_local_merge = True

    async def generate(self, provider: str, request: Any) -> ModelResponse:
        prompt = "".join(m["content"] for m in request.messages)
        estimated = len(prompt) // CHARS_PER_TOKEN
        self.max_observed_input_tokens = max(self.max_observed_input_tokens, estimated)
        if estimated > self.context_limit:
            raise AssertionError(
                f"provider would reject {estimated} input tokens > {self.context_limit}"
            )
        self.calls.append(request)
        if not self.items:
            raise AssertionError("fake provider exhausted: pipeline made an unexpected call")
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, ModelResponse):
            return item
        return ModelResponse(
            text=json.dumps(item, ensure_ascii=False),
            model="deepseek-v4-flash",
            finish_reason="stop",
            input_tokens=estimated,
            output_tokens=2_000,
        )


def build_transport(chapters: list[SourceChapter], *, extra: list[Any] | None = None):
    budget = ProviderBudget(provider="deepseek", model="deepseek-v4-flash")
    windows = plan_windows([c.as_meta() for c in chapters], book_id=1, budget=budget)
    items: list[Any] = [window_payload_for(w, chapters) for w in windows]
    items.extend(extra or [])
    items.extend(synthesis_payloads(chapters))
    return FakeDeepSeekTransport(items), windows


@pytest.mark.asyncio
async def test_full_production_hierarchical_v2_pipeline_end_to_end():
    """542 chapters run start-to-finish: windows, consolidation, every unit, persist."""
    chapters = production_chapters()
    transport, windows = build_transport(chapters)
    analyzer = GatewayWholeBookV2Analyzer(
        transport, provider_name="deepseek", model_name="deepseek-v4-flash"
    )
    progress: list[tuple[Any, ...]] = []

    result, _ = await analyzer.analyze(
        run_id=8601,
        book_id=1,
        title="production-scale",
        chapters=chapters,
        progress=lambda *event: progress.append(event),
    )

    # Scale actually matches the reported production run.
    assert len(windows) == 15, f"expected the reported 15-window plan, got {len(windows)}"
    assert sum(len(c.text) for c in chapters) > 2_800_000

    # Real provider result, no scaffold and no local-merge fallback.
    assert result.analysis_metadata.result_origin == "real_provider"
    assert result.analysis_metadata.real_provider_calls == analyzer.stats.provider_calls

    # Every module is populated and the whole book is covered chapter by chapter.
    assert len(result.chapters.functions) == PRODUCTION_CHAPTERS
    assert [f.chapter_index for f in result.chapters.functions] == list(
        range(1, PRODUCTION_CHAPTERS + 1)
    )
    assert result.chapters.heatmap
    assert result.overview.one_sentence_story and result.story.structure_stages
    assert result.characters.major_characters and result.suspense.lifecycles
    assert result.pacing.points and result.assessment.dimensions
    assert result.evidence_index

    # Round-trips through the persistence contract.
    assert WholeBookAnalysisV2.model_validate_json(result.model_dump_json()) == result

    # No request came close to the context wall that broke production.
    assert transport.max_observed_input_tokens < 120_000, (
        f"a request reached {transport.max_observed_input_tokens} tokens — "
        "this is the CHG-086 regression"
    )
    assert progress[-1][0] == "materialize_report"


@pytest.mark.asyncio
async def test_synthesis_units_stay_bounded_at_production_scale():
    """Regression guard for the exact defect: unprojected payloads blew the context."""
    chapters = production_chapters()
    transport, _ = build_transport(chapters)
    analyzer = GatewayWholeBookV2Analyzer(
        transport, provider_name="deepseek", model_name="deepseek-v4-flash"
    )
    await analyzer.analyze(run_id=8602, book_id=1, title="x", chapters=chapters)

    payload = analyzer.last_synthesis_payload
    assert payload is not None
    full = len(json.dumps(payload, ensure_ascii=False))

    # The unprojected payload is what production actually sent — it must be large
    # enough here that the projection is doing real work.
    assert full > 200_000, "fixture no longer reproduces the oversized payload"

    limit = analyzer.budget.context_limit - analyzer.budget.safety_margin
    for unit, schema in UNIT_SCHEMAS.items():
        # Pre-CHG-086 behaviour: the whole payload went to every unit.
        unprojected = len(build_synthesis_unit_prompt(unit, schema, payload)) // CHARS_PER_TOKEN
        assert unprojected + analyzer.max_output_tokens > limit, (
            f"{unit} no longer reproduces the CONTEXT_UNSAFE overflow — "
            "the fixture has drifted and the test proves nothing"
        )
        projected = analyzer._unit_payload(unit, schema, payload)
        estimated = len(build_synthesis_unit_prompt(unit, schema, projected)) // CHARS_PER_TOKEN
        assert estimated + analyzer.max_output_tokens < limit, f"{unit} still overflows"
        # Projection must not silently drop a topic the unit depends on.
        assert projected["topics"], unit


def test_bounded_payload_degrades_instead_of_overflowing():
    """A book far larger than 542 chapters must trim, not raise CONTEXT_UNSAFE."""
    payload = {
        "topics": {
            "story_intermediate": {"payload": {"events": [f"event {i}" for i in range(50_000)]}}
        }
    }
    assert len(json.dumps(payload, ensure_ascii=False)) > 500_000
    bounded = bound_synthesis_payload(payload, max_chars=50_000)
    assert len(json.dumps(bounded, ensure_ascii=False)) <= 50_000
    # Still structurally valid, just shorter.
    assert bounded["topics"]["story_intermediate"]["payload"]["events"]


def test_unit_projection_excludes_unrelated_topics():
    payload = {
        "chapter_catalog": [{"chapter_id": 1, "chapter_index": 1, "title": "t"}],
        "topics": {
            name: {"payload": {}}
            for name in (
                "story_intermediate",
                "character_intermediate",
                "relationship_intermediate",
                "protagonist_arc_intermediate",
                "suspense_intermediate",
                "pacing_intermediate",
                "chapter_function_intermediate",
            )
        },
    }
    overview = project_synthesis_payload(payload, "overview_type")
    assert "pacing_intermediate" not in overview["topics"]
    assert "chapter_function_intermediate" not in overview["topics"]
    # Only chapter-enumerating units pay for the catalog.
    assert "chapter_catalog" not in overview
    assert project_synthesis_payload(payload, "pacing")["chapter_catalog"]
    assert project_synthesis_payload(payload, "chapter_functions")["chapter_catalog"]


@pytest.mark.asyncio
async def test_chapter_function_coverage_gap_is_rejected():
    """A batch that skips chapters must fail loudly, never persist a partial book."""
    chapters = production_chapters(120)
    budget = ProviderBudget(provider="deepseek", model="deepseek-v4-flash")
    windows = plan_windows([c.as_meta() for c in chapters], book_id=1, budget=budget)
    payloads = synthesis_payloads(chapters)
    # Drop one chapter from the first chapter-function batch, twice (call + repair).
    short = json.loads(json.dumps(payloads[6]))
    short["functions"] = short["functions"][:-1]
    items: list[Any] = [window_payload_for(w, chapters) for w in windows]
    items.extend(payloads[:6])
    items.extend([short, short])
    items.extend(payloads[7:])

    analyzer = GatewayWholeBookV2Analyzer(
        FakeDeepSeekTransport(items), provider_name="deepseek", model_name="deepseek-v4-flash"
    )
    with pytest.raises(SynthesisUnitError) as excinfo:
        await analyzer.analyze(run_id=8603, book_id=1, title="x", chapters=chapters)
    assert excinfo.value.code == UnitFailureCode.MISSING_REQUIRED_FIELD
    assert "chapter coverage" in str(excinfo.value)


# --------------------------------------------------------------------------
# Failure injection: a broken unit must never cost paid work twice, and must
# never take the process down with it.
# --------------------------------------------------------------------------


class _ProviderTimeout(TimeoutError):
    pass


class _ProviderServerError(RuntimeError):
    pass


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(_ProviderTimeout("provider timed out"), id="timeout"),
        pytest.param(_ProviderServerError("HTTP 500 from provider"), id="http_500"),
        pytest.param(
            ModelResponse(
                text="not json at all", model="deepseek-v4-flash",
                finish_reason="stop", input_tokens=10, output_tokens=5,
            ),
            id="invalid_json",
        ),
        pytest.param(
            ModelResponse(
                text='{"type_profile": {"primary_genre": "crime"',
                model="deepseek-v4-flash", finish_reason="length",
                input_tokens=10, output_tokens=4000,
            ),
            id="truncated_json",
        ),
    ],
)
@pytest.mark.asyncio
async def test_injected_failure_preserves_paid_work_and_does_not_crash_process(failure):
    """A failing unit surfaces a typed error; earlier paid windows are kept."""
    chapters = production_chapters(120)
    windows = windows_for(chapters)
    # Fail on the first synthesis call, i.e. after every window is already paid for.
    # Twice: the unit fails, its repair attempt fails the same way, and the unit
    # is then abandoned — which is what a real bad provider response looks like.
    transport = FakeDeepSeekTransport(
        [window_payload_for(w, chapters) for w in windows] + [failure, failure]
    )
    analyzer = GatewayWholeBookV2Analyzer(
        transport, provider_name="deepseek", model_name="deepseek-v4-flash"
    )
    with pytest.raises((SynthesisUnitError, TimeoutError, RuntimeError)):
        await analyzer.analyze(run_id=8610, book_id=1, title="x", chapters=chapters)

    # Every window extraction succeeded and is retained in the asset ledger.
    assert analyzer.stats.window_calls == len(windows)
    saved = [k for k in analyzer.asset_ledger.successful if k.startswith("window:")]
    assert len(saved) == len(windows), "paid window work was lost on failure"

    # Resuming reuses those windows instead of re-buying them: the transport is
    # primed with synthesis responses only, so any window request would exhaust it.
    resumed_transport = FakeDeepSeekTransport(synthesis_payloads(chapters))
    resumed = GatewayWholeBookV2Analyzer(
        resumed_transport,
        provider_name="deepseek",
        model_name="deepseek-v4-flash",
        asset_ledger=analyzer.asset_ledger,
    )
    result, _ = await resumed.analyze(run_id=8610, book_id=1, title="x", chapters=chapters)
    assert result.analysis_metadata.result_origin == "real_provider"
    window_requests = [
        r for r in resumed_transport.calls if "EVIDENCE_CATALOG" in r.messages[0]["content"]
    ]
    assert window_requests == [], "resume re-bought windows that were already paid for"


def windows_for(chapters: list[SourceChapter]):
    return plan_windows(
        [c.as_meta() for c in chapters],
        book_id=1,
        budget=ProviderBudget(provider="deepseek", model="deepseek-v4-flash"),
    )


@pytest.mark.asyncio
async def test_missing_required_field_is_repaired_without_reburning_windows():
    chapters = production_chapters(120)
    windows = windows_for(chapters)
    payloads = synthesis_payloads(chapters)
    broken = json.loads(json.dumps(payloads[0]))
    del broken["overview"]["core_goal"]
    items: list[Any] = [window_payload_for(w, chapters) for w in windows]
    items.extend([broken, *payloads])  # bad overview, then a valid repair
    transport = FakeDeepSeekTransport(items)
    analyzer = GatewayWholeBookV2Analyzer(
        transport, provider_name="deepseek", model_name="deepseek-v4-flash"
    )
    result, _ = await analyzer.analyze(run_id=8611, book_id=1, title="x", chapters=chapters)
    assert analyzer.stats.repair_calls == 1
    assert result.overview.core_goal
    assert analyzer.stats.window_calls == len(windows)


@pytest.mark.asyncio
async def test_successful_units_are_never_requested_twice():
    """No duplicate provider spend across a completed run plus a full resume."""
    chapters = production_chapters(120)
    transport, windows = build_transport(chapters)
    analyzer = GatewayWholeBookV2Analyzer(
        transport, provider_name="deepseek", model_name="deepseek-v4-flash"
    )
    await analyzer.analyze(run_id=8612, book_id=1, title="x", chapters=chapters)
    first_pass = len(transport.calls)
    assert first_pass == analyzer.stats.provider_calls

    await analyzer.analyze(run_id=8612, book_id=1, title="x", chapters=chapters)
    assert len(transport.calls) == first_pass, "resume re-issued already-paid provider calls"
    assert analyzer.ledger.duplicate_provider_units == 0
