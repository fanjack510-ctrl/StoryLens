"""Path resolution for scene_evidence_validation.json (CHG-20260726-009)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.core import paths
from app.services import scene_evidence_validation as sev


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("STORYLENS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("STORYLENS_DATA_DIR", raising=False)
    paths.user_data_root.cache_clear()
    sev.clear_evidence_validation_config_cache()
    yield
    paths.user_data_root.cache_clear()
    sev.clear_evidence_validation_config_cache()


def test_production_localappdata_never_resolves_bare_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = tmp_path / "AppData" / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    # Keep resource_root on real repo so bundled config is found.
    paths.user_data_root.cache_clear()

    resolved = sev.resolve_evidence_validation_config_path()
    forbidden = (local / "config" / "scene_evidence_validation.json").resolve()
    storylens_cfg = (local / "StoryLens" / "config" / "scene_evidence_validation.json").resolve()
    assert resolved != forbidden
    assert "StoryLens" in str(resolved) or resolved.name == "scene_evidence_validation.json"
    assert resolved.is_file()
    # Prefer bundled when user override absent — must not invent LocalAppData\config.
    assert not str(resolved).replace("\\", "/").endswith("/Local/config/scene_evidence_validation.json")
    assert resolved != storylens_cfg or storylens_cfg.is_file()


def test_user_override_under_storylens_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = tmp_path / "AppData" / "Local"
    override_dir = local / "StoryLens" / "config"
    override_dir.mkdir(parents=True)
    override = override_dir / "scene_evidence_validation.json"
    bundled = paths.resource_root() / "config" / "scene_evidence_validation.json"
    override.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    paths.user_data_root.cache_clear()
    sev.clear_evidence_validation_config_cache()

    resolved = sev.resolve_evidence_validation_config_path()
    assert resolved == override.resolve()
    cfg = sev.load_evidence_validation_config()
    assert isinstance(cfg.get("field_classes"), dict)


def test_cwd_independent_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("STORYLENS_APP_ENV", raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    paths.user_data_root.cache_clear()
    sev.clear_evidence_validation_config_cache()

    expected = (paths.resource_root() / "config" / "scene_evidence_validation.json").resolve()
    results: list[Path] = []
    for cwd in (Path.cwd(), tmp_path, tmp_path / "nested"):
        cwd.mkdir(parents=True, exist_ok=True)
        prev = Path.cwd()
        try:
            os.chdir(cwd)
            sev.clear_evidence_validation_config_cache()
            results.append(sev.resolve_evidence_validation_config_path())
        finally:
            os.chdir(prev)
    assert all(item == expected for item in results)
    assert expected.is_file()


def test_loaded_config_matches_schema_keys() -> None:
    sev.clear_evidence_validation_config_cache()
    cfg = sev.load_evidence_validation_config()
    assert "field_classes" in cfg
    assert "local" in (cfg.get("field_classes") or {})


def test_list_analysis_runs_with_scene_validation_path(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GET /analysis-runs must survive production-like LOCALAPPDATA + scene serialize path."""
    import json

    from app.db.models import ModelInvocation
    from app.db.session import get_session_factory
    from app.main import app
    from tests.test_phase_1c_a10 import _seed_confirmed_run

    local = tmp_path / "AppData" / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    paths.user_data_root.cache_clear()
    sev.clear_evidence_validation_config_cache()

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=1
        )
        run.status = "failed"
        run.failed_stage = "scene_analysis"
        run.root_error_code = "SCENE_ANALYSIS_FAILED"
        scene = scenes[0]
        para = paragraphs[0]
        payload = {
            "scene_id": scene.scene_key,
            "entry_state": {
                "summary": "进入",
                "evidence_paragraph_ids": [para.id],
            },
            "goal": {"summary": "目标", "evidence_paragraph_ids": [para.id]},
            "obstacle": {"summary": "", "evidence_paragraph_ids": []},
            "key_actions": [
                {"summary": "行动", "evidence_paragraph_ids": [para.id]}
            ],
            "turning_point": {"summary": "", "evidence_paragraph_ids": []},
            "outcome": {"summary": "结果", "evidence_paragraph_ids": [para.id]},
            "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
            "function_tags": ["事件推进"],
            "confidence": 0.8,
        }
        inv = ModelInvocation(
            run_id=run.id,
            task_type="scene_analysis",
            provider_name="fake",
            model_name="fake",
            prompt_version="v3.2",
            schema_version="v1",
            attempt_no=1,
            invocation_kind="primary",
            request_hash="h" * 64,
            input_snapshot_json=json.dumps(
                {"content_hash": "x" * 64, "paragraph_ids": [para.id]},
                ensure_ascii=False,
            ),
            raw_response_text=json.dumps(payload, ensure_ascii=False),
            parsed_response_json=json.dumps(payload, ensure_ascii=False),
            status="failed",
            latency_ms=10,
            http_request_sent=True,
            http_status_code=200,
            error_code="SCENE_ANALYSIS_FAILED",
            error_message="synthetic",
            audit_type="provider_invocation",
        )
        session.add(inv)
        session.flush()
        run.failed_invocation_id = inv.id
        session.commit()

    # Ensure resolve would have used bare Local\config under the old bug.
    assert not (local / "config" / "scene_evidence_validation.json").exists()

    response = client.get("/api/v1/analysis-runs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert any(item.get("id") == run.id for item in body)
