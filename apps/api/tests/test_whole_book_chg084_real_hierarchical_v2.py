"""CHG-084: Real Hierarchical V2 Provider window extraction + formal contracts."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AnalysisRun, Base, Book, ModelInvocation, WholeBookRun
from app.model_gateway.base import ModelResponse
from app.narrative_core.services.whole_book_gateway_transport_v1 import _run_async
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit,
    CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit,
    PacingSynthesisUnit,
    StorySynthesisUnit,
    SuspenseSynthesisUnit,
)
from app.narrative_core.whole_book_v2.engine import (
    DeterministicPrimitiveExtractor,
    SourceChapter,
    WholeBookV2Engine,
    progress_snapshot,
)
from app.narrative_core.whole_book_v2.pipeline import (
    ChapterMeta,
    ProviderBudget,
    build_cost_plan,
    build_token_plan,
    extract_window_asset,
    plan_windows,
)
from app.narrative_core.whole_book_v2.provider_engine import (
    UNIT_REQUIRED_HINTS,
    UNIT_SCHEMAS,
    GatewayWholeBookV2Analyzer,
    recover_json_object,
)
from app.narrative_core.whole_book_v2.result_origin import (
    detect_scaffold,
    product_flags_for_result,
)
from app.narrative_core.whole_book_v2.task_center_projection import (
    merge_whole_book_runs_into_task_list,
    project_whole_book_run,
)
from app.narrative_core.whole_book_v2.usage_ledger import (
    TASK_TYPE,
    count_usage_calls,
    ensure_task_projection,
    record_provider_call,
)
from app.narrative_core.whole_book_v2.window_extraction import (
    ORIGIN_REAL,
    ORIGIN_SCAFFOLD,
    build_window_evidence_catalog,
    contains_scaffold_semantics,
    is_reusable_real_provider_intermediate,
    materialize_window_asset_from_provider,
    validate_evidence_ids,
)
from app.services.whole_book_free_background import (
    schedule_free_whole_book_pipeline_background,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "chg084"


def source(count: int = 3) -> list[SourceChapter]:
    return [
        SourceChapter(
            1000 + i,
            i,
            f"chapter {i}",
            f"@Lin chapter {i} chooses a costly path and reveals clue {i}.",
            77,
            "rev",
        )
        for i in range(1, count + 1)
    ]


def synth_payloads(chapters: list[SourceChapter]) -> list[dict[str, Any]]:
    r = WholeBookV2Engine(DeterministicPrimitiveExtractor(), window_size=3, overlap=0).run(
        run_id=1, book_id=1, title="fixture", chapters=chapters
    )
    return [
        OverviewTypeSynthesisUnit(type_profile=r.type_profile, overview=r.overview).model_dump(
            mode="json"
        ),
        StorySynthesisUnit(story=r.story).model_dump(mode="json"),
        CharactersSynthesisUnit(characters=r.characters).model_dump(mode="json"),
        SuspenseSynthesisUnit(suspense=r.suspense).model_dump(mode="json"),
        PacingSynthesisUnit(pacing=r.pacing, chapters=r.chapters).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=r.assessment).model_dump(mode="json"),
    ]


def window_payload_for(window, chapters) -> dict[str, Any]:
    catalog = build_window_evidence_catalog(window, [c.as_meta() for c in chapters])
    ids = [e.evidence_id for e in catalog]
    return {
        "events": [f"Lin faces a costly choice in window {window.window_id}"],
        "event_causality": ["choice raises stakes"],
        "characters": ["Lin"],
        "character_states": ["Lin is committed"],
        "character_changes": ["Lin accepts risk"],
        "relationships": ["Lin|ally|trust"],
        "relationship_changes": ["trust deepens"],
        "protagonist_goals": ["secure the next clue"],
        "protagonist_obstacles": ["hostile watchers"],
        "protagonist_choices": ["expose identity briefly"],
        "cost_paid": ["cover blown"],
        "gain_received": ["new lead"],
        "ability_changes": ["improvised cover craft"],
        "identity_changes": ["undercover edge hardens"],
        "belief_value_changes": ["duty outweighs safety"],
        "suspense_hooks": ["who tipped the watchers"],
        "hook_progression": ["pressure increases"],
        "hook_payoff": [],
        "story_signals": ["mainline advance"],
        "pacing_signals": {"tension": 62.0, "pace_speed": 55.0},
        "chapter_functions": ["mainline_progress"],
        "evidence_ids": ids,
    }


class ProviderQueueGateway:
    def __init__(self, items: list[Any]):
        self.items = list(items)
        self.calls: list[Any] = []
        self.deterministic_extraction = False
        self.disallow_local_merge = True

    async def generate(self, provider, request):
        self.calls.append((provider, request))
        if not self.items:
            raise RuntimeError("provider queue exhausted")
        item = self.items.pop(0)
        if isinstance(item, ModelResponse):
            return item
        return ModelResponse(
            text=json.dumps(item, ensure_ascii=False),
            model="fixture",
            finish_reason="stop",
            input_tokens=11,
            output_tokens=22,
            request_id="req-fixture",
        )


def full_provider_queue(chapters: list[SourceChapter]) -> list[dict[str, Any]]:
    metas = [c.as_meta() for c in chapters]
    windows = plan_windows(metas, book_id=1, budget=ProviderBudget(provider="fake", model="fixture"))
    items = [window_payload_for(w, chapters) for w in windows]
    items.extend(synth_payloads(chapters))
    return items


@pytest.mark.asyncio
async def test_production_window_extraction_uses_provider():
    chapters = source()
    gateway = ProviderQueueGateway(full_provider_queue(chapters))
    analyzer = GatewayWholeBookV2Analyzer(gateway, provider_name="fake", model_name="fixture")
    result, _ = await analyzer.analyze(run_id=8401, book_id=1, title="x", chapters=chapters)
    assert analyzer.stats.window_calls >= 1
    assert analyzer.stats.provider_calls >= analyzer.stats.window_calls
    assert result.analysis_metadata.result_origin == "real_provider"
    first_prompt = gateway.calls[0][1].messages[0]["content"]
    assert "EVIDENCE_CATALOG" in first_prompt
    assert "evidence_ids" in first_prompt


@pytest.mark.asyncio
async def test_production_window_extraction_never_returns_scaffold():
    chapters = source()
    gateway = ProviderQueueGateway(full_provider_queue(chapters))
    analyzer = GatewayWholeBookV2Analyzer(gateway, provider_name="fake", model_name="fixture")
    await analyzer.analyze(run_id=8402, book_id=1, title="x", chapters=chapters)
    for key, asset in analyzer.asset_ledger.successful.items():
        if not str(key).startswith("window:"):
            continue
        assert getattr(asset, "origin", None) == ORIGIN_REAL
        assert not contains_scaffold_semantics(asset)


def test_deterministic_scaffold_rejected_from_formal_result():
    chapters = source()
    r = WholeBookV2Engine(DeterministicPrimitiveExtractor(), window_size=3, overlap=0).run(
        run_id=1, book_id=1, title="scaffold", chapters=chapters
    )
    assert detect_scaffold(r) is True
    flags = product_flags_for_result(r)
    assert flags["is_real_provider_result"] is False
    assert flags["needs_reanalysis"] is True
    assert flags["non_real_result"] is True


def test_real_provider_intermediate_origin():
    chapters = source()
    metas = [c.as_meta() for c in chapters]
    windows = plan_windows(metas, book_id=1, budget=ProviderBudget(provider="fake", model="m"))
    catalog = build_window_evidence_catalog(windows[0], metas)
    asset = materialize_window_asset_from_provider(
        window=windows[0],
        catalog=catalog,
        payload=window_payload_for(windows[0], chapters),
        provider="fake",
        model="m",
        origin=ORIGIN_REAL,
    )
    assert is_reusable_real_provider_intermediate(asset)
    scaffold = extract_window_asset(windows[0], metas)
    assert scaffold.origin == ORIGIN_SCAFFOLD
    assert not is_reusable_real_provider_intermediate(scaffold)


@pytest.mark.asyncio
async def test_force_full_reanalysis_does_not_reuse_intermediate():
    chapters = source()
    gateway = ProviderQueueGateway(full_provider_queue(chapters))
    analyzer = GatewayWholeBookV2Analyzer(gateway, provider_name="fake", model_name="fixture")
    await analyzer.analyze(run_id=8403, book_id=1, title="x", chapters=chapters)
    calls_first = len(gateway.calls)
    gateway.items = full_provider_queue(chapters)
    analyzer2 = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        asset_ledger=analyzer.asset_ledger,
        ledger=analyzer.ledger,
        force_full_reanalysis=True,
    )
    await analyzer2.analyze(run_id=8403, book_id=1, title="x", chapters=chapters)
    assert len(gateway.calls) > calls_first
    assert analyzer2.stats.window_calls >= 1


@pytest.mark.asyncio
async def test_safe_reanalysis_only_reuses_real_provider_intermediate():
    chapters = source()
    gateway = ProviderQueueGateway(full_provider_queue(chapters))
    analyzer = GatewayWholeBookV2Analyzer(gateway, provider_name="fake", model_name="fixture")
    await analyzer.analyze(run_id=8404, book_id=1, title="x", chapters=chapters)
    calls_after_first = len(gateway.calls)
    gateway.items = synth_payloads(chapters)
    analyzer2 = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        asset_ledger=analyzer.asset_ledger,
        ledger=analyzer.ledger,
        force_full_reanalysis=False,
    )
    await analyzer2.analyze(run_id=8404, book_id=1, title="x", chapters=chapters)
    assert len(gateway.calls) == calls_after_first
    assert analyzer2.stats.window_calls == 0


def test_window_evidence_ids_validate():
    chapters = source()
    metas = [c.as_meta() for c in chapters]
    windows = plan_windows(metas, book_id=1, budget=ProviderBudget(provider="fake", model="m"))
    catalog = build_window_evidence_catalog(windows[0], metas)
    validate_evidence_ids([catalog[0].evidence_id], catalog)
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_evidence_ids(["E-NOT-REAL-0"], catalog)
    payload = window_payload_for(windows[0], chapters)
    payload["evidence_ids"] = ["E-HALLUCINATED-0"]
    with pytest.raises(ValueError):
        materialize_window_asset_from_provider(
            window=windows[0],
            catalog=catalog,
            payload=payload,
            provider="fake",
            model="m",
        )


def test_story_real_response_regression_fixture():
    failed = json.loads(
        (FIXTURE_DIR / "story_deepseek_missing_fields.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ValidationError):
        StorySynthesisUnit.model_validate(failed)
    repaired = json.loads((FIXTURE_DIR / "story_complete_unit.json").read_text(encoding="utf-8"))
    unit = StorySynthesisUnit.model_validate(repaired)
    assert unit.story.storylines
    assert unit.story.causal_chain
    assert unit.story.chronology
    raw = json.dumps(failed, ensure_ascii=False)
    assert recover_json_object(raw) == failed


def test_all_synthesis_prompt_schema_contracts_match():
    for key, schema in UNIT_SCHEMAS.items():
        assert key in UNIT_REQUIRED_HINTS
        js = schema.model_json_schema()
        assert isinstance(js, dict)
        props = js.get("properties") or {}
        assert props, key
        if key == "story":
            dumped = json.dumps(js)
            assert "storylines" in dumped
            assert "causal_chain" in dumped
            assert "chronology" in dumped
            assert "structure_stages" in dumped


@pytest.mark.asyncio
async def test_failed_synthesis_repairs_only_failed_unit():
    chapters = source()
    good = synth_payloads(chapters)
    windows = plan_windows(
        [c.as_meta() for c in chapters],
        book_id=1,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    items = [window_payload_for(w, chapters) for w in windows]
    bad_story = json.loads(json.dumps(good[1]))
    del bad_story["story"]["storylines"]
    del bad_story["story"]["causal_chain"]
    del bad_story["story"]["chronology"]
    items.extend([good[0], bad_story, good[1], *good[2:]])
    gateway = ProviderQueueGateway(items)
    analyzer = GatewayWholeBookV2Analyzer(gateway, provider_name="fake", model_name="fixture")
    await analyzer.analyze(run_id=8405, book_id=1, title="x", chapters=chapters)
    assert analyzer.stats.repair_calls == 1
    assert analyzer.stats.provider_calls == len(windows) + 7


def test_progress_tracks_real_provider_completion():
    snap0 = progress_snapshot(
        stage_index=3,
        stage_percent=100,
        current_window=15,
        total_windows=15,
        current_chapter=542,
        total_chapters=542,
        provider_calls_completed=0,
        provider_calls_estimated=33,
        provider="deepseek",
        model="x",
        elapsed=10,
        last_action="抽取窗口",
        current_action="抽取窗口",
    )
    assert snap0.provider_calls_completed == 0
    assert snap0.overall_percent <= 5.0
    snap1 = progress_snapshot(
        stage_index=3,
        stage_percent=50,
        current_window=8,
        total_windows=15,
        current_chapter=200,
        total_chapters=542,
        provider_calls_completed=8,
        provider_calls_estimated=33,
        provider="deepseek",
        model="x",
        elapsed=100,
        last_action="抽取窗口",
        current_action="抽取窗口",
    )
    assert snap1.overall_percent > snap0.overall_percent
    assert snap1.overall_percent < 70


def test_zero_provider_calls_cannot_show_high_progress():
    for stage_index in range(0, 10):
        snap = progress_snapshot(
            stage_index=stage_index,
            stage_percent=100,
            current_window=15,
            total_windows=15,
            current_chapter=542,
            total_chapters=542,
            provider_calls_completed=0,
            provider_calls_estimated=33,
            provider="deepseek",
            model="x",
            elapsed=30,
            last_action="x",
            current_action="x",
        )
        assert snap.overall_percent <= 5.0, (stage_index, snap.overall_percent)


def test_v2_calls_written_to_usage_ledger():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        book = Book(title="t", author="", source_file_name="t.txt", source_file_hash="abc")
        session.add(book)
        session.flush()
        wb = WholeBookRun(
            book_id=book.id,
            mode="whole_book_native",
            status="running",
            idempotency_key="chg084-ledger",
            engine_id="whole_book_v2_hierarchical",
            engine_version="2.1.0",
            contract_version="v2",
            result_origin="formal",
            provider_name="fake",
            model_name="fixture",
        )
        session.add(wb)
        session.flush()
        ensure_task_projection(session, wb)
        resp = ModelResponse(
            text="{}",
            model="fixture",
            finish_reason="stop",
            input_tokens=3,
            output_tokens=5,
            request_id="r1",
        )
        record_provider_call(
            session,
            whole_book_run_id=int(wb.id),
            unit_key="window:w1",
            provider="fake",
            model="fixture",
            response=resp,
            window_id="w1",
        )
        session.commit()
        assert count_usage_calls(session, int(wb.id)) == 1
        inv = session.query(ModelInvocation).one()
        assert inv.task_type == TASK_TYPE
        assert inv.input_tokens == 3
        ar = session.query(AnalysisRun).filter(AnalysisRun.task_type == TASK_TYPE).one()
        assert ar.book_id == book.id


def test_task_center_projects_whole_book_run():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        book = Book(title="余罪", author="", source_file_name="yuzui.txt", source_file_hash="def")
        session.add(book)
        session.flush()
        wb = WholeBookRun(
            book_id=book.id,
            mode="whole_book_native",
            status="running",
            idempotency_key="chg084-task",
            engine_id="whole_book_v2_hierarchical",
            engine_version="2.1.0",
            contract_version="v2",
            result_origin="formal",
            provider_name="deepseek",
            model_name="deepseek-v4-flash",
        )
        session.add(wb)
        session.flush()
        projected = project_whole_book_run(session, wb)
        assert projected.task_type == "whole_book_v2"
        assert projected.mode_label == "全书 V2"
        assert projected.whole_book_run_id == wb.id
        merged = merge_whole_book_runs_into_task_list(session, [], book_id=book.id)
        assert any(r.task_type == "whole_book_v2" for r in merged)


def test_failed_new_run_does_not_auto_show_scaffold_as_completed():
    chapters = source()
    r = WholeBookV2Engine(DeterministicPrimitiveExtractor(), window_size=3, overlap=0).run(
        run_id=3, book_id=1, title="scaffold", chapters=chapters
    )
    flags = product_flags_for_result(r)
    assert flags["is_real_provider_result"] is False
    assert flags["result_origin"] != "real_provider" or flags["scaffold_detected"]


def test_background_executor_has_valid_event_loop():
    async def _probe():
        loop = asyncio.get_running_loop()
        assert loop.is_running()
        return "ok"

    assert _run_async(_probe()) == "ok"

    async def _nested():
        return _run_async(_probe())

    assert asyncio.run(_nested()) == "ok"


def test_background_failure_does_not_kill_sidecar():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    thread = schedule_free_whole_book_pipeline_background(Session, run_id=999999)
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_542_chapter_dry_run_includes_window_extraction_calls():
    budget = ProviderBudget(provider="deepseek", model="deepseek-v4-flash")
    chapters = [
        ChapterMeta(
            chapter_id=i,
            chapter_index=i,
            title=f"c{i}",
            text="字" * 5400,
            snapshot_id=1,
            revision_hash="r",
        )
        for i in range(1, 543)
    ]
    windows = plan_windows(chapters, book_id=2, budget=budget)
    plan = build_token_plan(windows, budget=budget)
    plan = plan.model_copy(update={"chapter_count": 542})
    cost = build_cost_plan(plan, budget)
    assert plan.window_count == len(windows)
    assert plan.extract_calls == plan.window_count
    assert plan.final_synthesis_calls == 6
    assert plan.repair_reserve_calls >= 1
    assert plan.estimated_total_calls == (
        plan.extract_calls
        + plan.consolidation_calls
        + plan.final_synthesis_calls
        + plan.repair_reserve_calls
    )
    print(
        "DRYRUN542",
        plan.window_count,
        plan.extract_calls,
        plan.consolidation_calls,
        plan.final_synthesis_calls,
        plan.repair_reserve_calls,
        plan.estimated_total_calls,
        plan.estimated_input_tokens,
        plan.estimated_output_tokens,
        getattr(cost, "estimated_cost_low", None),
        getattr(cost, "estimated_cost_high", None),
    )


@pytest.mark.asyncio
async def test_formal_path_forbids_deterministic_extraction_flag():
    chapters = source()
    gateway = ProviderQueueGateway([])
    gateway.deterministic_extraction = True
    gateway.disallow_local_merge = True
    analyzer = GatewayWholeBookV2Analyzer(gateway, provider_name="fake", model_name="fixture")
    with pytest.raises(Exception, match="deterministic_extraction|SCAFFOLD|scaffold"):
        await analyzer.analyze(run_id=8406, book_id=1, title="x", chapters=chapters)
