from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_macos_uses_onedir_without_changing_windows_onefile() -> None:
    spec = (REPO / "apps/api/storylens-api.spec").read_text(encoding="utf-8")
    assert 'if sys.platform == "darwin":' in spec
    assert "exclude_binaries=True" in spec
    assert "coll = COLLECT(" in spec
    assert "# Preserve the established Windows onefile package." in spec


def test_macos_bundle_contains_complete_sidecar_runtime() -> None:
    config = json.loads(
        (REPO / "apps/desktop/src-tauri/tauri.macos.conf.json").read_text(encoding="utf-8")
    )
    bundle = config["bundle"]
    assert bundle["externalBin"] == []
    assert bundle["macOS"]["hardenedRuntime"] is False
    assert bundle["macOS"]["files"] == {
        "Resources/storylens-api-runtime": "../../api/dist-sidecar/storylens-api"
    }
    backend = (REPO / "apps/desktop/src-tauri/src/backend.rs").read_text(encoding="utf-8")
    assert '.join("Resources")' in backend
    assert '.join("storylens-api-runtime")' in backend


def test_release_checks_packaged_onedir_instead_of_onefile_archive() -> None:
    build = (REPO / "scripts/build_macos_release.sh").read_text(encoding="utf-8")
    smoke = (REPO / "scripts/smoke_macos_release.sh").read_text(encoding="utf-8")
    checker = (REPO / "scripts/check_macos_sidecar_signature.py").read_text(encoding="utf-8")
    assert 'BUILT_SIDECAR_DIR="$ROOT/apps/api/dist-sidecar/storylens-api"' in build
    assert 'find "$BUILT_SIDECAR_DIR" -type f -print0' in build
    assert 'codesign --force --sign - "$MACHO_PATH"' in build
    assert "codesign --force --options runtime --timestamp" in build
    assert '"$PACKAGED_APP/Contents/Resources/storylens-api-runtime"' in build
    assert '"sidecar_layout": "onedir"' in build
    assert '"hardened_runtime": os.environ["HARDENED_RUNTIME"] == "true"' in build
    assert '"hardenedRuntime":true' in build
    assert 'ARTIFACT_SUFFIX="${STORYLENS_MACOS_ARTIFACT_SUFFIX:-}"' in build
    assert "onedir-candidate" in (REPO / ".github/workflows/macos-release.yml").read_text(
        encoding="utf-8"
    )
    assert '"$APP/Contents/Resources/storylens-api-runtime"' in smoke
    assert 'find "$APP_HOME/Library/Application Support"' in smoke
    assert 'find "$APP_DATA/runtime"' not in smoke
    assert "CArchiveReader" not in checker
    assert "_runtime_macho_paths" in checker
    assert "for signature in signatures.values()" in checker
