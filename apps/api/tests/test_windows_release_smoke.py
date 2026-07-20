import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TAURI_CONF = REPO / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
BUILD_SCRIPT = REPO / "scripts" / "build_windows_release.ps1"


def test_updater_config_loadable():
    raw = TAURI_CONF.read_text(encoding="utf-8")
    conf = json.loads(raw)
    updater = conf.get("plugins", {}).get("updater", {})
    assert updater.get("pubkey"), "updater pubkey must be configured"
    endpoints = updater.get("endpoints") or []
    assert endpoints, "updater endpoints required"
    assert all(str(url).startswith("https://") for url in endpoints)


def test_release_build_skips_signing_without_secret():
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "createUpdaterArtifacts" in text
    assert "skipped_no_secret" in text
    assert "No updater signing key" in text
    assert "TAURI_SIGNING_PRIVATE_KEY" in text


def test_set_version_script_exists():
    script = REPO / "scripts" / "set_version.ps1"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    assert "tauri.conf.json" in body
    assert "apps/api/app/main.py" in body or "apps\\api\\app\\main.py" in body


def test_no_private_key_patterns_in_tauri_conf():
    raw = TAURI_CONF.read_text(encoding="utf-8")
    assert "BEGIN PRIVATE KEY" not in raw
    assert "BEGIN RSA PRIVATE KEY" not in raw


def test_build_summary_schema_when_present():
    summary_path = REPO / "dist" / "release" / "build-summary.json"
    if not summary_path.is_file():
        return
    data = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    assert data.get("version")
    assert data.get("sidecar") == "ok"
    assert data.get("tauri") == "ok"
    updater = data.get("updater_artifacts")
    assert updater in {"enabled", "skipped", "skipped_no_secret"}
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        assert updater != "enabled", "local build must not claim signed updater without secret"
