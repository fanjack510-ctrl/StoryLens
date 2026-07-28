"""Shared field validators for whole_book_contract_v1."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import AfterValidator
from typing_extensions import Annotated

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STAGE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_ASSET_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_RELATION_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_EVIDENCE_KEY_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,128}$")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("must be 64-char lowercase hex SHA-256")
    return value


def validate_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware UTC")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        # Normalize check: offset must be zero (UTC).
        if value.utcoffset().total_seconds() != 0:  # type: ignore[union-attr]
            raise ValueError("datetime must be UTC (offset 0)")
    return value


def validate_stage_code(value: str) -> str:
    if not _STAGE_CODE_RE.fullmatch(value):
        raise ValueError("stage_code must match ^[a-z][a-z0-9_]{1,63}$")
    return value


def validate_asset_type(value: str) -> str:
    if not _ASSET_TYPE_RE.fullmatch(value):
        raise ValueError("asset_type must match ^[a-z][a-z0-9_]{2,63}$")
    return value


def validate_relation_type(value: str) -> str:
    if not _RELATION_TYPE_RE.fullmatch(value):
        raise ValueError("relation_type must match ^[a-z][a-z0-9_]{2,63}$")
    return value


def validate_evidence_key(value: str) -> str:
    if not _EVIDENCE_KEY_RE.fullmatch(value):
        raise ValueError("evidence_key must match ^[a-zA-Z0-9_.:-]{1,128}$")
    return value


def dedupe_sorted_positive_ints(values: list[int]) -> list[int]:
    unique = sorted(set(values))
    if any(v <= 0 for v in unique):
        raise ValueError("ids must be positive integers")
    return unique


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def is_json_compatible(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(is_json_compatible(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_json_compatible(v) for k, v in value.items())
    return False


def scan_sensitive_payload(payload: dict[str, Any], *, max_text_chars: int = 20_000) -> list[str]:
    """Return list of sensitivity issues found in checkpoint/payload dicts."""
    issues: list[str] = []
    blob = str(payload).lower()
    if "api_key" in blob or "authorization" in blob or "bearer " in blob:
        issues.append("possible_api_key")
    if "sk-" in blob and len(blob) > 40:
        issues.append("possible_api_key_token")
    # Heuristic: very large nested text suggests full novel / prompt / response dump.
    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, str) and len(obj) > max_text_chars:
            issues.append(f"oversized_text:{path or 'root'}")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:50]):
                walk(v, f"{path}[{i}]")

    walk(payload)
    return issues


Sha256Str = Annotated[str, AfterValidator(validate_sha256)]
UtcDatetime = Annotated[datetime, AfterValidator(validate_utc_datetime)]
StageCodeStr = Annotated[str, AfterValidator(validate_stage_code)]
AssetTypeStr = Annotated[str, AfterValidator(validate_asset_type)]
RelationTypeStr = Annotated[str, AfterValidator(validate_relation_type)]
EvidenceKeyStr = Annotated[str, AfterValidator(validate_evidence_key)]
