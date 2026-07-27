"""CHG-20260727-013: V2 role-target / formulas config loading reliability."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.paths import resource_root
from app.schemas.reader_journey_v2 import ScoredLevelField, SceneReaderJourneyProfileItemV2
from app.services import reader_journey_v2_config as v2cfg
from app.services.reader_journey_v2_config import (
    load_formula_v2_bundle,
    load_scene_role_targets_bundle,
    resolve_reader_journey_v2_config_path,
    validate_scene_role_targets,
)
from app.services.reader_journey_v2_derivation import (
    compute_pacing_fit_result,
    derive_scene_metrics,
    fit_to_band,
    load_scene_role_targets,
)
from app.services.reader_journey_v2_mapping import load_formula_v2_config, level_to_mapped_score

REPO_ROOT = resource_root()


def _level(level: int, evidence: list[str] | None = None) -> ScoredLevelField:
    return ScoredLevelField(
        level=level,
        mapped_score=None,
        evidence_paragraph_ids=evidence or ["P1"],
        rationale="t",
        confidence=0.9,
    )


def _profile(
    ordinal: int = 1,
    *,
    scene_role: str = "reveal",
    pacing_level: int = 2,
) -> SceneReaderJourneyProfileItemV2:
    levels = {
        key: _level(2)
        for key in (
            "goal_progress",
            "conflict_change",
            "state_change",
            "information_gain",
            "character_agency",
            "causal_coherence",
            "curiosity",
            "tension",
            "emotional_investment",
            "hook",
            "payoff",
            "setup_consistency",
            "question_lifecycle",
            "emotional_valence_start",
            "emotional_valence_end",
            "arousal_start",
            "arousal_end",
            "clarity",
            "cognitive_load",
            "redundancy",
        )
    }
    levels["pacing_speed"] = _level(pacing_level)
    return SceneReaderJourneyProfileItemV2(
        scene_id=ordinal,
        scene_ordinal=ordinal,
        node_type="scene",
        scene_role=scene_role,  # type: ignore[arg-type]
        scene_value_summary="test summary",
        confidence=0.9,
        evidence_paragraph_ids=["P1"],
        **levels,
    )


def test_resolve_config_independent_of_cwd(tmp_path, monkeypatch):
    repo_config = REPO_ROOT / "config" / "scene_role_targets.json"
    assert repo_config.is_file()
    foreign = tmp_path / "elsewhere"
    foreign.mkdir()
    monkeypatch.chdir(foreign)
    monkeypatch.delenv("STORYLENS_CONFIG_DIR", raising=False)
    path, source, err = resolve_reader_journey_v2_config_path("scene_role_targets.json")
    assert err is None
    assert path is not None
    assert path.is_file()
    assert path.name == "scene_role_targets.json"
    assert source in {"bundled", "user", "env"}
    bundle = load_scene_role_targets_bundle()
    assert bundle.ok
    assert "setup" in bundle.roles


def test_resolve_from_apps_api_cwd(monkeypatch):
    monkeypatch.chdir(REPO_ROOT / "apps" / "api")
    monkeypatch.delenv("STORYLENS_CONFIG_DIR", raising=False)
    path, _source, err = resolve_reader_journey_v2_config_path("scene_role_targets.json")
    assert err is None
    assert path is not None and path.is_file()
    formulas, _fs, ferr = resolve_reader_journey_v2_config_path("reader_journey_formulas_v2.json")
    assert ferr is None
    assert formulas is not None and formulas.is_file()


def test_missing_role_targets_via_resolver(monkeypatch):
    monkeypatch.setattr(
        v2cfg,
        "resolve_reader_journey_v2_config_path",
        lambda filename, explicit=None: (None, "unknown", "missing"),
    )
    bundle = load_scene_role_targets_bundle()
    assert not bundle.ok
    assert bundle.config is None
    assert "scene_role_targets_missing" in bundle.provenance.quality_flags
    with pytest.raises((FileNotFoundError, ValueError)):
        load_scene_role_targets()


def test_invalid_role_targets_json(tmp_path):
    bad = tmp_path / "scene_role_targets.json"
    bad.write_text("{not-json", encoding="utf-8")
    bundle = load_scene_role_targets_bundle(explicit=bad)
    assert not bundle.ok
    assert bundle.provenance.status == "invalid"
    assert "scene_role_targets_invalid" in bundle.provenance.quality_flags


def test_validate_scene_role_targets_rejects_empty():
    with pytest.raises(ValueError, match="roles"):
        validate_scene_role_targets({})
    with pytest.raises(ValueError, match="non-empty"):
        validate_scene_role_targets({"roles": {}})


def test_validate_scene_role_targets_rejects_bad_band():
    roles = {
        role: {
            "pacing_speed": [10, 20],
            "hook": [10, 20],
            "payoff": [10, 20],
        }
        for role in sorted(v2cfg.REQUIRED_SCENE_ROLES)
    }
    roles["setup"] = {
        "pacing_speed": [80, 20],
        "hook": [10, 20],
        "payoff": [10, 20],
    }
    with pytest.raises(ValueError, match="min must be <= max"):
        validate_scene_role_targets({"roles": roles})


def test_pacing_fit_unavailable_when_targets_missing():
    profile = _profile(pacing_level=5, scene_role="open_end")
    cfg = load_formula_v2_config()
    result = compute_pacing_fit_result(
        profile,
        role_targets=None,
        formula_config=cfg,
        targets_load_status="missing",
    )
    assert result.status == "unavailable"
    assert result.value is None
    assert result.reason_code == "scene_role_targets_unavailable"
    updated, derived = derive_scene_metrics(
        profile,
        formula_config=cfg,
        role_targets=v2cfg.RoleTargetsBundle(
            provenance=v2cfg.ConfigProvenance(
                config_name="scene_role_targets.json",
                status="missing",
                source="unknown",
                version=None,
                content_hash=None,
                resolved_path=None,
                error="missing",
                quality_flags=("scene_role_targets_missing", "pacing_fit_unavailable"),
            ),
            config=None,
        ),
    )
    assert derived.pacing_fit is None
    assert updated.pacing_fit is None
    assert updated.pacing_fit_status == "unavailable"
    assert updated.pacing_speed.mapped_score == 95
    assert derived.reading_momentum is not None


def test_pacing_fit_formula_in_out_of_band():
    roles = load_scene_role_targets()
    cfg = load_formula_v2_config()
    in_band = _profile(scene_role="aftermath", pacing_level=2)
    high = _profile(scene_role="aftermath", pacing_level=5)
    low = _profile(scene_role="climax", pacing_level=1)
    _, d_in = derive_scene_metrics(in_band, formula_config=cfg, role_targets=roles)
    _, d_high = derive_scene_metrics(high, formula_config=cfg, role_targets=roles)
    _, d_low = derive_scene_metrics(low, formula_config=cfg, role_targets=roles)
    assert d_in.pacing_fit == 90
    assert d_high.pacing_fit is not None and d_high.pacing_fit < 90
    assert d_low.pacing_fit is not None and d_low.pacing_fit < 90
    assert fit_to_band(50, [40, 60], config=cfg) == 90


def test_level_mapping_unchanged():
    assert level_to_mapped_score(5, has_evidence=True) == 95
    assert level_to_mapped_score(4, has_evidence=True) == 80
    assert level_to_mapped_score(1, has_evidence=True) == 30


def test_pyinstaller_spec_lists_v2_configs():
    spec = (REPO_ROOT / "apps" / "api" / "storylens-api.spec").read_text(encoding="utf-8")
    assert "scene_role_targets.json" in spec
    assert "reader_journey_formulas_v2.json" in spec


def test_packaged_config_files_present_in_repo_config():
    assert (REPO_ROOT / "config" / "scene_role_targets.json").is_file()
    assert (REPO_ROOT / "config" / "reader_journey_formulas_v2.json").is_file()


def test_formulas_bundle_loads_from_resource_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    bundle = load_formula_v2_bundle()
    assert bundle.config.get("version") == "2.0"
    assert "level_to_mapped_score" in bundle.config


def test_simulate_install_layout_datas(tmp_path, monkeypatch):
    """Simulate PyInstaller extracted layout: resource_root/config/*.json."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    for name in ("scene_role_targets.json", "reader_journey_formulas_v2.json"):
        src = REPO_ROOT / "config" / name
        (cfg_dir / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr("app.core.paths.resource_root", lambda: tmp_path)
    # Isolate from developer AppData / prior install configs.
    empty_user = tmp_path / "user_data"
    empty_user.mkdir()
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(empty_user))
    foreign = tmp_path / "cwd_elsewhere"
    foreign.mkdir()
    monkeypatch.chdir(foreign)
    monkeypatch.delenv("STORYLENS_CONFIG_DIR", raising=False)
    path, source, err = resolve_reader_journey_v2_config_path("scene_role_targets.json")
    assert err is None
    assert path is not None
    assert path == (tmp_path / "config" / "scene_role_targets.json").resolve()
    assert source == "bundled"
    bundle = load_scene_role_targets_bundle()
    assert bundle.ok
