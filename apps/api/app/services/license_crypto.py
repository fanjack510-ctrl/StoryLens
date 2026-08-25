"""Ed25519 offline license codec for StoryLens Pro (issuer + verifier shared logic)."""

from __future__ import annotations

import base64
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

PRODUCT_CODE = "storylens_pro"
EDITION = "pro"
LICENSE_PREFIX = "SLP1"
#: PRO 卖的东西。**只列真正属于 PRO 的**——全书分析是免费的核心功能，曾经也被签在这里，
#: 那是一个错误的承诺：用户自己付模型费，再收一次等于收「允许你使用自己买的算力」的钱。
#:
#: 每一项的可用状态见 `FEATURE_STATUS`。清单不该只是名字，还得说清今天能不能用——
#: 之前六项里只有一项真正有门，而买家看到的是六个名字。
CANONICAL_FEATURES = (
    "advanced_export",
    "common_patterns",
    "cross_book_search",
    "knowledge_extraction",
    "book_skill_generation",
    "narrative_asset_library",
    # 把它从清单里删掉，等于对已经买过的人收回一项已经发出去的能力——那是另一回事，
    # 不是「这一轮不做」。它的门和接口都在，留着；清单不撒谎靠的是下面的状态，不是删除。
    "pro_whole_book_insights",
)

#: available = 今天就能用；foundation = 免费基础兼容层；
#: engine_required = 门和接口都在，但要装了私有引擎才跑得起来，打包版没有它。
#: 界面按这个标状态，不把跑不起来的东西混在能用的里面卖。
FEATURE_STATUS: dict[str, str] = {
    "advanced_export": "available",
    "common_patterns": "available",
    "cross_book_search": "available",
    "knowledge_extraction": "available",
    "book_skill_generation": "available",
    "narrative_asset_library": "foundation",
    "pro_whole_book_insights": "engine_required",
}

#: 人话名字。让授权页能列出「你买到了什么」，而不是一串英文键。
FEATURE_LABELS: dict[str, str] = {
    "advanced_export": "成品报告导出（PDF）",
    "common_patterns": "共性视图：把一组书摆在一起看",
    "cross_book_search": "找相似写法",
    "knowledge_extraction": "从全书提取素材",
    "book_skill_generation": "生成作品 Skill",
    "narrative_asset_library": "知识库基础层（兼容项）",
    "pro_whole_book_insights": "章节素材聚合洞察（需私有引擎）",
}


class LicenseError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


# Back-compat aliases for internal callers.
_b64url_encode = b64url_encode
_b64url_decode = b64url_decode


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def load_private_key_b64url(raw: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_b64url_decode(raw.strip()))


def load_public_key_b64url(raw: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64url_decode(raw.strip()))


def public_key_b64url(public: Ed25519PublicKey) -> str:
    return _b64url_encode(
        public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def private_key_b64url(private: Ed25519PrivateKey) -> str:
    return _b64url_encode(
        private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def build_unsigned_payload(
    *,
    major_version: int,
    key_id: str,
    signature_version: int = 1,
    license_id: str | None = None,
    features: tuple[str, ...] | list[str] | None = None,
    valid_until: str | None = None,
) -> dict[str, Any]:
    payload = {
        "license_id": license_id or str(uuid.uuid4()),
        "product_code": PRODUCT_CODE,
        "edition": EDITION,
        "major_version": int(major_version),
        "issued_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "features": list(features or CANONICAL_FEATURES),
        "nonce": secrets.token_hex(8),
        "signature_version": int(signature_version),
        "key_id": key_id,
    }
    # Monthly cards (爱发电 one-shot purchases) are ordinary licenses with a signed
    # expiry. Absent field = perpetual, which keeps every previously issued license valid.
    if valid_until:
        payload["valid_until"] = valid_until
    return payload


def encode_license(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    body = _b64url_encode(canonical_payload_bytes(payload))
    signature = _b64url_encode(private_key.sign(canonical_payload_bytes(payload)))
    return f"{LICENSE_PREFIX}-{body}.{signature}"


_LICENSE_RE = re.compile(rf"^{LICENSE_PREFIX}-([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$")


@dataclass(frozen=True)
class VerifiedLicense:
    payload: dict[str, Any]
    signed_license: str
    key_id: str


def peek_license_payload(raw_code: str) -> dict[str, Any]:
    """Parse license payload without verifying the signature."""
    code = raw_code.strip().replace("\r", "").replace("\n", "").replace(" ", "")
    match = _LICENSE_RE.match(code)
    if not match:
        raise LicenseError("LICENSE_FORMAT_INVALID", "授权码格式无效。")
    body_b64 = match.group(1)
    try:
        payload = json.loads(b64url_decode(body_b64).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise LicenseError("LICENSE_FORMAT_INVALID", "授权码内容无法解析。") from exc
    if not isinstance(payload, dict):
        raise LicenseError("LICENSE_FORMAT_INVALID", "授权码内容无效。")
    return payload


def parse_and_verify(
    raw_code: str,
    *,
    public_keys_by_id: dict[str, str],
    expected_major_version: int,
    expected_product: str = PRODUCT_CODE,
) -> VerifiedLicense:
    code = raw_code.strip().replace("\r", "").replace("\n", "").replace(" ", "")
    match = _LICENSE_RE.match(code)
    if not match:
        raise LicenseError("LICENSE_FORMAT_INVALID", "授权码格式无效。")
    body_b64, sig_b64 = match.group(1), match.group(2)
    payload = peek_license_payload(code)

    key_id = str(payload.get("key_id") or "")
    pub_b64 = public_keys_by_id.get(key_id)
    if not pub_b64:
        raise LicenseError("LICENSE_KEY_UNSUPPORTED", "不支持的授权密钥。")

    if str(payload.get("product_code") or "") != expected_product:
        raise LicenseError("LICENSE_PRODUCT_MISMATCH", "授权产品不匹配。")
    try:
        major = int(payload.get("major_version"))
    except (TypeError, ValueError) as exc:
        raise LicenseError("LICENSE_MAJOR_VERSION_MISMATCH", "授权版本信息无效。") from exc
    if major != int(expected_major_version):
        raise LicenseError(
            "LICENSE_MAJOR_VERSION_MISMATCH",
            f"该授权适用于 StoryLens {major}.x，与当前大版本不兼容。",
        )

    try:
        public = load_public_key_b64url(pub_b64)
        public.verify(_b64url_decode(sig_b64), canonical_payload_bytes(payload))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise LicenseError("LICENSE_SIGNATURE_INVALID", "授权签名无效。") from exc

    # A monthly card that has already lapsed fails at activation with its own message,
    # rather than activating into an entitlement that every later check refuses.
    expires = payload_valid_until(payload)
    if expires is not None and expires <= datetime.now(timezone.utc):
        raise LicenseError("LICENSE_EXPIRED", "该授权已过期。请获取有效授权后重新激活。")

    return VerifiedLicense(payload=payload, signed_license=code, key_id=key_id)


def payload_valid_until(payload: dict[str, Any]) -> datetime | None:
    """The signed expiry, if the license carries one. None = perpetual."""
    raw = str(payload.get("valid_until") or payload.get("expires_at") or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
