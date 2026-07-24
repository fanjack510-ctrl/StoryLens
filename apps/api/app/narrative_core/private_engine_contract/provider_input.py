"""Provider Input Bundle contracts (Phase 2B-R1 Agent U).

Ephemeral in-process only: no DB, Artifact, Audit, or API response bodies.
Novel text is untrusted; safe serialization omits text by default.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.narrative_core.private_engine_contract.provider_gateway import (
    FORBIDDEN_PROVIDER_REQUEST_KEYS,
)

PROVIDER_INPUT_BUNDLE_SCHEMA = "storylens.provider_input_bundle"
PROVIDER_INPUT_BUNDLE_VERSION = "1.0.0"
DEFAULT_PROVIDER_CONTEXT_CHAR_LIMIT = 120_000

FORBIDDEN_BUNDLE_KEYS: frozenset[str] = frozenset(
    {
        *FORBIDDEN_PROVIDER_REQUEST_KEYS,
        "api_key",
        "credential",
        "credentials",
        "authorization",
        "payment",
        "payment_info",
    }
)


@dataclass(frozen=True, slots=True)
class SourceDataBlock:
    block_id: str
    unit_type: str
    chapter_ref: str | None
    paragraph_refs: tuple[str, ...]
    source_kind: str
    character_count: int
    content_hash: str
    text: str = field(repr=False, default="")
    untrusted_source_data: bool = True

    def __post_init__(self) -> None:
        if not self.block_id.strip():
            raise ValueError("block_id is required")
        if self.character_count < 0:
            raise ValueError("character_count must be >= 0")
        if not self.untrusted_source_data:
            raise ValueError("novel source blocks must be marked untrusted_source_data=True")

    def __repr__(self) -> str:
        return (
            f"SourceDataBlock(block_id={self.block_id!r}, unit_type={self.unit_type!r}, "
            f"chars={self.character_count}, untrusted=True, text_omitted=True)"
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "unit_type": self.unit_type,
            "chapter_ref": self.chapter_ref,
            "paragraph_refs": list(self.paragraph_refs),
            "source_kind": self.source_kind,
            "character_count": self.character_count,
            "content_hash": self.content_hash,
            "untrusted_source_data": True,
            # text excluded by default
        }


@dataclass(frozen=True, slots=True)
class ProviderChatMessage:
    role: str
    content: str = field(repr=False)
    untrusted_source_data: bool = False

    def __repr__(self) -> str:
        return (
            f"ProviderChatMessage(role={self.role!r}, chars={len(self.content)}, "
            f"untrusted={self.untrusted_source_data})"
        )

    def to_openai_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    def safe_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "character_count": len(self.content),
            "untrusted_source_data": self.untrusted_source_data,
            "content_omitted": True,
        }


@dataclass(frozen=True, slots=True)
class ProviderInputBundle:
    schema: str
    version: str
    request_id: str
    book_id: int
    book_snapshot_id: int
    module_key: str
    context_bundle_hash: str
    prompt_pack_id: str
    prompt_pack_version: str
    system_instruction_ref: str
    source_data_blocks: tuple[SourceDataBlock, ...]
    response_schema_ref: str
    source_language: str
    output_locale: str
    provider_key: str
    model_id: str
    quality_profile: str
    token_budget: int | None
    cost_budget: float | None
    data_handling_policy: Mapping[str, Any]
    bundle_fingerprint: str
    system_instruction: str = field(repr=False, default="")
    messages: tuple[ProviderChatMessage, ...] = field(repr=False, default=())
    selected_context_unit_ids: tuple[str, ...] = ()
    selected_chapter_ids: tuple[str, ...] = ()
    selected_paragraph_ids: tuple[str, ...] = ()
    context_limit_ok: bool = True
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema != PROVIDER_INPUT_BUNDLE_SCHEMA:
            raise ValueError("invalid provider input bundle schema")
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if self.book_id <= 0 or self.book_snapshot_id <= 0:
            raise ValueError("book_id and book_snapshot_id must be positive")
        _assert_no_credentials(self.data_handling_policy)
        if self.messages:
            system_msgs = [m for m in self.messages if m.role == "system"]
            user_msgs = [m for m in self.messages if m.role == "user"]
            if system_msgs and user_msgs:
                for block in self.source_data_blocks:
                    if block.text and block.text in system_msgs[0].content:
                        raise ValueError("source_data must not alter system instruction")
            if any(m.untrusted_source_data for m in system_msgs):
                raise ValueError("system instruction must not be marked untrusted source")

    def __repr__(self) -> str:
        return (
            f"ProviderInputBundle(request_id={self.request_id!r}, module_key={self.module_key!r}, "
            f"blocks={len(self.source_data_blocks)}, fingerprint={self.bundle_fingerprint!r}, "
            f"bodies_omitted=True)"
        )

    def safe_dict(self) -> dict[str, Any]:
        """Safe serialization — excludes novel text, instructions, and messages."""
        return {
            "schema": self.schema,
            "version": self.version,
            "request_id": self.request_id,
            "book_id": self.book_id,
            "book_snapshot_id": self.book_snapshot_id,
            "module_key": self.module_key,
            "context_bundle_hash": self.context_bundle_hash,
            "prompt_pack_id": self.prompt_pack_id,
            "prompt_pack_version": self.prompt_pack_version,
            "system_instruction_ref": self.system_instruction_ref,
            "source_data_blocks": [b.safe_dict() for b in self.source_data_blocks],
            "response_schema_ref": self.response_schema_ref,
            "source_language": self.source_language,
            "output_locale": self.output_locale,
            "provider_key": self.provider_key,
            "model_id": self.model_id,
            "quality_profile": self.quality_profile,
            "token_budget": self.token_budget,
            "cost_budget": self.cost_budget,
            "data_handling_policy": dict(self.data_handling_policy),
            "bundle_fingerprint": self.bundle_fingerprint,
            "selected_context_unit_ids": list(self.selected_context_unit_ids),
            "selected_chapter_ids": list(self.selected_chapter_ids),
            "selected_paragraph_ids": list(self.selected_paragraph_ids),
            "context_limit_ok": self.context_limit_ok,
            "warnings": list(self.warnings),
        }

    def transport_messages(self) -> tuple[dict[str, str], ...]:
        if self.messages:
            return tuple(m.to_openai_dict() for m in self.messages)
        # Fallback assembly from instruction + blocks (tests / fake path).
        source = "\n\n".join(b.text for b in self.source_data_blocks if b.text)
        return (
            {"role": "system", "content": self.system_instruction or f"instruction_ref={self.system_instruction_ref}"},
            {
                "role": "user",
                "content": (
                    f"<untrusted_source_data>\n{source}\n</untrusted_source_data>"
                    if source
                    else f"input_bundle_ref={self.request_id}"
                ),
            },
        )

    def source_character_count(self) -> int:
        return sum(b.character_count for b in self.source_data_blocks)

    def recomputed_fingerprint(self) -> str:
        return compute_provider_input_bundle_fingerprint(self)


def compute_provider_input_bundle_fingerprint(bundle: ProviderInputBundle) -> str:
    payload = {
        "schema": bundle.schema,
        "version": bundle.version,
        "request_id": bundle.request_id,
        "book_id": bundle.book_id,
        "book_snapshot_id": bundle.book_snapshot_id,
        "module_key": bundle.module_key,
        "context_bundle_hash": bundle.context_bundle_hash,
        "prompt_pack_id": bundle.prompt_pack_id,
        "prompt_pack_version": bundle.prompt_pack_version,
        "system_instruction_ref": bundle.system_instruction_ref,
        "block_hashes": [b.content_hash for b in bundle.source_data_blocks],
        "provider_key": bundle.provider_key,
        "model_id": bundle.model_id,
        "quality_profile": bundle.quality_profile,
        "response_schema_ref": bundle.response_schema_ref,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_provider_input_bundle_fingerprint(**fields: Any) -> str:
    raw = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assert_context_within_limit(
    bundle: ProviderInputBundle,
    *,
    limit: int = DEFAULT_PROVIDER_CONTEXT_CHAR_LIMIT,
) -> None:
    if bundle.source_character_count() > limit or not bundle.context_limit_ok:
        from app.narrative_core.private_engine_contract.errors import (
            PrivateEngineErrorCode,
            private_engine_error,
        )

        raise private_engine_error(PrivateEngineErrorCode.CONTEXT_LIMIT_EXCEEDED)


def _assert_no_credentials(mapping: Mapping[str, Any]) -> None:
    for key in mapping:
        lowered = str(key).lower()
        if lowered in FORBIDDEN_BUNDLE_KEYS or lowered.endswith("_api_key"):
            raise ValueError(f"credential-like key forbidden in provider bundle: {key}")


@dataclass(frozen=True, slots=True)
class ResolvedProviderPayload:
    """Process-local resolved payload bound at execute boundary."""

    messages: tuple[dict[str, str], ...]
    input_bundle: ProviderInputBundle | None = None
    response_format_mode: str = "json_object"
    response_schema: Mapping[str, Any] | None = None
    response_schema_ref: str | None = None
    allow_tools: bool = False
    # Schema repair (max 1) authorized by estimate/consent budget.
    allow_schema_repair: bool = True
    max_repair_count: int = 1

    def __post_init__(self) -> None:
        if self.allow_tools:
            raise ValueError("provider payload must forbid tools/network from model")
        if not self.messages:
            raise ValueError("resolved provider payload requires messages")
        if int(self.max_repair_count) < 0 or int(self.max_repair_count) > 1:
            raise ValueError("max_repair_count must be 0 or 1")


@runtime_checkable
class ProviderInputBundleResolver(Protocol):
    def resolve(self, **kwargs: Any) -> ProviderInputBundle: ...

    def estimate(self, bundle: ProviderInputBundle, **kwargs: Any) -> Any: ...

    def build_transfer_manifest(self, bundle: ProviderInputBundle, **kwargs: Any) -> Any: ...

    def validate_consent(self, *, consent_fingerprint: str, manifest: Any) -> bool: ...
