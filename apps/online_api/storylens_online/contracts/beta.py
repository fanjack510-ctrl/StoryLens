from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    sha256: str
    file_size_bytes: int
    created_at: datetime


class JobCreateRequest(BaseModel):
    upload_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    upload_id: str
    pipeline: str
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


class JobResultResponse(BaseModel):
    job_id: str
    result: Phase2AResult


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


def phase2a_result_from_json(value: dict[str, Any]) -> Phase2AResult:
    return Phase2AResult.model_validate(value)
