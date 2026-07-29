"""CHG-041 Round 7: UTF-8 fixture text + Fake dynamic scenes after split."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.v1.reader_journey import _serialize_result
from app.db.models import Chapter, Paragraph, ReaderJourneyRun, SceneReaderJourneyProfile
from app.model_gateway.gateway import ModelRequest
from app.model_gateway.registry import get_model_gateway
from app.services.chapter_analysis_smoke_fake_transport import (
    synthesize_chapter_smoke_fake_text,
)
from app.services.prompt_service import load_prompt
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    ensure_ai_model_revision_after_scenes_v1,
    split_scene_at_paragraph_v1,
)
from tests.test_chg041_scene_boundary_manual_review import (
    _attach_scene_analysis,
    _seed_chapter,
)


def _enable_fake(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL", "0")
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "success")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    monkeypatch.setenv("STORYLENS_REAL_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "STORYLENS_DATABASE_URL",
        "sqlite:///" + (tmp_path / "unused.db").as_posix(),
    )
    from app.core import config as config_mod
    from app.core.paths import apply_runtime_path_defaults

    config_mod.get_settings.cache_clear()
    apply_runtime_path_defaults()
    config_mod.get_settings.cache_clear()


def test_seed_fixture_stores_unicode_chinese(testing_session):
    book, chapter, paragraphs, _run, _scenes = _seed_chapter(testing_session)
    assert "???" not in book.title
    assert "场景" in book.title
    assert chapter.title == "第一章 夜雨初至"
    assert "???" not in chapter.title
    assert len(paragraphs) == 20
    for index, paragraph in enumerate(paragraphs, start=1):
        assert "???" not in paragraph.raw_text
        assert "???" not in paragraph.normalized_text
        assert f"第{index}段" in paragraph.raw_text
        assert "雨打青瓦" in paragraph.normalized_text


def test_prompt_loads_when_cwd_is_apps_api(monkeypatch, tmp_path):
    _enable_fake(monkeypatch, tmp_path)
    api_dir = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(api_dir)
    bundle = load_prompt("reader_journey_scene", "v2.0")
    assert "system" in bundle.system.lower() or len(bundle.system) > 20


def test_fake_emits_profiles_for_arbitrary_scene_ids(monkeypatch, tmp_path):
    _enable_fake(monkeypatch, tmp_path)
    prompt = {
        "profiles_target": [
            {
                "scene_id": 101,
                "scene_ordinal": 1,
                "paragraphs": [
                    {"id": "B0001-C0001-P0002", "text": "第二段正文"},
                ],
            },
            {
                "scene_id": 102,
                "scene_ordinal": 2,
                "paragraphs": [
                    {"id": "B0001-C0001-P0003", "text": "第三段正文"},
                ],
            },
            {
                "scene_id": 205,
                "scene_ordinal": 3,
                "paragraphs": [
                    {"id": "B0001-C0001-P0008", "text": "第八段正文"},
                ],
            },
            {
                "scene_id": 206,
                "scene_ordinal": 4,
                "paragraphs": [
                    {"id": "B0001-C0001-P0012", "text": "第十二段正文"},
                ],
            },
            {
                "scene_id": 207,
                "scene_ordinal": 5,
                "paragraphs": [
                    {"id": "B0001-C0001-P0018", "text": "第十八段正文"},
                ],
            },
        ]
    }
    request = ModelRequest(
        provider="aliyun_qwen_plus",
        model="qwen-plus",
        messages=[
            {
                "role": "user",
                "content": (
                    "reader_journey_scene contract_version 2.0 profiles\n"
                    + json.dumps(prompt, ensure_ascii=False)
                    + '\n"owned_scene_ids_json": "[101, 102, 205, 206, 207]"'
                ),
            }
        ],
        temperature=0,
        max_tokens=1000,
    )
    payload = json.loads(synthesize_chapter_smoke_fake_text(request))
    ids = [int(item["scene_id"]) for item in payload["profiles"]]
    assert ids == [101, 102, 205, 206, 207]
    for profile in payload["profiles"]:
        evidence = profile["evidence_paragraph_ids"]
        assert evidence
        assert all(pid.startswith("B0001-C0001-P") for pid in evidence)


def test_split_then_confirm_start_journey_succeeds_with_five_scenes(
    testing_session, monkeypatch, tmp_path
):
    _enable_fake(monkeypatch, tmp_path)
    _, chapter, paragraphs, run, scenes = _seed_chapter(testing_session)
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen-plus"
    run.cloud_consent = True
    testing_session.flush()
    _attach_scene_analysis(testing_session, run, scenes)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    # Split after paragraph 2 (inside first scene P0001-P0005) → 4 scenes become 5.
    split = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=paragraphs[1].id,
        expected_etag=draft.revision_etag,
        client_request_id="chg041-r7-split-p2",
    )
    testing_session.commit()
    assert len(split["scenes"]) == 5
    draft = testing_session.get(type(draft), draft.id)
    testing_session.refresh(draft)

    _revision, journey, _, err = asyncio.run(
        confirm_scene_revision_and_start_journey_v1(
            testing_session,
            draft.id,
            expected_etag=draft.revision_etag,
            start_journey=True,
            session_factory=None,
            gateway=None,
        )
    )
    assert err is None and journey is not None
    journey_id = int(journey.id)
    Session = sessionmaker(
        bind=testing_session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    asyncio.run(execute_reader_journey(Session, get_model_gateway(), journey_id))
    refreshed = testing_session.get(ReaderJourneyRun, journey_id)
    testing_session.refresh(refreshed)
    assert refreshed.status == "succeeded", (
        refreshed.root_error_code,
        refreshed.root_error_message,
    )
    included = json.loads(refreshed.included_scene_ids_json or "[]")
    assert len(included) == 5
    profiles = list(
        testing_session.scalars(
            select(SceneReaderJourneyProfile).where(
                SceneReaderJourneyProfile.reader_journey_run_id == journey_id
            )
        )
    )
    profile_scene_ids = sorted(int(p.scene_id) for p in profiles)
    assert profile_scene_ids == sorted(int(x) for x in included)
    assert refreshed.completed_scene_count == 5

    with Session() as session:
        first = _serialize_result(session, session.get(ReaderJourneyRun, journey_id))
    assert first.visualization is not None
    with Session() as session:
        second = _serialize_result(session, session.get(ReaderJourneyRun, journey_id))
    assert second.visualization == first.visualization

    # API text matches DB unicode.
    db_chapter = testing_session.get(Chapter, chapter.id)
    assert db_chapter.title == "第一章 夜雨初至"
    db_paragraphs = list(
        testing_session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    assert all("???" not in p.raw_text for p in db_paragraphs)
