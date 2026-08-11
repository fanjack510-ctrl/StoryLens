"""CHG-085 synthesis contract alignment + overview missing-field repair fixture."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, BookSnapshot, WholeBookCheckpoint, WholeBookRun
from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
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
)
from app.narrative_core.whole_book_v2.failure_taxonomy import classify_pipeline_exception
from app.narrative_core.whole_book_v2.pipeline import ProviderBudget, plan_windows
from app.narrative_core.whole_book_v2.provider_engine import (
    UNIT_REQUIRED_TOP_LEVEL,
    UNIT_SCHEMAS,
    GatewayWholeBookV2Analyzer,
    SynthesisUnitError,
    UnitFailureCode,
    build_synthesis_repair_prompt,
    build_synthesis_unit_prompt,
    required_top_level_fields,
)
from app.narrative_core.whole_book_v2.repository import (
    INTERMEDIATE_STAGE,
    WholeBookV2Repository,
)
from app.narrative_core.whole_book_v2.window_extraction import (
    ORIGIN_REAL,
    build_window_evidence_catalog,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "chg085" / "overview_type_missing_overview.json"
)


def source(count: int = 6) -> list[SourceChapter]:
    return [
        SourceChapter(
            3000 + i,
            i,
            f"chapter {i}",
            f"@Lin chapter {i} chooses a costly path and reveals clue {i}.",
            99,
            "rev-chg085-synth",
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
            output_tokens=7,
        )


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chg085-synth.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_run(session, *, book_id: int = 1) -> WholeBookRun:
    book = Book(
        id=book_id,
        title="chg085-synth",
        author="",
        source_file_name="chg085-synth.txt",
        source_file_hash="hash085s",
    )
    session.add(book)
    snap = BookSnapshot(
        book_id=book_id,
        content_hash="h",
        source_fingerprint="rev-chg085-synth",
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
        idempotency_key=f"chg085-synth-{book_id}-{snap.id}",
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


@pytest.mark.parametrize(
    "unit_key,schema",
    list(UNIT_SCHEMAS.items()),
)
def test_synthesis_unit_prompt_dto_schema_alignment(unit_key, schema):
    required = required_top_level_fields(schema, unit_key)
    assert set(required) == set(UNIT_REQUIRED_TOP_LEVEL[unit_key])
    assert set(required) == set(schema.model_json_schema().get("required") or [])
    prompt = build_synthesis_unit_prompt(unit_key, schema, {"note": "intermediate"})
    for field in required:
        assert f"- {field}" in prompt
        assert field in prompt
    assert "SCHEMA:" in prompt
    err = SynthesisUnitError(unit_key, UnitFailureCode.MISSING_REQUIRED_FIELD, f"{required[0]} missing")
    repair = build_synthesis_repair_prompt(
        unit_key, schema, error=err, invalid_output='{"partial":true}'
    )
    assert "COMPLETE corrected JSON object" in repair
    assert "Do NOT return only the missing fields" in repair
    assert "VALIDATION_ERROR:" in repair
    for field in required:
        assert f"- {field}" in repair


def test_overview_type_missing_overview_fixture_rejects_dto():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = {k: v for k, v in raw.items() if not str(k).startswith("_")}
    assert "type_profile" in payload
    assert "overview" not in payload
    with pytest.raises(ValidationError) as exc:
        OverviewTypeSynthesisUnit.model_validate(payload)
    assert any(e.get("loc") == ("overview",) for e in exc.value.errors())


@pytest.mark.asyncio
async def test_overview_type_missing_overview_repairs_to_valid_contract(tmp_path):
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    good = synth_payloads(chapters)
    bad_raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = {k: v for k, v in bad_raw.items() if not str(k).startswith("_")}
    # Map fixture evidence ids onto catalog-safe ids from good overview later; keep shape.
    bad["type_profile"] = good[0]["type_profile"]
    gateway = ProviderQueueGateway([*windows, bad, good[0], *good[1:]])
    repo = WholeBookV2Repository(session, on_persist=session.commit)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
    )
    result, _ = await analyzer.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert result.overview.one_sentence_story
    assert analyzer.stats.repair_calls == 1
    # First synthesis call is overview_type base; second is repair.
    overview_calls = [
        req for _, req in gateway.calls if "synthesis unit overview_type" in req.messages[0]["content"]
        or "Repair ONLY synthesis unit overview_type" in req.messages[0]["content"]
    ]
    assert len(overview_calls) == 2
    repair_prompt = overview_calls[1].messages[0]["content"]
    assert "Required top-level fields" in repair_prompt
    assert "- overview" in repair_prompt
    assert "- type_profile" in repair_prompt
    assert "COMPLETE corrected JSON object" in repair_prompt
    assert "VALIDATION_ERROR:" in repair_prompt
    OverviewTypeSynthesisUnit.model_validate(
        {"type_profile": result.type_profile.model_dump(mode="json"), "overview": result.overview.model_dump(mode="json")}
    )


@pytest.mark.asyncio
async def test_resume_after_overview_failure_keeps_15_completed_windows(tmp_path):
    chapters = source(6)
    session = _session(tmp_path)
    run = _seed_run(session)
    windows = _window_queue(chapters)
    n_windows = len(windows)
    good = synth_payloads(chapters)
    bad_raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = {k: v for k, v in bad_raw.items() if not str(k).startswith("_")}
    bad["type_profile"] = good[0]["type_profile"]
    # Fail permanently on first pass (bad + bad repair).
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
    assert exc.value.unit_key == "overview_type"
    classified = classify_pipeline_exception(exc.value)
    assert classified.failure_stage == "overview_synthesis"
    assert "Provider 配置" not in classified.message_safe
    assert "全书总览生成失败" in classified.message_safe

    window_rows = session.scalars(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run.id,
            WholeBookCheckpoint.stage_code == INTERMEDIATE_STAGE,
            WholeBookCheckpoint.checkpoint_key.like("window:%"),
        )
    ).all()
    assert len(window_rows) == n_windows

    gateway2 = ProviderQueueGateway(list(good))
    analyzer2 = GatewayWholeBookV2Analyzer(
        gateway2,
        provider_name="fake",
        model_name="fixture",
        repository=repo,
        budget=ProviderBudget(provider="fake", model="fixture"),
        force_full_reanalysis=True,
    )
    await analyzer2.analyze(run_id=run.id, book_id=1, title="t", chapters=chapters)
    assert analyzer2.stats.window_calls == 0
    for _, req in gateway2.calls:
        assert "Extract SHORT structured window" not in req.messages[0]["content"]
    progress = repo.load_progress(run.id)
    assert progress is not None
    assert progress.provider_calls_completed >= n_windows + 6
