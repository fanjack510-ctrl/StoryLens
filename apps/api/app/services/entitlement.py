"""Local StoryLens Pro entitlement: offline signed licenses in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core.paths import resource_root
from app.db.models import LocalLicense
from app.services.license_crypto import (
    CANONICAL_FEATURES,
    LicenseError,
    VerifiedLicense,
    parse_and_verify,
)

PRO_FEATURES = list(CANONICAL_FEATURES)


def app_major_version() -> int:
    try:
        return int(str(__version__).split(".", 1)[0])
    except (TypeError, ValueError):
        return 1


def license_config_path() -> Path:
    override = Path(__file__).resolve()
    del override
    return (resource_root() / "config" / "license_public_keys.json").resolve()


def load_license_config() -> dict[str, Any]:
    path = license_config_path()
    if not path.is_file():
        return {"keys": [], "commerce": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def public_keys_by_id(config: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = config or load_license_config()
    out: dict[str, str] = {}
    for item in cfg.get("keys") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"active", "readonly"}:
            continue
        key_id = str(item.get("key_id") or "").strip()
        pub = str(item.get("public_key_b64url") or "").strip()
        if key_id and pub:
            out[key_id] = pub
    return out


def commerce_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_license_config()
    commerce = cfg.get("commerce") or {}
    return {
        "afdian_product_url": str(commerce.get("afdian_product_url") or "").strip(),
        "product_code": str(commerce.get("product_code") or "storylens_pro"),
        "product_label": str(commerce.get("product_label") or "StoryLens Pro"),
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def active_license_row(session: Session) -> LocalLicense | None:
    rows = list(
        session.scalars(
            select(LocalLicense)
            .where(LocalLicense.license_status == "active")
            .order_by(LocalLicense.id.desc())
        )
    )
    return rows[0] if rows else None


def entitlement_snapshot(session: Session) -> dict[str, Any]:
    row = active_license_row(session)
    commerce = commerce_config()
    if row is None:
        return {
            "edition": "free",
            "edition_label": "StoryLens 免费版",
            "license_id": None,
            "license_id_masked": None,
            "major_version": None,
            "activated_at": None,
            "features": {key: False for key in PRO_FEATURES},
            "pro_active": False,
            "commerce": commerce,
        }
    features = {key: True for key in PRO_FEATURES}
    lid = row.license_id
    masked = f"{lid[:8]}…{lid[-4:]}" if lid and len(lid) > 12 else lid
    return {
        "edition": "pro",
        "edition_label": "StoryLens Pro",
        "license_id": lid,
        "license_id_masked": masked,
        "major_version": row.major_version,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
        "features": features,
        "pro_active": True,
        "commerce": commerce,
        "key_id": row.key_id,
    }


def can_use_feature(session: Session, feature_key: str) -> dict[str, Any]:
    snap = entitlement_snapshot(session)
    enabled = bool(snap["pro_active"] and snap["features"].get(feature_key))
    if feature_key not in PRO_FEATURES:
        return {
            "enabled": False,
            "reason": "FEATURE_UNKNOWN",
            "source": "none",
            "edition": snap["edition"],
            "license_id": snap["license_id"],
            "major_version": snap["major_version"],
            "feature_key": feature_key,
        }
    if enabled:
        return {
            "enabled": True,
            "reason": None,
            "source": "signed_local_license",
            "edition": snap["edition"],
            "license_id": snap["license_id"],
            "major_version": snap["major_version"],
            "feature_key": feature_key,
        }
    return {
        "enabled": False,
        "reason": "PRO_LICENSE_REQUIRED",
        "source": "none",
        "edition": snap["edition"],
        "license_id": None,
        "major_version": None,
        "feature_key": feature_key,
    }


def activate_license_code(session: Session, raw_code: str) -> dict[str, Any]:
    keys = public_keys_by_id()
    try:
        verified = parse_and_verify(
            raw_code,
            public_keys_by_id=keys,
            expected_major_version=app_major_version(),
        )
    except LicenseError as exc:
        raise
    return _persist_verified(session, verified)


def _persist_verified(session: Session, verified: VerifiedLicense) -> dict[str, Any]:
    payload = verified.payload
    license_id = str(payload["license_id"])
    existing = session.scalar(select(LocalLicense).where(LocalLicense.license_id == license_id))
    now = _now()
    if existing and existing.license_status == "active":
        existing.last_validated_at = now
        existing.signed_license = verified.signed_license
        session.commit()
        return {
            "ok": True,
            "already_active": True,
            "error_code": None,
            "user_message": "StoryLens Pro 已激活（该授权已在本机生效）。",
            "entitlement": entitlement_snapshot(session),
        }

    # Supersede other active rows for this product.
    for row in session.scalars(
        select(LocalLicense).where(LocalLicense.license_status == "active")
    ):
        row.license_status = "superseded"
        row.updated_at = now

    if existing is None:
        existing = LocalLicense(
            license_id=license_id,
            product_code=str(payload["product_code"]),
            edition=str(payload.get("edition") or "pro"),
            major_version=int(payload["major_version"]),
            license_status="active",
            signed_license=verified.signed_license,
            activated_at=now,
            last_validated_at=now,
            key_id=verified.key_id,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.license_status = "active"
        existing.signed_license = verified.signed_license
        existing.activated_at = existing.activated_at or now
        existing.last_validated_at = now
        existing.key_id = verified.key_id
        existing.updated_at = now
        existing.major_version = int(payload["major_version"])
        existing.product_code = str(payload["product_code"])
        existing.edition = str(payload.get("edition") or "pro")

    session.commit()
    return {
        "ok": True,
        "already_active": False,
        "error_code": None,
        "user_message": "StoryLens Pro 已激活",
        "entitlement": entitlement_snapshot(session),
    }
