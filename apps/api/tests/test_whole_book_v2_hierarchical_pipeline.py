"""CHG-073 hierarchical Whole-Book V2 pipeline tests (deterministic, zero real provider)."""
from __future__ import annotations

import pytest

from app.narrative_core.whole_book_v2.contracts import V2_STAGES, WholeBookAnalysisV2
from app.narrative_core.whole_book_v2.engine import SourceChapter, WholeBookV2Engine, progress_snapshot
from app.narrative_core.whole_book_v2.pipeline import (
    AssetLedger,
    ChapterMeta,
    ProviderBudget,
    assert_context_safe,
    build_cost_plan,
    build_token_plan,
    contains_raw_chapter_text,
    dry_run_1299,
    extract_window_asset,
    make_window_id,
    materialize_from_intermediates,
    plan_windows,
    run_hierarchical_pipeline,
    synthesis_payload_from_intermediates,
)


def _metas(count: int = 24, chars: int = 400) -> list[ChapterMeta]:
    return [
        ChapterMeta(
            chapter_id=10_000 + i,
            chapter_index=i,
            title=f"第{i}章",
            text=f"@林 @顾 第{i}章 选择与代价。" + ("内容" * (chars // 2)),
            snapshot_id=77,
            revision_hash="rev-h",
        )
        for i in range(1, count + 1)
    ]


def _sources(count: int = 24) -> list[SourceChapter]:
    return [
        SourceChapter(m.chapter_id, m.chapter_index, m.title, m.text, m.snapshot_id, m.revision_hash)
        for m in _metas(count)
    ]


def test_1299_chapter_planning():
    report = dry_run_1299()
    assert report.window_count >= 10
    assert report.estimated_provider_calls > report.window_count
    assert report.context_safe == "YES"
    assert report.no_raw_full_book_final_request == "YES"
    assert report.no_request_above_safe_context == "YES"
    assert report.window_plan_exists == report.call_plan_exists == "YES"
    assert report.token_plan_exists == report.cost_plan_exists == "YES"
    assert report.resume_plan_exists == report.repair_plan_exists == "YES"
    assert report.max_request_tokens <= report.provider_context_limit - report.safety_margin
    assert report.token_plan.chapter_count == 1299


def test_context_safety():
    budget = ProviderBudget(provider="x", model="y", context_limit=50_000, safety_margin=5_000)
    windows = plan_windows(_metas(40, chars=800), book_id=1, budget=budget)
    plan = build_token_plan(windows, budget=budget)
    assert plan.context_safe == "YES"
    assert_context_safe(plan)
    # Force unsafe: shrink context so even one planned request fails the gate.
    unsafe = plan.model_copy(
        update={
            "context_safe": "NO",
            "max_single_request_total_tokens": budget.context_limit,
            "provider_context_limit": budget.context_limit,
            "context_safety_margin": budget.safety_margin,
        }
    )
    with pytest.raises(ValueError, match="CONTEXT_SAFE=NO"):
        assert_context_safe(unsafe)


def test_window_boundary_deterministic():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(30)
    a = plan_windows(chapters, book_id=9, budget=budget)
    b = plan_windows(chapters, book_id=9, budget=budget)
    assert [w.window_id for w in a] == [w.window_id for w in b]
    assert a[0].start_chapter_index == 1
    assert a[-1].end_chapter_index == 30
    # Contiguous coverage with overlap allowed, but never empty.
    assert all(w.chapter_count >= 1 for w in a)
    assert all(w.estimated_input_tokens <= budget.safe_input_capacity for w in a)


def test_window_identity_stable():
    w1 = make_window_id(
        book_id=1, snapshot_id=2, revision="r", provider="p", model="m",
        start_chapter_id=100, end_chapter_id=110,
    )
    w2 = make_window_id(
        book_id=1, snapshot_id=2, revision="r", provider="p", model="m",
        start_chapter_id=100, end_chapter_id=110,
    )
    w3 = make_window_id(
        book_id=1, snapshot_id=2, revision="r2", provider="p", model="m",
        start_chapter_id=100, end_chapter_id=110,
    )
    assert w1 == w2 and w1 != w3


def test_evidence_preserved():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(16)
    pipe = run_hierarchical_pipeline(chapters, book_id=1, budget=budget)
    assert pipe.evidence_index
    for topic, asset in pipe.intermediates.items():
        assert asset.evidence_ids, topic
        assert set(asset.evidence_ids).issubset(pipe.evidence_index)
    modules = materialize_from_intermediates(
        chapters=chapters,
        intermediates=pipe.intermediates,
        evidence_index=pipe.evidence_index,
        genre_profile=pipe.genre_profile,
    )
    for ref in modules["evidence_index"].values():
        chapter = next(c for c in chapters if c.chapter_id == ref.chapter_id)
        assert chapter.chapter_index == ref.chapter_index
        assert chapter.text[ref.start_offset:ref.end_offset] == ref.quote_or_excerpt


def test_successful_window_reuse():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(12)
    ledger = AssetLedger()
    first = run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger)
    calls_after_first = ledger.provider_calls
    second = run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger)
    assert second.windows == first.windows
    assert ledger.provider_calls == calls_after_first  # no new provider units


