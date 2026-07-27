"""Phase 2B-P Private Engine error codes (stable API / contract).

Messages must be user-safe: no full novel body, credentials, prompts, or stacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PrivateEngineErrorCode(StrEnum):
    PRIVATE_ENGINE_NOT_FOUND = "PRIVATE_ENGINE_NOT_FOUND"
    PRIVATE_ENGINE_SIGNATURE_INVALID = "PRIVATE_ENGINE_SIGNATURE_INVALID"
    PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE = "PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE"
    PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE = "PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE"
    PRIVATE_ENGINE_HEALTH_FAILED = "PRIVATE_ENGINE_HEALTH_FAILED"
    PROMPT_PACK_NOT_FOUND = "PROMPT_PACK_NOT_FOUND"
    PROMPT_PACK_SIGNATURE_INVALID = "PROMPT_PACK_SIGNATURE_INVALID"
    PROMPT_PACK_INCOMPATIBLE = "PROMPT_PACK_INCOMPATIBLE"
    CONTEXT_BUNDLE_INVALID = "CONTEXT_BUNDLE_INVALID"
    CONTEXT_BUNDLE_SNAPSHOT_MISMATCH = "CONTEXT_BUNDLE_SNAPSHOT_MISMATCH"
    CONTEXT_LIMIT_EXCEEDED = "CONTEXT_LIMIT_EXCEEDED"
    MODULE_NOT_SUPPORTED = "MODULE_NOT_SUPPORTED"
    MODULE_OUTPUT_SCHEMA_INVALID = "MODULE_OUTPUT_SCHEMA_INVALID"
    MODULE_OUTPUT_REFERENCE_INVALID = "MODULE_OUTPUT_REFERENCE_INVALID"
    MODULE_EVIDENCE_INSUFFICIENT = "MODULE_EVIDENCE_INSUFFICIENT"
    MODULE_EVIDENCE_HASH_MISMATCH = "MODULE_EVIDENCE_HASH_MISMATCH"
    MODULE_OUTPUT_DUPLICATE = "MODULE_OUTPUT_DUPLICATE"
    MODULE_OUTPUT_CONFLICT = "MODULE_OUTPUT_CONFLICT"
    PROVIDER_POLICY_INVALID = "PROVIDER_POLICY_INVALID"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_CANCELLED = "PROVIDER_CANCELLED"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    PROVIDER_BUDGET_EXCEEDED = "PROVIDER_BUDGET_EXCEEDED"
    DATA_HANDLING_CONSENT_REQUIRED = "DATA_HANDLING_CONSENT_REQUIRED"
    ENGINE_CHECKPOINT_INCOMPATIBLE = "ENGINE_CHECKPOINT_INCOMPATIBLE"


PRIVATE_ENGINE_ERROR_MESSAGES: dict[PrivateEngineErrorCode, str] = {
    PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND: "Private whole-book engine was not found.",
    PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID: "Private engine package signature is invalid.",
    PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE: "Private engine protocol version is incompatible.",
    PrivateEngineErrorCode.PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE: "Private engine is incompatible with this app version.",
    PrivateEngineErrorCode.PRIVATE_ENGINE_HEALTH_FAILED: "Private engine health check failed.",
    PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND: "Prompt pack was not found.",
    PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID: "Prompt pack signature is invalid.",
    PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE: "Prompt pack is incompatible with this engine or run.",
    PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID: "Context bundle is invalid or incomplete.",
    PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH: "Context bundle does not match the book snapshot.",
    PrivateEngineErrorCode.CONTEXT_LIMIT_EXCEEDED: "Context size exceeds the configured limit.",
    PrivateEngineErrorCode.MODULE_NOT_SUPPORTED: "Requested whole-book module is not supported.",
    PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID: "Module output failed schema validation.",
    PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID: "Module output references are invalid.",
    PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT: "Module output lacks required evidence.",
    PrivateEngineErrorCode.MODULE_EVIDENCE_HASH_MISMATCH: "Evidence paragraph hash does not match the snapshot.",
    PrivateEngineErrorCode.MODULE_OUTPUT_DUPLICATE: "Module output duplicates an existing candidate.",
    PrivateEngineErrorCode.MODULE_OUTPUT_CONFLICT: "Module output conflicts with another candidate.",
    PrivateEngineErrorCode.PROVIDER_POLICY_INVALID: "Provider policy is invalid for this request.",
    PrivateEngineErrorCode.PROVIDER_UNAVAILABLE: "Provider is unavailable.",
    PrivateEngineErrorCode.PROVIDER_TIMEOUT: "Provider request timed out.",
    PrivateEngineErrorCode.PROVIDER_CANCELLED: "Provider request was cancelled.",
    PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID: "Provider response is invalid.",
    PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED: "Provider budget was exceeded; no candidates were written.",
    PrivateEngineErrorCode.DATA_HANDLING_CONSENT_REQUIRED: "User consent is required for this data handling policy.",
    PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE: "Engine checkpoint is incompatible and cannot be resumed.",
}

_FORBIDDEN_MESSAGE_TOKENS: frozenset[str] = frozenset(
    {
        "api_key",
        "authorization:",
        "prompt=",
        "full_text",
        "novel_body",
        "credential",
        "bearer ",
        "sk-",
    }
)


@dataclass(frozen=True, slots=True)
class PrivateEngineError(Exception):
    code: PrivateEngineErrorCode
    message: str
    detail_code: str | None = None
    run_id: int | None = None
    stage_key: str | None = None
    module_key: str | None = None
    engine_id: str | None = None

    def __post_init__(self) -> None:
        if len(self.message) > 500:
            raise ValueError("error message must stay short (no novel body)")
        lower = self.message.lower()
        if any(token in lower for token in _FORBIDDEN_MESSAGE_TOKENS):
            raise ValueError("error message must not leak credentials, prompts, or body")

    def __str__(self) -> str:
        return self.message


def private_engine_error(code: PrivateEngineErrorCode, **kwargs: object) -> PrivateEngineError:
    message = PRIVATE_ENGINE_ERROR_MESSAGES[code]
    return PrivateEngineError(code=code, message=message, **kwargs)  # type: ignore[arg-type]


def all_private_engine_error_codes() -> tuple[str, ...]:
    return tuple(sorted(code.value for code in PrivateEngineErrorCode))


def validate_error_message_safe(message: str) -> None:
    """Raise ValueError if message is too long or leaks sensitive content."""

    if len(message) > 500:
        raise ValueError("error message must stay short (no novel body)")
    lower = message.lower()
    if any(token in lower for token in _FORBIDDEN_MESSAGE_TOKENS):
        raise ValueError("error message must not leak credentials, prompts, or body")
