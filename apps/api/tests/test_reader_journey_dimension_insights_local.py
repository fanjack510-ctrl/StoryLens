"""Tests for Reader Journey dimension insights (CHG-20260729-001)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.reader_journey_v2 import DimensionInsightsV2, SceneReaderJourneyProfileItemV2
from app.services.chapter_analysis_smoke_fake_transport import synthesize_chapter_smoke_fake_text
from app.services.reader_journey_dimension_insights import (
    DIMENSION_KEYS,
    attach_dimension_insights_to_node,
    composite_role_fit_label,
    derive_legacy_dimension_insights,
    normalize_insight_text,
    resolve_scene_dimension_insights,
    validate_dimension_insights,
)
from app.services.reader_journey_v2_persist import build_v2_deterministic_statistics
from app.services.reader_journey_visualization import _apply_v2_presentation_overrides
from app.model_gateway.base import ModelRequest
from tests.fixtures.reader_journey_dimension_insights_fixture import (
    DETERMINISTIC_STATS_FIXTURE,
    DIMENSION_INSIGHTS_FIXTURE_SCENES,
)


def test_dimension_insights_v2_schema_optional_and_forbid_extra():
    item = DimensionInsightsV2(
        overall_reading="综合阅读洞察示例。",
        plot_progression="剧情推进洞察示例。",
    )
    assert item.overall_reading.startswith("综合阅读")
    with pytest.raises(ValidationError):
        DimensionInsightsV2(overall_reading="ok", unknown="x")  # type: ignore[call-arg]


def test_validate_dimension_insights_rejects_exact_duplicate():
    with pytest.raises(ValueError, match="exact duplicate"):
        validate_dimension_insights(
            {
                "overall_reading": "同一段洞察文本。",
                "plot_progression": "同一段洞察文本。",
            }
        )


def test_validate_dimension_insights_warns_high_overlap():
    warnings = validate_dimension_insights(
        {
            "overall_reading": "综合阅读贡献偏强，读者继续阅读动力明显。",
            "plot_progression": "综合阅读贡献偏强，读者继续阅读动力明显啊",
        }
    )
    assert any("high overlap" in item for item in warnings)


def test_derive_legacy_dimension_insights_distinct_per_dimension():
    legacy_node = {
        "scene_ordinal": 1,
        "scene_role": "setup",
        "scene_value_summary": "人物进入新环境，建立初始疑问。",
        "scores": {
            "reading_momentum": 55,
            "plot_progress": 48,
            "reading_tension": 40,
            "pacing_speed": 50,
            "hook": 60,
            "payoff": 30,
            "emotional_investment": 45,
        },
    }
    result = derive_legacy_dimension_insights(legacy_node)
    texts = [result["insights"][key] for key in DIMENSION_KEYS if result["insights"][key]]
    assert len(texts) >= 4
    assert len(set(texts)) == len(texts)
    assert result["insight_source"] == "derived_legacy"


def test_composite_momentum_differs_from_tension_in_fixture():
    for scene in DIMENSION_INSIGHTS_FIXTURE_SCENES:
        momentum = scene["scores"]["reading_momentum"]
        tension = scene["scores"]["reading_tension"]
        if scene["scene_ordinal"] in {3, 5}:
            assert momentum != tension


def test_composite_role_fit_label_bands():
    assert composite_role_fit_label(50, "setup") == "合适"
    assert composite_role_fit_label(30, "setup") == "偏弱"
    assert composite_role_fit_label(90, "climax") == "合适"
    assert composite_role_fit_label(55, "climax") == "偏弱"
    assert composite_role_fit_label(None, "climax") == "无法判断"


def test_visualization_attaches_dimension_insights():
    scene_nodes = [
        {
            "scene_ordinal": scene["scene_ordinal"],
            "scene_id": scene["scene_id"],
            "scene_role": scene["scene_role"],
            "role": "core",
            "scores": dict(scene["scores"]),
            "engagement": {"engagement_score": int(scene["scores"]["reading_momentum"])},
        }
        for scene in DIMENSION_INSIGHTS_FIXTURE_SCENES
    ]
    summary = type(
        "Summary",
        (),
        {"deterministic_statistics_json": json.dumps(DETERMINISTIC_STATS_FIXTURE, ensure_ascii=False)},
    )()
    _apply_v2_presentation_overrides(scene_nodes, summary)
    node = scene_nodes[0]
    assert node["dimension_insights"]["overall_reading"]
    assert node["insight_source"] == "generated"
    assert node["overall_reading_score"] == 42
    assert node["composite_role_fit"] in {"合适", "偏弱", "偏强", "无法判断"}


def test_fake_transport_emits_six_distinct_dimension_insights():
    prompt = (
        "读者阅读旅程 scene_profiles contract_version 2.0\n"
        '{"profiles_target":[{"scene_id":1,"scene_ordinal":1,"paragraphs":[{"id":"B0001-C0001-P0001","text":"test"}]}],'
        '"owned_scene_ids_json":"[1]"}'
    )
    payload = json.loads(
        synthesize_chapter_smoke_fake_text(ModelRequest(messages=[{"role": "user", "content": prompt}]))
    )
    profile = payload["profiles"][0]
    assert "Scene1推进" not in profile["scene_value_summary"]
    insights = profile["dimension_insights"]
    texts = list(insights.values())
    assert len(texts) == 6
    assert len(set(texts)) == 6


def test_persist_v2_dimension_insights_without_migration():
    from app.schemas.reader_journey_v2 import ScoredLevelField

    def _level(n: int) -> ScoredLevelField:
        return ScoredLevelField(level=n, rationale="t", confidence=0.8)

    profile = SceneReaderJourneyProfileItemV2(
        scene_id=1,
        scene_ordinal=1,
        scene_role="setup",
        scene_value_summary="测试场景",
        goal_progress=_level(2),
        conflict_change=_level(2),
        state_change=_level(2),
        information_gain=_level(2),
        character_agency=_level(2),
        causal_coherence=_level(2),
        curiosity=_level(2),
        tension=_level(2),
        emotional_investment=_level(2),
        pacing_speed=_level(2),
        hook=_level(2),
        payoff=_level(2),
        setup_consistency=_level(2),
        question_lifecycle=_level(2),
        emotional_valence_start=_level(2),
        emotional_valence_end=_level(2),
        arousal_start=_level(2),
        arousal_end=_level(2),
        clarity=_level(3),
        cognitive_load=_level(2),
        redundancy=_level(1),
        confidence=0.8,
        dimension_insights=DimensionInsightsV2(
            overall_reading="综合阅读测试洞察。",
            plot_progression="剧情推进测试洞察。",
            reading_tension="阅读张力测试洞察。",
            emotional_intensity="情绪强度测试洞察。",
            hook_payoff="钩子回收测试洞察。",
            pacing_speed="节奏速度测试洞察。",
        ),
    )
    stats = build_v2_deterministic_statistics(derived=[profile], finalize_stats={})
    assert "v2_dimension_insights" in stats
    assert stats["v2_dimension_insights"]["1"]["overall_reading"].startswith("综合阅读")


def test_resolve_prefers_generated_over_legacy():
    node = {
        "scene_ordinal": 2,
        "scene_role": "transition",
        "dimension_insights": {
            "overall_reading": "生成的综合阅读洞察。",
            "plot_progression": "生成的剧情推进洞察。",
            "reading_tension": "生成的阅读张力洞察。",
            "emotional_intensity": "生成的情绪强度洞察。",
            "hook_payoff": "生成的钩子回收洞察。",
            "pacing_speed": "生成的节奏速度洞察。",
        },
        "scores": {"reading_momentum": 50},
    }
    resolved = resolve_scene_dimension_insights(node)
    assert resolved["insight_source"] == "generated"
    assert resolved["insights"]["overall_reading"].startswith("生成的")


def test_normalize_insight_text_strips_and_caps():
    assert normalize_insight_text("  测试  洞察  ") == "测试 洞察"
    long_text = "测" * 200
    assert len(normalize_insight_text(long_text) or "") <= 160