def test_failed_window_only_retry():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(10)
    windows = plan_windows(chapters, book_id=1, budget=budget)
    fail_id = windows[0].window_id
    ledger = AssetLedger()
    with pytest.raises(RuntimeError, match="forced window failure"):
        run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger, fail_windows={fail_id})
    # Successful later windows were not reached; only retry the failed window.
    assert f"window:{fail_id}" not in ledger.successful
    recovered = run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger, fail_windows=set())
    assert f"window:{fail_id}" in ledger.successful
    assert recovered.extractions


def test_no_duplicate_successful_window_call():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(8)
    ledger = AssetLedger()
    run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger)
    before = dict(ledger.attempts)
    run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger)
    assert ledger.attempts == before


def test_intermediate_reuse():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(12)
    ledger = AssetLedger()
    pipe = run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger)
    for topic in pipe.intermediates:
        assert ledger.load(f"topic:{topic}") is not None
    again = run_hierarchical_pipeline(chapters, book_id=1, budget=budget, ledger=ledger)
    assert again.intermediates.keys() == pipe.intermediates.keys()


def test_protagonist_arc_consolidation():
    budget = ProviderBudget(provider="p", model="m")
    pipe = run_hierarchical_pipeline(_metas(20), book_id=1, budget=budget)
    arc = pipe.intermediates["protagonist_arc_intermediate"].payload
    assert arc["stages"]
    assert arc["initial_state"] and arc["final_state"]
    assert arc["overall_cost"] is not None and arc["core_transformation"]
    stage = arc["stages"][0]
    for key in (
        "chapter_range", "stage_goal", "external_conflict", "internal_conflict",
        "obstacles", "key_events", "key_choices", "cost_paid", "gain_received",
        "ability_change", "relationship_change", "identity_change",
        "belief_value_change", "turning_point", "stage_result", "next_goal", "evidence_ids",
    ):
        assert key in stage


def test_hook_lifecycle_cross_window():
    # Force multiple windows so the same hook family must merge across windows.
    budget = ProviderBudget(
        provider="p", model="m", context_limit=4_000, safety_margin=500,
        system_prompt_reserve=200, schema_reserve=200, expected_output=400, repair_reserve=400,
    )
    chapters = [
        ChapterMeta(
            chapter_id=10_000 + i,
            chapter_index=i,
            title=f"第{i}章",
            text=f"@林 悬念推进 " + ("内容" * 400),
            snapshot_id=77,
            revision_hash="rev-h",
        )
        for i in range(1, 25)
    ]
    windows = plan_windows(chapters, book_id=1, budget=budget)
    assert len(windows) >= 2
    pipe = run_hierarchical_pipeline(chapters, book_id=1, budget=budget)
    hooks = pipe.intermediates["suspense_intermediate"].payload["hooks"]
    assert hooks
    multi = [h for h in hooks if len(h.get("windows") or []) >= 2]
    assert multi, "expected cross-window hook lifecycle"


