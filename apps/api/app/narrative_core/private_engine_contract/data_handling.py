"""Data handling / privacy policy contract (Phase 2B-P)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionLocation(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class WholeBookDataHandlingPolicy:
    execution_location: ExecutionLocation
    provider_kind: str
    sends_source_text: bool
    sends_derived_text: bool
    stores_provider_content: bool
    retention_policy: str
    user_consent_required: bool
    redaction_policy: str
    offline_supported: bool
    data_region: str | None
    policy_version: str

    def __post_init__(self) -> None:
        if self.sends_source_text and not self.user_consent_required:
            raise ValueError("sending source text requires user_consent_required=True")
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")


def requires_consent_for_upload(policy: WholeBookDataHandlingPolicy) -> bool:
    return policy.sends_source_text or (
        policy.execution_location in (ExecutionLocation.CLOUD, ExecutionLocation.HYBRID)
        and policy.user_consent_required
    )


DEFAULT_LOCAL_DATA_HANDLING_POLICY = WholeBookDataHandlingPolicy(
    execution_location=ExecutionLocation.LOCAL,
    provider_kind="local_fake",
    sends_source_text=False,
    sends_derived_text=False,
    stores_provider_content=False,
    retention_policy="none",
    user_consent_required=False,
    redaction_policy="no_full_text_in_logs",
    offline_supported=True,
    data_region=None,
    policy_version="1.0.0",
)

DEFAULT_CLOUD_DATA_HANDLING_POLICY = WholeBookDataHandlingPolicy(
    execution_location=ExecutionLocation.CLOUD,
    provider_kind="openai_compatible",
    sends_source_text=True,
    sends_derived_text=True,
    stores_provider_content=False,
    retention_policy="provider_ephemeral",
    user_consent_required=True,
    redaction_policy="no_full_text_in_logs_audit_artifact",
    offline_supported=False,
    data_region=None,
    policy_version="1.0.0",
)
