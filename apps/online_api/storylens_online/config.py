from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OnlineConfigSnapshot(BaseModel):
    runtime: str
    database_backend: str
    redis_configured: bool
    pocketbase_configured: bool
    afdian_configured: bool
    billing_multiplier: Decimal
    frontend_origin: str


class OnlineSettings(BaseSettings):
    """Server-side settings; secrets are accepted only through environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="STORYLENS_ONLINE_",
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    runtime: str = "hong_kong_beta"
    database_url: str = "postgresql+psycopg://storylens@postgres:5432/storylens_online"
    redis_url: str = "redis://redis:6379/0"
    pocketbase_url: str = "http://pocketbase:8090"
    pocketbase_auth_collection: str = "users"
    frontend_origin: str = "https://replace-with-your-domain.example"

    afdian_api_base_url: str = "https://afdian.net/api/open"
    afdian_user_id: str | None = None
    afdian_api_token: SecretStr | None = None
    afdian_allowed_plan_ids: str = ""

    billing_multiplier: Decimal = Field(default=Decimal("2.0"), ge=Decimal("1.0"))

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

    @model_validator(mode="after")
    def reject_desktop_database(self) -> OnlineSettings:
        scheme = urlparse(self.database_url).scheme.lower()
        if not scheme.startswith("postgresql"):
            raise ValueError("StoryLens Online requires PostgreSQL; desktop SQLite is not accepted")
        return self

    @property
    def allowed_afdian_plan_ids(self) -> frozenset[str]:
        return frozenset(
            item.strip() for item in self.afdian_allowed_plan_ids.split(",") if item.strip()
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
