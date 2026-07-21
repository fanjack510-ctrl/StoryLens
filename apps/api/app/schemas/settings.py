from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class CloudSettings(BaseModel):
    enabled: bool = False
    state: Literal["disabled", "unconfigured", "no_healthy_provider", "available", "partial"] = (
        "disabled"
    )


class CloudSettingsUpdate(BaseModel):
    enabled: bool


class CloudBudgetUpdate(BaseModel):
    cloud_request_budget_enabled: bool = True
    cloud_max_input_tokens_per_request: int = Field(default=16000, ge=1, le=10_000_000)
    # Must be ≥ reader_journey scene/schema_repair defaults (3500); canary uses 4000.
    cloud_max_output_tokens_per_request: int = Field(default=4000, ge=1, le=1_000_000)
    # Real Canary v13: max HTTP attempts for one succeeded single-chapter run = 41.
    cloud_max_requests_per_run: int = Field(default=50, ge=1, le=10_000)
    cloud_daily_request_limit: int = Field(default=50, ge=1, le=1_000_000)
    cloud_daily_token_limit: int = Field(default=200000, ge=1, le=1_000_000_000)
    cloud_daily_estimated_cost_limit: float = Field(default=1.0, gt=0, le=1_000_000)
    currency: Literal["CNY"] = "CNY"
    cloud_stop_on_unknown_pricing: bool = True
    cloud_confirm_each_paid_test: bool = True


class CloudBudgetSettings(CloudBudgetUpdate):
    pricing_configured: bool = False
    pricing_version: str | None = None


class CloudPricingStatus(BaseModel):
    configured: bool
    valid: bool
    enabled: bool
    pricing_version: str | None = None
    currency: str | None = None
    model_names: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class CloudUsageSummary(BaseModel):
    date: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    currency: str
    remaining_requests: int
    remaining_tokens: int
    remaining_estimated_cost: float
    reserved_requests: int = 0
    reserved_tokens: int = 0
    reserved_estimated_cost: float = 0.0
    committed_requests: int | None = None
    committed_tokens: int | None = None
    committed_estimated_cost: float | None = None
    available_requests: int | None = None
    available_tokens: int | None = None
    available_estimated_cost: float | None = None
    within_budget: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    blocked_gate_count: int = 0


class ProviderConfigurationUpdate(BaseModel):
    display_name: str = "阿里云百炼"
    region: str = "cn-beijing"
    workspace_id: str = ""
    base_url: HttpUrl | None = None
    plus_model: str = "qwen3.7-plus"
    max_model: str = "qwen3.7-max"
    flash_model: str = "qwen3.6-flash"
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_retries: int = Field(default=3, ge=1, le=10)
    enabled: bool = False
    disconnected: bool = True
    allow_auto_route: bool = False
    raw_logging_enabled: bool = False
    api_key: str | None = Field(default=None, min_length=8)

    @model_validator(mode="before")
    @classmethod
    def empty_base_url_as_none(cls, data):
        # Frontend historically round-tripped GET responses with base_url="".
        # Empty string is not a valid HttpUrl and blocked ordinary-user saves.
        if isinstance(data, dict) and data.get("base_url") == "":
            data = {**data, "base_url": None}
        return data


class ProviderConfigurationResponse(BaseModel):
    provider_name: str
    display_name: str
    region: str
    workspace_id: str
    base_url: str
    plus_model: str
    max_model: str
    flash_model: str
    timeout_seconds: int
    max_retries: int
    enabled: bool
    disconnected: bool
    allow_auto_route: bool
    raw_logging_enabled: bool
    credential_state: Literal["missing", "configured", "invalid", "unknown"]
    connection_state: str
    updated_at: datetime | None = None


class ProviderTestRequest(BaseModel):
    confirmed: bool = False
    confirm_paid_request: bool | None = None
    test_type: Literal["minimal_json"] = "minimal_json"
    max_output_tokens: int = Field(default=32, ge=1, le=64)

    @model_validator(mode="after")
    def normalize_confirmation(self):
        if self.confirm_paid_request is True:
            self.confirmed = True
        return self


class ProviderConnectionTestPreflight(BaseModel):
    provider: str
    configured_model: str
    max_output_tokens: int
    max_real_requests: int = 1
    estimated_cost: float | None
    currency: str | None
    pricing_version: str | None
    remaining_requests: int
    remaining_tokens: int
    remaining_estimated_cost: float
    within_budget: bool
    blockers: list[str] = Field(default_factory=list)
    sends_user_content: bool = False


class ProviderConnectionTestResponse(BaseModel):
    status: Literal["healthy"]
    http_status: int
    provider: str
    configured_model: str
    response_model: str
    json_valid: bool
    schema_valid: bool
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    invocation_id: int
    estimated_cost: float | None
    currency: str | None
    pricing_version: str | None
    request_id: str | None
    retryable: bool = False


class DemoSettings(BaseModel):
    demo_mode: bool = True
    theme: Literal["light", "dark", "system"] = "light"
    font_size: int = Field(default=17, ge=14, le=26)
    line_height: float = Field(default=1.9, ge=1.3, le=2.6)


class RecommendedQwenSetupRequest(BaseModel):
    """Ordinary-user Bailian quick setup (wizard + settings share this)."""

    api_key: str | None = Field(default=None, min_length=8)
    analysis_mode: Literal["FAST", "BALANCED", "QUALITY"] = "BALANCED"
    cloud_body_consent: bool = False
    persist: bool = True


class RecommendedQwenRepairRequest(BaseModel):
    cloud_body_consent: bool | None = None


class RecommendedQwenSetupResponse(BaseModel):
    ok: bool
    user_message: str
    persisted: bool = False
    credential_configured: bool
    provider_enabled: bool
    cloud_enabled: bool
    provider_eligible: bool
    selected_provider_id: str
    connection_status: str
    analysis_mode: str | None = None
    blockers: list[str] = Field(default_factory=list)
    needs_cloud_consent: bool = False
    error_code: str | None = None
    model_service_validated: bool = False
    analysis_ready: bool = False
    readiness_reasons: list[str] = Field(default_factory=list)
