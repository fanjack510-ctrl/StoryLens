"""CHG-041 Round 4: Smoke Fake journey fixture contract tests."""

from __future__ import annotations

import json
import os

import pytest

from app.model_gateway.base import ModelRequest
from app.services.chapter_analysis_smoke_fake_transport import (
    journey_smoke_fake_mode,
    synthesize_chapter_smoke_fake_text,
    validate_manual_gate_journey_fixture_v1,
)


def _batch_prompt(scenes: list[dict]) -> str:
    return (
        "读者阅读旅程 scene_profiles contract_version 2.0\n"
        + json.dumps(
            {
                "profiles_target": scenes,
                "owned_scene_ids_json": json.dumps([s["scene_id"] for s in scenes]),
            },
            ensure_ascii=False,
        )
    )


def _scenes_four() -> list[dict]:
    return [
        {
            "scene_id": 1,
            "scene_ordinal": 1,
            "paragraphs": [
                {"id": "B0001-C0001-P0001", "text": "s1a"},
                {"id": "B0001-C0001-P0005", "text": "s1b"},
            ],
        },
        {
            "scene_id": 2,
            "scene_ordinal": 2,
            "paragraphs": [
                {"id": "B0001-C0001-P0006", "text": "s2a"},
                {"id": "B0001-C0001-P0010", "text": "s2b"},
            ],
        },
        {
            "scene_id": 3,
            "scene_ordinal": 3,
            "paragraphs": [
                {"id": "B0001-C0001-P0011", "text": "s3a"},
                {"id": "B0001-C0001-P0015", "text": "s3b"},
            ],
        },
        {
            "scene_id": 4,
            "scene_ordinal": 4,
            "paragraphs": [
                {"id": "B0001-C0001-P0016", "text": "s4a"},
                {"id": "B0001-C0001-P0020", "text": "s4b"},
            ],
        },
    ]


@pytest.fixture(autouse=True)
def _enable_fake(monkeypatch):
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL", "0")
    monkeypatch.delenv("STORYLENS_JOURNEY_FAKE_MODE", raising=False)


def test_default_mode_is_success():
    assert journey_smoke_fake_mode() == "success"


def test_four_scene_evidence_in_range():
    prompt = _batch_prompt(_scenes_four())
    payload = json.loads(
        synthesize_chapter_smoke_fake_text(
            ModelRequest(messages=[{"role": "user", "content": prompt}], model="qwen-plus")
        )
    )
    profiles = payload["profiles"]
    assert [p["scene_id"] for p in profiles] == [1, 2, 3, 4]
    allowed = {
        1: {"B0001-C0001-P0001", "B0001-C0001-P0005"},
        2: {"B0001-C0001-P0006", "B0001-C0001-P0010"},
        3: {"B0001-C0001-P0011", "B0001-C0001-P0015"},
        4: {"B0001-C0001-P0016", "B0001-C0001-P0020"},
    }
    for profile in profiles:
        sid = profile["scene_id"]
        evidence = profile["evidence_paragraph_ids"]
        assert evidence
        assert set(evidence) <= allowed[sid]
        assert "B0001-C0001-P0001" not in evidence or sid == 1


def test_repair_returns_all_expected_ids():
    scenes = _scenes_four()[:2]
    prompt = _batch_prompt(scenes) + "\nstructural_repair expected scenes [1, 2]\nmissing scene_id 2"
    payload = json.loads(
        synthesize_chapter_smoke_fake_text(
            ModelRequest(messages=[{"role": "user", "content": prompt}], model="qwen-plus")
        )
    )
    assert [p["scene_id"] for p in payload["profiles"]] == [1, 2]


def test_repair_single_and_noncontiguous(monkeypatch):
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "success")
    prompt = (
        '读者阅读旅程 structural_repair expected scenes [3]\n'
        '{"scene_id": 3, "scene_ordinal": 3, "paragraphs": [{"id": "B0001-C0001-P0011", "text": "x"}]}'
    )
    payload = json.loads(
        synthesize_chapter_smoke_fake_text(
            ModelRequest(messages=[{"role": "user", "content": prompt}], model="qwen-plus")
        )
    )
    assert [p["scene_id"] for p in payload["profiles"]] == [3]

    prompt2 = (
        '读者阅读旅程 structural_repair expected scenes [7, 9]\n'
        '{"scene_id": 7, "scene_ordinal": 1, "paragraphs": [{"id": "B0001-C0001-P0001", "text": "a"}]}\n'
        '{"scene_id": 9, "scene_ordinal": 2, "paragraphs": [{"id": "B0001-C0001-P0008", "text": "b"}]}'
    )
    payload2 = json.loads(
        synthesize_chapter_smoke_fake_text(
            ModelRequest(messages=[{"role": "user", "content": prompt2}], model="qwen-plus")
        )
    )
    assert [p["scene_id"] for p in payload2["profiles"]] == [7, 9]


def test_repair_failure_mode_incomplete(monkeypatch):
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "repair_failure")
    prompt = _batch_prompt(_scenes_four()[:2]) + "\nstructural_repair expected scenes [1, 2]"
    payload = json.loads(
        synthesize_chapter_smoke_fake_text(
            ModelRequest(messages=[{"role": "user", "content": prompt}], model="qwen-plus")
        )
    )
    assert [p["scene_id"] for p in payload["profiles"]] == [1]


def test_manual_gate_self_check_pass(monkeypatch):
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "success")
    # Avoid packaged production rejection in CI by forcing enabled path via env only.
    result = validate_manual_gate_journey_fixture_v1()
    assert result["ok"] is True
    assert result["mode"] == "success"


def test_manual_gate_self_check_rejects_repair_failure(monkeypatch):
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "repair_failure")
    with pytest.raises(RuntimeError, match="MANUAL_GATE_FAKE_FIXTURE_INVALID"):
        validate_manual_gate_journey_fixture_v1()