def test_final_synthesis_has_no_raw_full_book():
    budget = ProviderBudget(provider="p", model="m")
    chapters = _metas(18, chars=600)
    pipe = run_hierarchical_pipeline(chapters, book_id=1, budget=budget)
    assert not contains_raw_chapter_text(pipe.synthesis_payload, chapters)
    with pytest.raises(ValueError, match="must not receive raw"):
        synthesis_payload_from_intermediates(pipe.intermediates, include_raw_chapters=True)


def test_token_planner():
    budget = ProviderBudget(provider="p", model="m")
    windows = plan_windows(_metas(50), book_id=1, budget=budget)
    plan = build_token_plan(windows, budget=budget)
    assert plan.extract_calls == len(windows)
    assert plan.consolidation_calls > 0
    assert plan.final_synthesis_calls == 6
    assert plan.repair_reserve_calls >= 1
    assert plan.estimated_total_calls == (
        plan.extract_calls + plan.consolidation_calls + plan.final_synthesis_calls + plan.repair_reserve_calls
    )
    assert plan.context_safe in {"YES", "NO"}


def test_cost_planner():
    budget = ProviderBudget(provider="p", model="m", input_rate_per_mtok=2.0, output_rate_per_mtok=4.0)
    windows = plan_windows(_metas(40), book_id=1, budget=budget)
    token = build_token_plan(windows, budget=budget, reused_successful_units=5)
    cost = build_cost_plan(token, budget)
    assert cost.estimated_cost_low <= cost.estimated_cost_high
    assert cost.reused_units_not_rebilled == 5
    full = build_cost_plan(build_token_plan(windows, budget=budget, reused_successful_units=0), budget)
    assert cost.estimated_cost_low <= full.estimated_cost_low


def test_progress_reporting():
    assert "extract_windows" in V2_STAGES
    assert "build_protagonist_arc" in V2_STAGES
    assert "complete" in V2_STAGES
    events = []
    budget = ProviderBudget(provider="p", model="m")

    def progress(stage, pct, cur_w, total_w, cur_ch):
        events.append((stage, pct, cur_w, total_w, cur_ch))

    run_hierarchical_pipeline(_metas(12), book_id=1, budget=budget, progress=progress)
    stages = [e[0] for e in events]
    assert stages[0] == "prepare_source"
    assert "extract_windows" in stages
    assert stages[-1] == "complete"
    # Percent / window counters must move during long work.
    extract_events = [e for e in events if e[0] == "extract_windows"]
    assert extract_events and extract_events[-1][1] == 100
    snap = progress_snapshot(
        stage_index=3, stage_percent=50, current_window=2, total_windows=5,
        current_chapter=40, total_chapters=100, provider_calls_completed=2,
        provider_calls_estimated=20, provider="p", model="m", elapsed=30,
        last_action="抽取窗口", current_action="抽取窗口",
    )
    assert snap.overall_percent > 0 and snap.current_window == 2


def test_engine_hierarchical_produces_valid_v2():
    result = WholeBookV2Engine().run(run_id=73, book_id=1, title="h", chapters=_sources(20))
    assert WholeBookAnalysisV2.model_validate_json(result.model_dump_json()) == result
    assert result.analysis_metadata.real_provider_calls == 0
    assert result.characters.protagonist.stages
    assert result.characters.protagonist.core_transformation
    assert result.pacing.points[0].chapter_id is not None
    assert result.type_profile.genre_expectations
    assert result.assessment.overall_assessment
