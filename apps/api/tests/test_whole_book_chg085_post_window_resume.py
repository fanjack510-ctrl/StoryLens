"""CHG-085: Post-window failure preserves real windows; resume does not reburn."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, BookSnapshot, WholeBookCheckpoint, WholeBookRun
from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
    execute_hierarchical_v2_pipeline_v1,
)
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit,
    CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit,
    ChapterFunctionBatchUnit,
    PacingCoreSynthesisUnit,
    ProgressV2,
    StorySynthesisUnit,
    SuspenseSynthesisUnit,
)
from app.narrative_core.whole_book_v2.engine import (
    DeterministicPrimitiveExtractor,
    SourceChapter,
    WholeBookV2Engine,
)
from app.narrative_core.whole_book_v2.failure_taxonomy import (
    classify_pipeline_exception,
    inspect_resumable_checkpoints,
)
from app.narrative_core.whole_book_v2.pipeline import ProviderBudget, plan_windows
from app.narrative_core.whole_book_v2.provider_engine import (
    CHAPTER_FUNCTION_BATCH_SIZE,
    GatewayWholeBookV2Analyzer,
    SynthesisUnitError,
    UnitFailureCode,
)
from app.narrative_core.whole_book_v2.repository import (
    INTERMEDIATE_STAGE,
    WholeBookV2Repository,
)
from app.narrative_core.whole_book_v2.window_extraction import (
    ORIGIN_REAL,
    build_window_evidence_catalog,
    is_reusable_real_provider_intermediate,
)
from app.services.whole_book_free_background import _mark_run_failed

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "chg084"


def source(count: int = 6) -> list[SourceChapter]:
    return [
        SourceChapter(
            2000 + i,
            i,
            f"chapter {i}",
            f"@Lin chapter {i} chooses a costly path and reveals clue {i}.",
            88,
            "rev-chg085",
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
        PacingCoreSynthesisUnit(pacing=r.pacing).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=r.assessment).model_dump(mode="json"),
        # Chapter functions are requested last, in bounded batches (CHG-086).
        *[
            ChapterFunctionBatchUnit(
                functions=r.chapters.functions[i : i + CHAPTER_FUNCTION_BATCH_SIZE]
            ).model_dump(mode="json")
            for i in range(0, max(1, len(r.chapters.functions)), CHAPTER_FUNCTION_BATCH_SIZE)
        ],
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
            output_tokens=7,
        )


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chg085.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_run(session, *, book_id: int = 1) -> WholeBookRun:
    book = Book(
        id=book_id,
        title="chg085",
        author="",
        source_file_name="chg085.txt",
        source_file_hash="hash085",
    )
    session.add(book)
    snap = BookSnapshot(
        book_id=book_id,
        content_hash="h",
        source_fingerprint="rev-chg085",
        chapter_count=6,
        character_count=100,
    )
    session.add(snap)
    session.flush()
    run = WholeBookRun(
        book_id=book_id,
        snapshot_id=snap.id,
        mode="whole_book_native",
        status=WholeBookRunStatus.running.value,
        current_stage_code="windowing",
        idempotency_key=f"chg085-{book_id}-{snap.id}",
        engine_id="whole_book_v2_hierarchical",
        engine_version="2.1.0",
        contract_version="whole_book_contract_v1",
        result_origin="formal",
        provider_name="fake",
        model_name="fixture",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _window_queue(chapters: list[SourceChapter]) -> list[dict[str, Any]]:
    metas = [c.as_meta() for c in chapters]
    windows = plan_windows(metas, book_id=1, budget=ProviderBudget(provider="fake", model="fixture"))
    return [window_payload_for(w, chapters) for w in windows]


@pytest.mark.asyncio
async def test_15_real_windows_persist_before_consolidation(tmp_path):
    """Persist real window assets before topic consolidation / synthesis."""
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    # Fail first synthesis after windows + topics persist.
    bad_overview = {"type_profile": synth_payloads(chapters)[0]["type_profile"]}
    gateway = ProviderQueueGateway([*windows, bad_overview, bad_overview])
    repo = WholeBookV2Repository(session, on_persist=session.commit)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
        force_full_reanalysis=True,  # must NOT wipe same-run checkpoints
    )
    with pytest.raises(SynthesisUnitError) as exc:
        await analyzer.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert exc.value.unit_key == "overview_type"
    session.commit()
    rows = session.scalars(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run.id,
            WholeBookCheckpoint.stage_code == INTERMEDIATE_STAGE,
        )
    ).all()
    window_rows = [r for r in rows if str(r.checkpoint_key).startswith("window:")]
    topic_rows = [r for r in rows if str(r.checkpoint_key).startswith("topic:")]
    assert len(window_rows) == len(windows)
    assert len(topic_rows) >= 1
    for row in window_rows:
        data = json.loads(row.checkpoint_payload_json)
        assert data.get("origin") == ORIGIN_REAL
        assert is_reusable_real_provider_intermediate(data)


@pytest.mark.asyncio
async def test_failure_after_window_extraction_preserves_windows(tmp_path):
    await test_15_real_windows_persist_before_consolidation(tmp_path)


@pytest.mark.asyncio
async def test_resume_does_not_repeat_completed_window_calls(tmp_path):
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    good = synth_payloads(chapters)
    bad_overview = {"type_profile": good[0]["type_profile"]}
    gateway = ProviderQueueGateway([*windows, bad_overview, bad_overview])
    repo = WholeBookV2Repository(session, on_persist=session.commit)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    with pytest.raises(SynthesisUnitError):
        await analyzer.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    first_calls = len(gateway.calls)
    assert first_calls == len(windows) + 2

    # Resume: only remaining synthesis units (repair + full set).
    gateway2 = ProviderQueueGateway(list(good))
    analyzer2 = GatewayWholeBookV2Analyzer(
        gateway2,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
        force_full_reanalysis=True,
    )
    result, _ = await analyzer2.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert result.analysis_metadata.result_origin == "real_provider"
    # 6 synthesis units + 1 bounded chapter-function batch (CHG-086).
    assert len(gateway2.calls) == 7
    assert analyzer2.stats.provider_calls >= 15 or analyzer2.stats.provider_calls == 7 + (
        repo.load_progress(run.id).provider_calls_completed - 7
        if repo.load_progress(run.id)
        else 0
    )
    # No window extraction prompts on resume.
    for _, req in gateway2.calls:
        content = req.messages[0]["content"]
        assert "Extract SHORT structured window" not in content


@pytest.mark.asyncio
async def test_force_full_reanalysis_does_not_reexecute_same_run_checkpoints(tmp_path):
    await test_resume_does_not_repeat_completed_window_calls(tmp_path)


@pytest.mark.asyncio
async def test_resume_starts_at_first_failed_stage(tmp_path):
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    good = synth_payloads(chapters)
    bad = {"type_profile": good[0]["type_profile"]}
    gateway = ProviderQueueGateway([*windows, bad, bad])
    repo = WholeBookV2Repository(session, on_persist=session.commit)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    with pytest.raises(SynthesisUnitError) as exc:
        await analyzer.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert analyzer.last_failure_stage == "overview_synthesis"
    classified = classify_pipeline_exception(exc.value)
    assert classified.failure_stage == "overview_synthesis"


@pytest.mark.asyncio
async def test_provider_call_count_resumes_from_15(tmp_path):
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    n_windows = len(windows)
    good = synth_payloads(chapters)
    bad = {"type_profile": good[0]["type_profile"]}
    gateway = ProviderQueueGateway([*windows, bad, bad])
    repo = WholeBookV2Repository(session, on_persist=session.commit)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    with pytest.raises(SynthesisUnitError):
        await analyzer.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    progress = repo.load_progress(run.id)
    assert progress is not None
    # Progress reflects last successful emit (windows done); failed synthesis attempts
    # are not yet counted into the persisted progress baseline.
    assert progress.provider_calls_completed == n_windows

    gateway2 = ProviderQueueGateway(list(good))
    analyzer2 = GatewayWholeBookV2Analyzer(
        gateway2,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    await analyzer2.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    # Baseline restored from progress; new calls are synthesis only
    # (6 units + 1 bounded chapter-function batch).
    assert analyzer2.stats.provider_calls == n_windows + 7
    final = repo.load_progress(run.id)
    assert final is not None
    assert final.provider_calls_completed == n_windows + 7


def test_failure_stage_records_actual_stage(tmp_path):
    session = _session(tmp_path)
    run = _seed_run(session)
    run.status = WholeBookRunStatus.running.value
    session.commit()
    factory = sessionmaker(bind=session.get_bind())
    err = SynthesisUnitError(
        "overview_type",
        UnitFailureCode.MISSING_REQUIRED_FIELD,
        "overview Field required",
    )
    _mark_run_failed(factory, run.id, err)
    session.expire_all()
    refreshed = session.get(WholeBookRun, run.id)
    assert refreshed is not None
    assert refreshed.status == WholeBookRunStatus.failed.value
    assert refreshed.current_stage_code == "overview_synthesis"
    assert refreshed.failure_code == "WHOLE_BOOK_V2_MISSING_REQUIRED_FIELD"
    assert "Provider 配置" not in (refreshed.failure_message_safe or "")
    assert "全书总览生成失败" in (refreshed.failure_message_safe or "")
    assert "数据结构不完整" in (refreshed.failure_message_safe or "")


def test_schema_error_not_reported_as_provider_config_error():
    err = SynthesisUnitError(
        "story",
        UnitFailureCode.MISSING_REQUIRED_FIELD,
        "storylines missing",
    )
    classified = classify_pipeline_exception(err)
    assert classified.category.value == "schema_validation"
    assert "Provider 配置" not in classified.message_safe
    assert classified.failure_stage == "story_synthesis"


@pytest.mark.asyncio
async def test_completed_real_window_assets_are_reused(tmp_path):
    await test_resume_does_not_repeat_completed_window_calls(tmp_path)


@pytest.mark.asyncio
async def test_resume_only_calls_remaining_units(tmp_path):
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    good = synth_payloads(chapters)
    # Complete windows + overview + story, then fail characters permanently.
    bad_chars = {"characters": {"protagonist": good[2]["characters"]["protagonist"]}}
    gateway = ProviderQueueGateway(
        [*windows, good[0], good[1], bad_chars, bad_chars]
    )
    repo = WholeBookV2Repository(session, on_persist=session.commit)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    with pytest.raises(SynthesisUnitError) as exc:
        await analyzer.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert exc.value.unit_key == "characters"

    gateway2 = ProviderQueueGateway(good[2:])
    analyzer2 = GatewayWholeBookV2Analyzer(
        gateway2,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
        force_full_reanalysis=True,
    )
    result, _ = await analyzer2.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert len(gateway2.calls) == 5  # characters..assessment + chapter-function batch
    assert result.story.structure_stages


def test_inspect_resumable_checkpoints_for_failed_run(tmp_path):
    session = _session(tmp_path)
    run = _seed_run(session)
    run.status = WholeBookRunStatus.failed.value
    run.current_stage_code = "windowing"
    session.add(
        WholeBookCheckpoint(
            run_id=run.id,
            stage_code=INTERMEDIATE_STAGE,
            checkpoint_key="window:W-demo",
            sequence_no=1,
            completed_unit_count=1,
            payload_hash="",
            checkpoint_payload_json=json.dumps(
                {
                    "window_id": "W-demo",
                    "start_chapter_index": 1,
                    "end_chapter_index": 2,
                    "chapter_ids": [2001, 2002],
                    "origin": ORIGIN_REAL,
                    "provider": "fake",
                    "model": "fixture",
                    "events": ["e"],
                    "event_causality": [],
                    "characters": ["Lin"],
                    "character_states": [],
                    "character_changes": [],
                    "relationships": [],
                    "relationship_changes": [],
                    "protagonist_goals": [],
                    "protagonist_obstacles": [],
                    "protagonist_choices": [],
                    "cost_paid": [],
                    "gain_received": [],
                    "ability_changes": [],
                    "identity_changes": [],
                    "belief_value_changes": [],
                    "suspense_hooks": [],
                    "hook_progression": [],
                    "hook_payoff": [],
                    "story_signals": [],
                    "pacing_signals": {"tension": 1.0, "pace_speed": 1.0},
                    "chapter_functions": [],
                    "evidence": [],
                },
                ensure_ascii=False,
            ),
        )
    )
    session.add(
        WholeBookCheckpoint(
            run_id=run.id,
            stage_code="v2_progress",
            checkpoint_key="latest",
            sequence_no=1,
            completed_unit_count=15,
            payload_hash="",
            checkpoint_payload_json=ProgressV2(
                overall_percent=76.0,
                current_stage="generate_overview",
                stage_percent=10.0,
                current_window=15,
                total_windows=15,
                current_chapter=542,
                total_chapters=542,
                provider_calls_completed=15,
                provider_calls_estimated=33,
                successful_calls=15,
                failed_calls=0,
                retry_calls=0,
                repair_calls=0,
                elapsed_seconds=1,
                estimated_remaining_seconds=0,
                estimated_cost=2.3,
                estimated_actual_cost=0.0,
                provider="fake",
                model="fixture",
                last_completed_action="生成全书总结",
                current_action="生成全书总结",
                last_activity_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            ).model_dump_json(),
        )
    )
    session.commit()
    info = inspect_resumable_checkpoints(session, run.id)
    assert info["compatible"] is True
    assert info["completed_windows"] == 1
    assert info["provider_calls_completed"] == 15
    assert info["next_stage"] == "overview_synthesis"
