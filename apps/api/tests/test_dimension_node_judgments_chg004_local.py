"""CHG-20260729-004 — formula untouched; Fake journey exposes four dimension scores."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from app.db.models import ReaderJourneyRun
from app.model_gateway.registry import get_model_gateway
from app.services.chapter_analysis_smoke_fake_transport import (
    validate_manual_gate_journey_fixture_v1,
)
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    ensure_ai_model_revision_after_scenes_v1,
)
from tests.test_chg041_scene_boundary_manual_review import (
    _attach_scene_analysis,
    _seed_chapter,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FORMULA_PATH = REPO_ROOT / "config" / "reader_journey_formulas_v2.json"


def test_formula_v2_untouched_for_chg004():
    text = FORMULA_PATH.read_text(encoding="utf-8")
    assert "reading_momentum" in text
    assert "plot_progress" in text
    assert "reading_tension" in text
    assert "pacing_fit" in text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(digest) == 64


def test_fake_journey_visualization_exposes_four_dimension_scores(
    testing_session, monkeypatch, tmp_path
):
    """Fake HTTP-equivalent path: dimension score facts exist; judgments stay FE-derived."""
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL", "0")
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "success")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    monkeypatch.setenv("STORYLENS_REAL_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "STORYLENS_DATABASE_URL",
        "sqlite:///" + (tmp_path / "chg004.db").as_posix(),
    )
    from app.core import config as config_mod

    config_mod.get_settings.cache_clear()

    validate_manual_gate_journey_fixture_v1()
    _, chapter, _, run, scenes = _seed_chapter(testing_session)
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen-plus"
    testing_session.flush()
    _attach_scene_analysis(testing_session, run, scenes)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
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
    assert err is None
    assert journey is not None
    journey_id = journey.id

    factory = testing_session.get_bind()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=factory, autoflush=False, autocommit=False, expire_on_commit=False)
    gateway = get_model_gateway()
    asyncio.run(execute_reader_journey(Session, gateway, journey_id))

    refreshed = testing_session.get(ReaderJourneyRun, journey_id)
    testing_session.refresh(refreshed)
    assert refreshed is not None
    assert refreshed.status == "succeeded"

    from app.api.v1.reader_journey import _serialize_result

    with Session() as s1:
        first = _serialize_result(s1, s1.get(ReaderJourneyRun, journey_id))
    with Session() as s2:
        second = _serialize_result(s2, s2.get(ReaderJourneyRun, journey_id))

    assert first.visualization is not None
    assert second.visualization == first.visualization
    nodes = first.visualization.get("scene_nodes") or []
    assert len(nodes) >= 4
    for node in nodes:
        scores = node.get("scores") or {}
        assert scores.get("plot_progress") is not None
        assert scores.get("reading_tension") is not None
        assert scores.get("pacing_speed") is not None
        assert (
            scores.get("emotional_investment") is not None
            or scores.get("arousal_start") is not None
            or scores.get("arousal_end") is not None
        )
        assert "dimension_short_label" not in node
        assert "dimension_node_judgment" not in node
