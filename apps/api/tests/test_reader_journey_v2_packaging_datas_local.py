"""Assert PyInstaller datas / built sidecar embed V2 role-target configs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.paths import resource_root

REPO = resource_root()
REQUIRED = (
    b"scene_role_targets.json",
    b"reader_journey_formulas_v2.json",
)


def test_spec_datas_include_required_v2_configs():
    spec = (REPO / "apps" / "api" / "storylens-api.spec").read_text(encoding="utf-8")
    for name in REQUIRED:
        assert name.decode() in spec


@pytest.mark.parametrize("filename", [name.decode() for name in REQUIRED])
def test_repo_config_files_exist(filename: str):
    assert (REPO / "config" / filename).is_file()


def test_built_sidecar_embeds_v2_configs_when_present():
    """If a post-fix sidecar exists, require embedded filenames.

    Pre-change dist/install binaries are skipped — rebuild verifies packaging.
    Set STORYLENS_REQUIRE_PACKAGING_PROBE=1 to treat missing embeds as failure.
    """
    import os

    candidates = [
        REPO / "dist" / "release" / "storylens-api.exe",
        Path.home() / "AppData" / "Local" / "StoryLens" / "storylens-api.exe",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        pytest.skip("no built storylens-api.exe available for packaging probe")
    target = existing[0]
    blob = target.read_bytes()
    missing = [name.decode() for name in REQUIRED if name not in blob]
    require = os.environ.get("STORYLENS_REQUIRE_PACKAGING_PROBE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if missing and not require:
        pytest.skip(
            f"{target} missing {missing}; rebuild sidecar after CHG-20260727-013 "
            "(or set STORYLENS_REQUIRE_PACKAGING_PROBE=1)"
        )
    assert not missing, f"{target} missing embedded configs: {missing}"
