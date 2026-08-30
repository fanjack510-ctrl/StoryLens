from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

ZERO = Decimal(0)


class UsageDisposition(StrEnum):
    BILLABLE = "billable"
    PLATFORM_RETRY = "platform_retry"
    PROVIDER_FAILED = "provider_failed"


class ModelAttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"
    ACCOUNTING_INCOMPLETE = "accounting_incomplete"


class RechargeOrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    CREDITED = "credited"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class WalletTransactionKind(StrEnum):
    RECHARGE = "recharge"
    RESERVE = "reserve"
    RELEASE = "release"
    CHARGE = "charge"
    REFUND = "refund"


class ModelPricingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    pricing_version: str = Field(min_length=1, max_length=64)
    input_per_million_cny: Decimal = Field(ge=ZERO)
    cached_input_per_million_cny: Decimal = Field(default=ZERO, ge=ZERO)
    output_per_million_cny: Decimal = Field(ge=ZERO)


class ModelUsageEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocation_id: str = Field(min_length=1, max_length=128)
    analysis_run_id: str = Field(min_length=1, max_length=64)
    input_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(ge=0)
    disposition: UsageDisposition = UsageDisposition.BILLABLE
    pricing: ModelPricingSnapshot

    @field_validator("cached_tokens")
    @classmethod
    def cached_tokens_do_not_exceed_input(cls, value: int, info: ValidationInfo) -> int:
        input_tokens = info.data.get("input_tokens")
        if input_tokens is not None and value > input_tokens:
            raise ValueError("cached tokens must not exceed input tokens")
        return value


class InternalModelCost(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    provider_cost_cny: Decimal = Field(ge=ZERO)
    customer_charge_cny: Decimal = Field(default=ZERO, ge=ZERO, le=ZERO)


class ModelUsageAggregate(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_run_id: str = Field(min_length=1, max_length=64)
    attempt_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    provider_cost_cny: Decimal = Field(ge=ZERO)
    usage_complete: bool
    has_unknown_attempt: bool
    customer_charge_cny: Decimal = Field(default=ZERO, ge=ZERO, le=ZERO)


class UsageCharge(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocation_id: str
    provider_cost_cny: Decimal = Field(ge=ZERO)
    customer_charge_cny: Decimal = Field(ge=ZERO)
    multiplier: Decimal = Field(ge=Decimal("1.0"))
    disposition: UsageDisposition


class AnalysisInvoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_run_id: str
    provider_cost_cny: Decimal = Field(ge=ZERO)
    unrounded_customer_charge_cny: Decimal = Field(ge=ZERO)
    settlement_rounding_cny: Decimal = Field(ge=ZERO)
    customer_charge_cny: Decimal = Field(ge=ZERO)
    multiplier: Decimal = Field(ge=Decimal("1.0"))
    charges: tuple[UsageCharge, ...]


class RechargeOrderReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    internal_order_no: str = Field(min_length=6, max_length=64)
    external_order_no: str | None = Field(default=None, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    amount_cny: Decimal = Field(gt=ZERO)
    status: RechargeOrderStatus
    created_at: datetime
    paid_at: datetime | None = None

    @field_validator("amount_cny")
    @classmethod
    def amount_has_cent_precision(cls, value: Decimal) -> Decimal:
        if value.as_tuple().exponent < -2:
            raise ValueError("recharge amount must use cent precision")
        return value
