"""WholeBook Data Transfer Manifest contracts (Phase 2B-R1 Agent U).

Safe for frontend return. Must not contain novel body, prompt text, credentials,
provider raw responses, or payment info.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

DATA_TRANSFER_MANIFEST_SCHEMA = "storylens.whole_book_data_transfer_manifest"
DATA_TRANSFER_MANIFEST_VERSION = "1.0.0"

FORBIDDEN_MANIFEST_CONTENT_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "novel_body",
        "full_text",
        "prompt",
        "prompt_body",
        "system_instruction",
        "messages",
        "api_key",
        "credential",
        "credentials",
        "authorization",
        "raw_response",
        "provider_raw",
        "payment",
        "payment_info",
    }
)

# Normalized fields that participate in consent fingerprint.
CONSENT_FINGERPRINT_FIELDS: tuple[str, ...] = (
    "book_id",
    "book_snapshot_id",
    "module_key",
    "provider_key",
    "model_id",
    "execution_location",
    "context_bundle_hash",
    "selected_context_unit_ids",
    "selected_chapter_ids",
    "selected_paragraph_ids",
    "prompt_pack_id",
    "prompt_pack_version",
    "pricing_version",
    "sends_source_text",
    "sends_derived_text",
    "retention_policy",
    "estimated_input_tokens",
    "estimated_output_tokens",
    "estimated_cost_expected",
)


@dataclass(frozen=True, slots=True)
class WholeBookDataTransferManifest:
    schema: str
    version: str
    book_id: int
    book_snapshot_id: int
    module_key: str
    provider_key: str
    model_id: str
    execution_location: str
    context_bundle_hash: str
    selected_context_unit_ids: tuple[str, ...]
    selected_chapter_ids: tuple[str, ...]
    selected_paragraph_ids: tuple[str, ...]
    source_character_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_low: float | None
    estimated_cost_expected: float | None
    estimated_cost_high: float | None
    max_retry_cost: float | None
    pricing_version: str | None
    sends_source_text: bool
    sends_derived_text: bool
    retention_policy: str
    consent_required: bool
    consent_fingerprint: str
    estimate_fingerprint: str
    generated_at: datetime
    prompt_pack_id: str = ""
    prompt_pack_version: str = ""
    pricing_status: str = "known"  # known | unknown
    snapshot_content_hash: str = ""
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema != DATA_TRANSFER_MANIFEST_SCHEMA:
            raise ValueError("invalid data transfer manifest schema")
        if self.book_id <= 0 or self.book_snapshot_id <= 0:
            raise ValueError("book_id and book_snapshot_id must be positive")
        if self.source_character_count < 0:
            raise ValueError("source_character_count must be >= 0")

    def safe_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "version": self.version,
            "book_id": self.book_id,
            "book_snapshot_id": self.book_snapshot_id,
            "module_key": self.module_key,
            "provider_key": self.provider_key,
            "model_id": self.model_id,
            "execution_location": self.execution_location,
            "context_bundle_hash": self.context_bundle_hash,
            "selected_context_unit_ids": list(self.selected_context_unit_ids),
            "selected_chapter_ids": list(self.selected_chapter_ids),
            "selected_paragraph_ids": list(self.selected_paragraph_ids),
            "source_character_count": self.source_character_count,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_cost_low": self.estimated_cost_low,
            "estimated_cost_expected": self.estimated_cost_expected,
            "estimated_cost_high": self.estimated_cost_high,
            "max_retry_cost": self.max_retry_cost,
            "pricing_version": self.pricing_version,
            "pricing_status": self.pricing_status,
            "sends_source_text": self.sends_source_text,
            "sends_derived_text": self.sends_derived_text,
            "retention_policy": self.retention_policy,
            "consent_required": self.consent_required,
            "consent_fingerprint": self.consent_fingerprint,
            "estimate_fingerprint": self.estimate_fingerprint,
            "generated_at": self.generated_at.isoformat(),
            "prompt_pack_id": self.prompt_pack_id,
            "prompt_pack_version": self.prompt_pack_version,
            "snapshot_content_hash": self.snapshot_content_hash,
            "warnings": list(self.warnings),
        }
        for key in payload:
            if str(key).lower() in FORBIDDEN_MANIFEST_CONTENT_KEYS:
                raise ValueError(f"manifest must not expose forbidden key: {key}")
        return payload


@dataclass
class ConsentFingerprintService:
    """Compute and compare consent fingerprints from normalized Manifest fields."""

    version: str = "1.0.0"

    def compute(self, fields: Mapping[str, Any]) -> str:
        normalized = normalize_consent_fields(fields)
        raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def compute_from_manifest(self, manifest: WholeBookDataTransferManifest) -> str:
        return self.compute(manifest_consent_payload(manifest))

    def matches(self, *, consent_fingerprint: str, manifest: WholeBookDataTransferManifest) -> bool:
        return bool(consent_fingerprint) and consent_fingerprint == self.compute_from_manifest(manifest)


@dataclass
class DataTransferManifestValidator:
    """Validate Manifest safety and consent/estimate coupling."""

    consent: ConsentFingerprintService = field(default_factory=ConsentFingerprintService)

    def validate(self, manifest: WholeBookDataTransferManifest) -> None:
        payload = manifest.safe_dict()
        blob = json.dumps(payload, ensure_ascii=False).lower()
        for token in ("api_key", "sk-", "authorization:", "bearer ", "novel_body", "```"):
            if token in blob:
                raise ValueError("manifest serialization leaked sensitive content")
        expected = self.consent.compute_from_manifest(manifest)
        if manifest.consent_fingerprint != expected:
            raise ValueError("consent_fingerprint mismatch")

    def consent_still_valid(
        self,
        *,
        prior_fingerprint: str,
        manifest: WholeBookDataTransferManifest,
    ) -> bool:
        return self.consent.matches(consent_fingerprint=prior_fingerprint, manifest=manifest)


@dataclass
class DataTransferManifestBuilder:
    """Build frontend-safe WholeBookDataTransferManifest from estimate + selection."""

    consent: ConsentFingerprintService = field(default_factory=ConsentFingerprintService)
    validator: DataTransferManifestValidator | None = None

    def __post_init__(self) -> None:
        if self.validator is None:
            self.validator = DataTransferManifestValidator(consent=self.consent)

    def build(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_key: str,
        provider_key: str,
        model_id: str,
        execution_location: str,
        context_bundle_hash: str,
        selected_context_unit_ids: Sequence[str],
        selected_chapter_ids: Sequence[str],
        selected_paragraph_ids: Sequence[str],
        source_character_count: int,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        estimated_cost_low: float | None,
        estimated_cost_expected: float | None,
        estimated_cost_high: float | None,
        max_retry_cost: float | None,
        pricing_version: str | None,
        sends_source_text: bool,
        sends_derived_text: bool,
        retention_policy: str,
        consent_required: bool,
        estimate_fingerprint: str,
        prompt_pack_id: str = "",
        prompt_pack_version: str = "",
        pricing_status: str = "known",
        snapshot_content_hash: str = "",
        warnings: Sequence[str] = (),
        generated_at: datetime | None = None,
    ) -> WholeBookDataTransferManifest:
        ts = generated_at or datetime(2026, 7, 24, 0, 0, 0, tzinfo=timezone.utc)
        draft_fields = {
            "book_id": book_id,
            "book_snapshot_id": book_snapshot_id,
            "module_key": module_key,
            "provider_key": provider_key,
            "model_id": model_id,
            "execution_location": execution_location,
            "context_bundle_hash": context_bundle_hash,
            "selected_context_unit_ids": list(selected_context_unit_ids),
            "selected_chapter_ids": list(selected_chapter_ids),
            "selected_paragraph_ids": list(selected_paragraph_ids),
            "prompt_pack_id": prompt_pack_id,
            "prompt_pack_version": prompt_pack_version,
            "pricing_version": pricing_version,
            "sends_source_text": sends_source_text,
            "sends_derived_text": sends_derived_text,
            "retention_policy": retention_policy,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost_expected": estimated_cost_expected,
        }
        consent_fp = self.consent.compute(draft_fields)
        manifest = WholeBookDataTransferManifest(
            schema=DATA_TRANSFER_MANIFEST_SCHEMA,
            version=DATA_TRANSFER_MANIFEST_VERSION,
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_key=module_key,
            provider_key=provider_key,
            model_id=model_id,
            execution_location=execution_location,
            context_bundle_hash=context_bundle_hash,
            selected_context_unit_ids=tuple(selected_context_unit_ids),
            selected_chapter_ids=tuple(selected_chapter_ids),
            selected_paragraph_ids=tuple(selected_paragraph_ids),
            source_character_count=source_character_count,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_cost_low=estimated_cost_low,
            estimated_cost_expected=estimated_cost_expected,
            estimated_cost_high=estimated_cost_high,
            max_retry_cost=max_retry_cost,
            pricing_version=pricing_version,
            sends_source_text=sends_source_text,
            sends_derived_text=sends_derived_text,
            retention_policy=retention_policy,
            consent_required=consent_required,
            consent_fingerprint=consent_fp,
            estimate_fingerprint=estimate_fingerprint,
            generated_at=ts,
            prompt_pack_id=prompt_pack_id,
            prompt_pack_version=prompt_pack_version,
            pricing_status=pricing_status,
            snapshot_content_hash=snapshot_content_hash,
            warnings=tuple(warnings),
        )
        assert self.validator is not None
        self.validator.validate(manifest)
        return manifest


def normalize_consent_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in CONSENT_FINGERPRINT_FIELDS:
        if key not in fields and key not in {"prompt_pack_id", "prompt_pack_version"}:
            # prompt pack fields are optional in older callers but preferred.
            if key.startswith("prompt_pack"):
                continue
        value = fields.get(key)
        if isinstance(value, (list, tuple)):
            out[key] = list(value)
        else:
            out[key] = value
    # Always include prompt pack when present.
    for key in ("prompt_pack_id", "prompt_pack_version"):
        if key in fields:
            out[key] = fields[key]
    return out


def manifest_consent_payload(manifest: WholeBookDataTransferManifest) -> dict[str, Any]:
    return {
        "book_id": manifest.book_id,
        "book_snapshot_id": manifest.book_snapshot_id,
        "module_key": manifest.module_key,
        "provider_key": manifest.provider_key,
        "model_id": manifest.model_id,
        "execution_location": manifest.execution_location,
        "context_bundle_hash": manifest.context_bundle_hash,
        "selected_context_unit_ids": list(manifest.selected_context_unit_ids),
        "selected_chapter_ids": list(manifest.selected_chapter_ids),
        "selected_paragraph_ids": list(manifest.selected_paragraph_ids),
        "prompt_pack_id": manifest.prompt_pack_id,
        "prompt_pack_version": manifest.prompt_pack_version,
        "pricing_version": manifest.pricing_version,
        "sends_source_text": manifest.sends_source_text,
        "sends_derived_text": manifest.sends_derived_text,
        "retention_policy": manifest.retention_policy,
        "estimated_input_tokens": manifest.estimated_input_tokens,
        "estimated_output_tokens": manifest.estimated_output_tokens,
        "estimated_cost_expected": manifest.estimated_cost_expected,
    }
