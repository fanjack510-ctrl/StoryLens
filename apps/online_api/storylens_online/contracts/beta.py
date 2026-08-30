from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PipelineName = Literal["phase2a_smoke", "phase2b1_txt_evidence_summary"]


class AuthCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("invalid email format")
        return normalized


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)


class AuthSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str = Field(min_length=16)
    user: AuthenticatedUser


class UserResponse(BaseModel):
    id: str
    email: str
    available_pipelines: tuple[PipelineName, ...] = ("phase2a_smoke",)


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    sha256: str
    file_size_bytes: int
    created_at: datetime


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)
    pipeline: PipelineName = "phase2a_smoke"


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    upload_id: str
    pipeline: PipelineName
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: int = Field(ge=0, le=100)
    public_error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class Phase2AResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    pipeline: Literal["phase2a_smoke"] = "phase2a_smoke"
    character_count: int = Field(ge=0)
    nonempty_line_count: int = Field(ge=0)
    file_size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    processing_duration_ms: int = Field(ge=0)
    real_ai_analysis: Literal[False] = False
    billing_status: Literal["not_billable"] = "not_billable"
    charged_cny: Literal[0] = 0


class EvidenceConclusion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    evidence_paragraph_ids: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence conclusion text must not be blank")
        return normalized

    @field_validator("evidence_paragraph_ids")
    @classmethod
    def validate_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item or len(item) > 64 for item in normalized):
            raise ValueError("evidence paragraph id is invalid")
        if len(set(normalized)) != len(normalized):
            raise ValueError("evidence paragraph ids must be unique")
        return normalized


class Phase2B1TxtEvidenceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: Literal["phase2b1_txt_evidence_summary"] = "phase2b1_txt_evidence_summary"
    overview: EvidenceConclusion
    findings: tuple[EvidenceConclusion, ...] = Field(min_length=1, max_length=20)
    paragraph_count: int = Field(gt=0)
    character_count: int = Field(gt=0, le=20_000)
    real_ai_analysis: Literal[True] = True
    billing_status: Literal["not_billable"] = "not_billable"
    charged_cny: Literal[0] = 0


PhaseResult = Annotated[
    Phase2AResult | Phase2B1TxtEvidenceResult,
    Field(discriminator="pipeline"),
]
PHASE_RESULT_ADAPTER = TypeAdapter(PhaseResult)


class JobResultResponse(BaseModel):
    job_id: str
    result: PhaseResult


class PublicErrorBody(BaseModel):
    code: str
    message: str


class PublicErrorResponse(BaseModel):
    error: PublicErrorBody


class PocketBaseRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)


class PocketBaseAuthResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str = Field(min_length=16)
    record: PocketBaseRecord


def phase_result_from_json(value: dict[str, Any]) -> PhaseResult:
    return PHASE_RESULT_ADAPTER.validate_python(value)


def phase2a_result_from_json(value: dict[str, Any]) -> Phase2AResult:
    """Backward-compatible helper retained for Phase 2A worker tests."""

    return Phase2AResult.model_validate(value)
