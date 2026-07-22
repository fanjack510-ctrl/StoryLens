"""Local pytest for StoryLens Pro offline license activation (CHG-20260722-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, LocalLicense
from app.services import entitlement
from app.services.license_crypto import (
    LicenseError,
    build_unsigned_payload,
    encode_license,
    private_key_b64url,
    public_key_b64url,
)


@pytest.fixture()
def keypair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    priv = Ed25519PrivateKey.generate()
    key_id = "test-unit-001"
    pub = public_key_b64url(priv.public_key())
    config = {
        "keys": [
            {
                "key_id": key_id,
                "signature_version": 1,
                "algorithm": "ed25519",
                "environment": "test",
                "public_key_b64url": pub,
                "status": "active",
            }
        ],
        "commerce": {"afdian_product_url": "https://afdian.com/item/test", "product_code": "storylens_pro"},
    }
    path = tmp_path / "license_public_keys.test.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: False)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    return priv, key_id, private_key_b64url(priv)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _code(priv, key_id: str, *, major: int = 1, product: str | None = None) -> str:
    payload = build_unsigned_payload(major_version=major, key_id=key_id)
    if product:
        payload["product_code"] = product
    return encode_license(payload, priv)


def test_valid_license_activates(session: Session, keypair) -> None:
    priv, key_id, _ = keypair
    result = entitlement.activate_license_code(session, _code(priv, key_id))
    assert result["ok"] is True
    assert result["entitlement"]["pro_active"] is True
    assert result["entitlement"]["edition"] == "pro"
    assert session.scalar(select(LocalLicense)) is not None


def test_tampered_license_fails(session: Session, keypair) -> None:
    priv, key_id, _ = keypair
    code = _code(priv, key_id)
    bad = code[:-2] + ("A" if code[-2] != "A" else "B") + code[-1]
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, bad)
    assert exc.value.code == "LICENSE_SIGNATURE_INVALID"


def test_wrong_product_fails(session: Session, keypair) -> None:
    priv, key_id, _ = keypair
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, _code(priv, key_id, product="other_product"))
    assert exc.value.code == "LICENSE_PRODUCT_MISMATCH"


def test_wrong_major_fails(session: Session, keypair) -> None:
    priv, key_id, _ = keypair
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, _code(priv, key_id, major=9))
    assert exc.value.code == "LICENSE_MAJOR_VERSION_MISMATCH"


def test_unknown_key_id_fails(session: Session, keypair) -> None:
    priv, _, _ = keypair
    with pytest.raises(LicenseError) as exc:
        entitlement.activate_license_code(session, _code(priv, "unknown-key"))
    assert exc.value.code == "LICENSE_KEY_UNSUPPORTED"


def test_repeat_activation_idempotent(session: Session, keypair) -> None:
    priv, key_id, _ = keypair
    code = _code(priv, key_id)
    first = entitlement.activate_license_code(session, code)
    second = entitlement.activate_license_code(session, code)
    assert first["ok"] and second["ok"]
    assert second["already_active"] is True
    rows = list(session.scalars(select(LocalLicense)))
    assert len(rows) == 1


def test_sqlite_persistence_and_feature_gate(session: Session, keypair) -> None:
    priv, key_id, _ = keypair
    entitlement.activate_license_code(session, _code(priv, key_id))
    gate = entitlement.can_use_feature(session, "whole_book_analysis")
    assert gate["enabled"] is True
    assert gate["source"] == "signed_local_license"
    free = entitlement.can_use_feature(session, "whole_book_analysis")
    # still enabled after re-read
    assert free["enabled"] is True
    # no email/body fields in row
    row = session.scalar(select(LocalLicense))
    blob = json.dumps({c.name: getattr(row, c.name) for c in row.__table__.columns}, default=str)
    assert "email" not in blob.lower()
    assert "正文" not in blob


def test_free_edition_requires_pro(session: Session) -> None:
    gate = entitlement.can_use_feature(session, "story_lab")
    assert gate["enabled"] is False
    assert gate["reason"] == "PRO_LICENSE_REQUIRED"


def test_private_key_not_in_repo_config() -> None:
    prod = Path("config/license_public_keys.production.json").read_text(encoding="utf-8")
    assert "ed25519.priv" not in prod
    assert "test-dev-001" not in prod
    assert "BEGIN PRIVATE KEY" not in prod
    fixture = Path("tests/fixtures/license_public_keys.test.json").read_text(encoding="utf-8")
    assert "ed25519.priv" not in fixture
    data = json.loads(fixture)
    assert all(str(k.get("environment")) != "production" for k in data.get("keys") or [])
