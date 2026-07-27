"""Local StoryLens Pro entitlement: offline signed licenses in SQLite.

Trust isolation (CHG-20260722-001):
- Formal runtimes (browser_local_production, tauri/packaged, Windows install)
  load ONLY config/license_public_keys.production.json and reject test keys.
- browser_local_dev / non-production load tests/fixtures/license_public_keys.test.json.
- Pytest must inject its own fixture path (or use the shared test fixture).
- Ordinary env vars cannot force production runtimes onto test public keys.
- Settings UI cannot edit trusted public keys.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core.paths import is_production_runtime, resource_root
from app.db.models import LocalLicense
from app.services.license_crypto import (
    CANONICAL_FEATURES,
    LicenseError,
    VerifiedLicense,
    parse_and_verify,
    peek_license_payload,
)

PRO_FEATURES = list(CANONICAL_FEATURES)
TrustMode = Literal["production", "development"]

_TEST_KEY_ID_RE = re.compile(r"(^test-)|(^fixture-)|(^tmp-)|(-test-)|(\.test$)", re.I)


def app_major_version() -> int:
    try:
        return int(str(__version__).split(".", 1)[0])
    except (TypeError, ValueError):
        return 1


def license_trust_mode() -> TrustMode:
    """Formal product shells always use production trust. Dev never upgrades via env alone."""
    if is_production_runtime():
        return "production"
    return "development"


def production_config_path() -> Path:
    return (resource_root() / "config" / "license_public_keys.production.json").resolve()


def test_fixture_config_path() -> Path:
    return (resource_root() / "tests" / "fixtures" / "license_public_keys.test.json").resolve()


def license_config_path() -> Path:
    """Default config path for the current runtime trust mode."""
    if license_trust_mode() == "production":
        return production_config_path()
    return test_fixture_config_path()


def load_license_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or license_config_path()
    if not cfg_path.is_file():
        return {"keys": [], "commerce": {}}
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _allowed_environments(mode: TrustMode) -> set[str]:
    if mode == "production":
        return {"production"}
    return {"test", "development"}


def _iter_key_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    items = config.get("keys") or []
    return [item for item in items if isinstance(item, dict)]


def public_keys_by_id(
    config: dict[str, Any] | None = None,
    *,
    trust_mode: TrustMode | None = None,
) -> dict[str, str]:
    mode = trust_mode or license_trust_mode()
    cfg = config if config is not None else load_license_config()
    allowed_env = _allowed_environments(mode)
    out: dict[str, str] = {}
    for item in _iter_key_entries(cfg):
        if item.get("status") not in {"active", "readonly"}:
            continue
        env = str(item.get("environment") or "").strip().lower()
        if env not in allowed_env:
            continue
        key_id = str(item.get("key_id") or "").strip()
        pub = str(item.get("public_key_b64url") or "").strip()
        if key_id and pub:
            # Development must never silently absorb production keys from a mixed file.
            if mode == "production" and _looks_like_test_key_id(key_id):
                continue
            out[key_id] = pub
    return out


def is_safe_https_commerce_url(url: str) -> bool:
    """Allow only remote https purchase URLs (no localhost / non-https schemes)."""
    raw = (url or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    if lower.startswith(("javascript:", "file:", "data:", "vbscript:", "http:")):
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(raw)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        return False
    return True


def commerce_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else load_license_config()
    commerce = cfg.get("commerce") or {}
    raw_url = str(commerce.get("afdian_product_url") or "").strip()
    safe_url = raw_url if is_safe_https_commerce_url(raw_url) else ""
    return {
        "afdian_product_url": safe_url,
        "product_code": str(commerce.get("product_code") or "storylens_pro"),
        "product_label": str(commerce.get("product_label") or "StoryLens Pro"),
    }


def has_usable_verification_keys(
    config: dict[str, Any] | None = None,
    *,
    trust_mode: TrustMode | None = None,
) -> bool:
    return bool(public_keys_by_id(config, trust_mode=trust_mode))


def known_test_key_ids() -> set[str]:
    """Key ids from the test fixture — used as a production denylist, never for verify."""
    path = test_fixture_config_path()
    if not path.is_file():
        return {"test-dev-001"}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"test-dev-001"}
    ids = {
        str(item.get("key_id") or "").strip()
        for item in _iter_key_entries(cfg)
        if str(item.get("key_id") or "").strip()
    }
    ids.add("test-dev-001")
    return ids


def _looks_like_test_key_id(key_id: str) -> bool:
    if not key_id:
        return False
    if key_id in known_test_key_ids():
        return True
    return bool(_TEST_KEY_ID_RE.search(key_id))


def peek_license_key_id(raw_code: str) -> str | None:
    try:
        payload = peek_license_payload(raw_code)
    except LicenseError:
        return None
    key_id = str(payload.get("key_id") or "").strip()
    return key_id or None


def reject_key_for_runtime(key_id: str, *, trust_mode: TrustMode | None = None) -> None:
    mode = trust_mode or license_trust_mode()
    if mode != "production":
        return
    if _looks_like_test_key_id(key_id):
        raise LicenseError(
            "LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME",
            "此授权码不能用于当前版本。",
        )


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
    cfg = load_license_config()
    commerce = commerce_config(cfg)
    mode = license_trust_mode()
    ready = has_usable_verification_keys(cfg, trust_mode=mode)
    not_configured_msg = (
        "专业版授权功能尚未配置。" if mode == "production" and not ready else None
    )
    base_meta = {
        "license_trust_mode": mode,
        "license_issuance_ready": ready,
        "license_issuance_message": not_configured_msg,
    }
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
            **base_meta,
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
        **base_meta,
    }


def can_use_feature(session: Session, feature_key: str) -> dict[str, Any]:
    """Compatibility adapter → CapabilityService (Phase 1C).

    Preserves the historical response shape. License entitlement (not full
    shipped/quota gate) drives ``enabled`` so existing Pro activation UX and
    non-Pro paths keep working. Unknown / unmapped legacy keys never authorize.
    """

    from app.narrative_core.capability_legacy import (
        LEGACY_VIP_FEATURE_KEYS,
        map_legacy_feature_key,
    )
    from app.narrative_core.enums import CapabilityKey, CapabilityReasonCode
    from app.narrative_core.services.capability_service import (
        DefaultCapabilityService,
        decision_to_compat_gate,
        resolve_capability_key,
    )

    snap = entitlement_snapshot(session)
    raw = (feature_key or "").strip()

    # Unknown key: not canonical and not a known legacy VIP key → deny.
    canonical_values = {item.value for item in CapabilityKey} | set(PRO_FEATURES)
    if raw not in canonical_values and raw not in LEGACY_VIP_FEATURE_KEYS:
        return {
            "enabled": False,
            "reason": "FEATURE_UNKNOWN",
            "source": "none",
            "edition": snap["edition"],
            "license_id": snap["license_id"],
            "major_version": snap["major_version"],
            "feature_key": feature_key,
            "capability_reason_code": CapabilityReasonCode.CAPABILITY_UNKNOWN.value,
        }

    if raw in LEGACY_VIP_FEATURE_KEYS:
        mapping = map_legacy_feature_key(raw)
        if mapping.capability_key is None:
            return {
                "enabled": False,
                "reason": "FEATURE_UNKNOWN",
                "source": "none",
                "edition": snap["edition"],
                "license_id": snap["license_id"],
                "major_version": snap["major_version"],
                "feature_key": feature_key,
                "capability_reason_code": CapabilityReasonCode.CAPABILITY_UNKNOWN.value,
            }

    resolved = resolve_capability_key(raw)
    if resolved is None:
        return {
            "enabled": False,
            "reason": "FEATURE_UNKNOWN",
            "source": "none",
            "edition": snap["edition"],
            "license_id": snap["license_id"],
            "major_version": snap["major_version"],
            "feature_key": feature_key,
            "capability_reason_code": CapabilityReasonCode.CAPABILITY_UNKNOWN.value,
        }

    service = DefaultCapabilityService(session)
    decision = service.evaluate_capability(resolved)
    return decision_to_compat_gate(
        decision,
        feature_key=feature_key,
        license_id=snap.get("license_id"),
        major_version=snap.get("major_version"),
        edition=str(snap.get("edition") or "free"),
    )


def activate_license_code(session: Session, raw_code: str) -> dict[str, Any]:
    mode = license_trust_mode()
    key_id = peek_license_key_id(raw_code)
    if key_id:
        reject_key_for_runtime(key_id, trust_mode=mode)

    keys = public_keys_by_id(trust_mode=mode)
    if mode == "production" and not keys:
        raise LicenseError(
            "LICENSE_ISSUANCE_NOT_CONFIGURED",
            "专业版授权功能尚未配置。",
        )

    try:
        verified = parse_and_verify(
            raw_code,
            public_keys_by_id=keys,
            expected_major_version=app_major_version(),
        )
    except LicenseError:
        raise
    # Defense in depth after verify.
    reject_key_for_runtime(verified.key_id, trust_mode=mode)
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

    for row in session.scalars(select(LocalLicense).where(LocalLicense.license_status == "active")):
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
