"""License public-key trust isolation (CHG-20260722-001 follow-up)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.services import entitlement
from app.services.license_crypto import (
    LicenseError,
    build_unsigned_payload,
    encode_license,
    public_key_b64url,
)

ROOT = Path(__file__).resolve().parents[3]
TEST_FIXTURE = ROOT / "tests" / "fixtures" / "license_public_keys.test.json"
PROD_CONFIG = ROOT / "config" / "license_public_keys.production.json"


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _write_config(path: Path, *, key_id: str, env: str, pub: str, status: str = "active") -> None:
    path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "key_id": key_id,
                        "signature_version": 1,
                        "algorithm": "ed25519",
                        "environment": env,
                        "public_key_b64url": pub,
                        "status": status,
                    }
                ],
                "commerce": {
                    "afdian_product_url": "https://afdian.com/item/x",
                    "product_code": "storylens_pro",
                },
            }
        ),
        encoding="utf-8",
    )


def test_dev_mode_accepts_test_dev_fixture(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: False)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: TEST_FIXTURE)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    assert entitlement.license_trust_mode() == "development"
    keys = entitlement.public_keys_by_id()
    assert "test-dev-001" in keys


def test_pytest_injected_fixture_accepts_test_code(
    monkeypatch: pytest.MonkeyPatch, session: Session, tmp_path: Path
) -> None:
    priv = Ed25519PrivateKey.generate()
    pub = public_key_b64url(priv.public_key())
    path = tmp_path / "inj.json"
    _write_config(path, key_id="test-unit-inj", env="test", pub=pub)
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: False)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    code = encode_license(build_unsigned_payload(major_version=1, key_id="test-unit-inj"), priv)
    result = entitlement.activate_license_code(session, code)
    assert result["ok"] is True


def test_browser_local_production_rejects_test_code(
    monkeypatch: pytest.MonkeyPatch, session: Session, tmp_path: Path
) -> None:
    priv = Ed25519PrivateKey.generate()
    pub = public_key_b64url(priv.public_key())
    # Production config without the test key — but code is signed as test-dev-001 style.
    prod_path = tmp_path / "prod.json"
    _write_config(prod_path, key_id="storylens-pro-1-prod-001", env="production", pub=pub)
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: True)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: prod_path)
    monkeypatch.setattr(entitlement, "production_config_path", lambda: prod_path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    test_priv = Ed25519PrivateKey.generate()
    code = encode_license(
        build_unsigned_payload(major_version=1, key_id="test-dev-001"), test_priv
    )
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, code)
    assert exc.value.code == "LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME"
    assert "此授权码不能用于当前版本" in exc.value.message
    assert "test-dev" not in exc.value.message


def test_tauri_desktop_rejects_test_code(
    monkeypatch: pytest.MonkeyPatch, session: Session, tmp_path: Path
) -> None:
    # Same gate as production runtime (Tauri sidecar sets production env).
    priv = Ed25519PrivateKey.generate()
    pub = public_key_b64url(priv.public_key())
    prod_path = tmp_path / "prod.json"
    _write_config(prod_path, key_id="storylens-pro-1-prod-001", env="production", pub=pub)
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: True)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: prod_path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    code = encode_license(build_unsigned_payload(major_version=1, key_id="fixture-temp-1"), priv)
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, code)
    assert exc.value.code == "LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME"


def test_production_accepts_valid_production_fixture(
    monkeypatch: pytest.MonkeyPatch, session: Session, tmp_path: Path
) -> None:
    priv = Ed25519PrivateKey.generate()
    pub = public_key_b64url(priv.public_key())
    prod_path = tmp_path / "prod.json"
    _write_config(prod_path, key_id="storylens-pro-1-prod-001", env="production", pub=pub)
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: True)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: prod_path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    code = encode_license(
        build_unsigned_payload(major_version=1, key_id="storylens-pro-1-prod-001"), priv
    )
    result = entitlement.activate_license_code(session, code)
    assert result["ok"] is True
    assert result["entitlement"]["pro_active"] is True


def test_unknown_key_id_rejected(monkeypatch: pytest.MonkeyPatch, session: Session, tmp_path: Path) -> None:
    priv = Ed25519PrivateKey.generate()
    pub = public_key_b64url(priv.public_key())
    path = tmp_path / "prod.json"
    _write_config(path, key_id="storylens-pro-1-prod-001", env="production", pub=pub)
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: True)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    code = encode_license(build_unsigned_payload(major_version=1, key_id="unknown-prod-key"), priv)
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, code)
    assert exc.value.code == "LICENSE_KEY_UNSUPPORTED"


def test_missing_production_config_does_not_fallback_to_test(
    monkeypatch: pytest.MonkeyPatch, session: Session, tmp_path: Path
) -> None:
    empty = tmp_path / "empty-prod.json"
    empty.write_text(json.dumps({"keys": [], "commerce": {}}), encoding="utf-8")
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: True)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: empty)
    monkeypatch.setattr(entitlement, "production_config_path", lambda: empty)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    # Even if test fixture exists on disk, production must not use it.
    assert TEST_FIXTURE.is_file()
    keys = entitlement.public_keys_by_id()
    assert "test-dev-001" not in keys
    snap = entitlement.entitlement_snapshot(session)
    assert snap["license_issuance_ready"] is False
    assert snap["license_issuance_message"] == "专业版授权功能尚未配置。"
    code = encode_license(build_unsigned_payload(major_version=1, key_id="test-dev-001"), Ed25519PrivateKey.generate())
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, code)
    assert exc.value.code == "LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME"


def test_test_fixture_not_loaded_in_production_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: True)
    monkeypatch.setattr(entitlement, "license_config_path", entitlement.production_config_path)
    path = entitlement.license_config_path()
    assert path == PROD_CONFIG.resolve() or path.name == "license_public_keys.production.json"
    cfg = entitlement.load_license_config()
    for item in cfg.get("keys") or []:
        assert str(item.get("key_id")) != "test-dev-001"
        assert str(item.get("environment") or "").lower() != "test"


def test_repo_has_no_private_keys_or_real_code_files() -> None:
    assert not (ROOT / "config" / "license_public_keys.json").exists()
    prod = PROD_CONFIG.read_text(encoding="utf-8")
    assert "ed25519.priv" not in prod
    assert "test-dev-001" not in prod
    assert "BEGIN PRIVATE KEY" not in prod
    for path in ROOT.rglob("*.ed25519.priv.b64"):
        # gitignored private_release is ok on disk but must not be under config/
        assert "config" not in path.parts
    # Tracked production config must not embed SLP1 codes.
    assert "SLP1-" not in prod


def test_production_commerce_url_is_https_afdian() -> None:
    data = json.loads(PROD_CONFIG.read_text(encoding="utf-8"))
    url = str((data.get("commerce") or {}).get("afdian_product_url") or "")
    assert url.startswith("https://")
    assert "afdian.com" in url
    assert entitlement.is_safe_https_commerce_url(url) is True
    assert entitlement.is_safe_https_commerce_url("javascript:alert(1)") is False
    assert entitlement.is_safe_https_commerce_url("https://localhost/x") is False
    assert entitlement.is_safe_https_commerce_url("") is False
    monkey_cfg = {"commerce": {"afdian_product_url": "javascript:alert(1)"}}
    assert entitlement.commerce_config(monkey_cfg)["afdian_product_url"] == ""
