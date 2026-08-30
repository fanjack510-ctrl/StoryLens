from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

ZERO = Decimal(0)


class UsageDisposition(StrEnum):
    BILLABLE = "billable"
    PLATFORM_RETRY = "platform_retry"
    PROVIDER_FAILED = "provider_failed"


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
    output_per_million_cny: Decimal = Field(ge=ZERO)


class ModelUsageEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocation_id: str = Field(min_length=1, max_length=128)
    analysis_run_id: str = Field(min_length=1, max_length=64)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    disposition: UsageDisposition = UsageDisposition.BILLABLE
    pricing: ModelPricingSnapshot


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
