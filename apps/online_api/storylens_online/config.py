from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REDIS_BLOCKING_TIMEOUT_MARGIN_SECONDS = 2.0
PHASE2B1_LEASE_SAFETY_MARGIN_SECONDS = 30.0
PHASE2B1_ALLOWLIST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class OnlineConfigSnapshot(BaseModel):
    runtime: str
    database_backend: str
    redis_configured: bool
    pocketbase_configured: bool
    afdian_configured: bool
    billing_multiplier: Decimal
    frontend_origin: str


class OnlineSettings(BaseSettings):
    """Server settings; provider credentials are read from worker-only secret files."""

    model_config = SettingsConfigDict(
        env_prefix="STORYLENS_ONLINE_",
        env_file=None,
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    runtime: str = "hong_kong_beta"
    database_url: str = "postgresql+psycopg://storylens@postgres:5432/storylens_online"
    redis_url: str = "redis://redis:6379/0"
    pocketbase_url: str = "http://pocketbase:8090"
    pocketbase_auth_collection: str = "users"
    frontend_origin: str = "https://replace-with-your-domain.example"
    upload_dir: str = "/srv/storylens-online/uploads"
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    job_queue_name: str = "storylens:phase2a:jobs"
    worker_poll_seconds: int = Field(default=5, ge=1, le=60)
    redis_socket_timeout_seconds: float = Field(default=15.0, ge=3.0, le=300.0)
    redis_connect_timeout_seconds: float = Field(default=5.0, ge=0.5, le=60.0)
    worker_redis_retry_initial_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    worker_redis_retry_max_seconds: float = Field(default=15.0, ge=0.1, le=300.0)
    worker_lease_seconds: int = Field(default=900, ge=30, le=3600)
    session_cookie_max_age_seconds: int = Field(
        default=7 * 24 * 60 * 60,
        ge=300,
        le=30 * 24 * 60 * 60,
    )

    afdian_api_base_url: str = "https://afdian.net/api/open"
    afdian_user_id: str | None = None
    afdian_api_token: SecretStr | None = None
    afdian_allowed_plan_ids: str = ""

    billing_multiplier: Decimal = Field(default=Decimal("2.0"), ge=Decimal("1.0"))

    # Phase 2B1 is an internal-only, fixed-provider gate. The API consumes only
    # the feature flag, allowlist, and public-safe limits. Endpoint and secret
    # file settings are supplied exclusively to the worker container.
    phase2b1_enabled: bool = False
    phase2b1_allowlisted_user_ids_csv: str = ""
    phase2b1_provider: ClassVar[Literal["deepseek"]] = "deepseek"
    phase2b1_model: ClassVar[Literal["deepseek-v4-flash"]] = "deepseek-v4-flash"
    phase2b1_base_url: str | None = None
    phase2b1_api_key_file: str | None = None
    phase2b1_text_max_characters: int = Field(default=20_000, ge=1, le=20_000)
    phase2b1_text_max_bytes: int = Field(default=60_000, ge=1, le=60_000)
    phase2b1_prompt_max_tokens: int = Field(default=64_000, ge=1, le=64_000)
    phase2b1_max_completion_tokens: int = Field(default=2_048, ge=1, le=2_048)
    phase2b1_max_provider_calls: int = Field(default=2, ge=1, le=2)
    phase2b1_cost_cap_cny: Decimal = Field(
        default=Decimal("0.50"),
        gt=Decimal(0),
        le=Decimal("0.50"),
    )
    phase2b1_request_timeout_seconds: float = Field(default=120.0, ge=1.0, le=300.0)
    phase2b1_retry_initial_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    phase2b1_retry_max_seconds: float = Field(default=10.0, ge=0.1, le=120.0)
    phase2b1_pricing_version: ClassVar[str] = "deepseek-v4-flash@2026-08-30"
    phase2b1_fx_rate_version: ClassVar[str] = "safe-usdcny-central-parity-2026-08-28"
    phase2b1_fx_rate_to_cny: ClassVar[Decimal] = Decimal("6.7811")
    phase2b1_off_peak_cache_hit_usd: ClassVar[Decimal] = Decimal("0.007")
    phase2b1_off_peak_cache_miss_usd: ClassVar[Decimal] = Decimal("0.22")
    phase2b1_off_peak_output_usd: ClassVar[Decimal] = Decimal("0.66")
    phase2b1_peak_cache_hit_usd: ClassVar[Decimal] = Decimal("0.014")
    phase2b1_peak_cache_miss_usd: ClassVar[Decimal] = Decimal("0.44")
    phase2b1_peak_output_usd: ClassVar[Decimal] = Decimal("1.32")

    @field_validator("frontend_origin")
    @classmethod
    def validate_frontend_origin(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("online frontend origin must be an absolute https URL")
        return value.rstrip("/")

    @field_validator("pocketbase_url", "afdian_api_base_url")
    @classmethod
    def validate_service_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("service URL must be absolute http(s)")
        return value.rstrip("/")

    @field_validator("upload_dir", "job_queue_name", "pocketbase_auth_collection")
    @classmethod
    def validate_nonempty_runtime_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("runtime path and names must not be empty")
        return value.strip()

    @field_validator("phase2b1_base_url")
    @classmethod
    def validate_phase2b1_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from storylens_online.providers.deepseek import validate_base_url

        return validate_base_url(value.strip())

    @field_validator("phase2b1_api_key_file")
    @classmethod
    def validate_phase2b1_api_key_file(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        path = Path(value.strip())
        if not path.is_absolute():
            raise ValueError("Phase 2B1 API key file path must be absolute")
        return str(path)

    @field_validator("phase2b1_allowlisted_user_ids_csv")
    @classmethod
    def validate_phase2b1_allowlist(cls, value: str) -> str:
        user_ids = [item.strip() for item in value.split(",") if item.strip()]
        if any(not PHASE2B1_ALLOWLIST_ID_PATTERN.fullmatch(item) for item in user_ids):
            raise ValueError("Phase 2B1 allowlist contains an invalid user identifier")
        return ",".join(dict.fromkeys(user_ids))

    @model_validator(mode="after")
    def reject_desktop_database(self) -> OnlineSettings:
        scheme = urlparse(self.database_url).scheme.lower()
        if not scheme.startswith("postgresql"):
            raise ValueError("StoryLens Online requires PostgreSQL; desktop SQLite is not accepted")
        minimum_socket_timeout = self.worker_poll_seconds + REDIS_BLOCKING_TIMEOUT_MARGIN_SECONDS
        if self.redis_socket_timeout_seconds < minimum_socket_timeout:
            raise ValueError(
                "worker Redis socket timeout must include at least two seconds "
                "beyond the blocking poll timeout"
            )
        if self.worker_redis_retry_max_seconds < self.worker_redis_retry_initial_seconds:
            raise ValueError("worker Redis maximum retry delay must not be below its initial delay")
        if self.phase2b1_retry_max_seconds < self.phase2b1_retry_initial_seconds:
            raise ValueError("Phase 2B1 maximum retry delay must not be below its initial delay")
        if self.phase2b1_enabled:
            request_budget = (
                self.phase2b1_request_timeout_seconds * self.phase2b1_max_provider_calls
                + self.phase2b1_retry_max_seconds * (self.phase2b1_max_provider_calls - 1)
                + PHASE2B1_LEASE_SAFETY_MARGIN_SECONDS
            )
            if request_budget >= self.worker_lease_seconds:
                raise ValueError(
                    "Phase 2B1 request and retry budget must remain below the worker lease"
                )
        return self

    @property
    def allowed_afdian_plan_ids(self) -> frozenset[str]:
        return frozenset(
            item.strip() for item in self.afdian_allowed_plan_ids.split(",") if item.strip()
        )

    @property
    def phase2b1_allowlisted_user_ids(self) -> frozenset[str]:
        return frozenset(
            item.strip()
            for item in self.phase2b1_allowlisted_user_ids_csv.split(",")
            if item.strip()
        )

    def public_snapshot(self) -> OnlineConfigSnapshot:
        return OnlineConfigSnapshot(
            runtime=self.runtime,
            database_backend="postgresql",
            redis_configured=bool(self.redis_url),
            pocketbase_configured=bool(self.pocketbase_url),
            afdian_configured=bool(self.afdian_user_id and self.afdian_api_token),
            billing_multiplier=self.billing_multiplier,
            frontend_origin=self.frontend_origin,
        )
