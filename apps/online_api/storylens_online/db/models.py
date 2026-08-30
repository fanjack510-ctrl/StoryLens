from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


class OnlineBase(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WalletAccount(TimestampMixin, OnlineBase):
    __tablename__ = "online_wallet_accounts"
    __table_args__ = (
        CheckConstraint("balance_cny >= 0", name="ck_online_wallet_balance_nonnegative"),
        CheckConstraint("reserved_cny >= 0", name="ck_online_wallet_reserved_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    balance_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal(0))
    reserved_cny: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(0)
    )


class RechargeOrder(TimestampMixin, OnlineBase):
    __tablename__ = "online_recharge_orders"
    __table_args__ = (CheckConstraint("amount_cny > 0", name="ck_online_recharge_amount_positive"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    internal_order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    external_order_no: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="afdian")
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WalletTransaction(TimestampMixin, OnlineBase):
    __tablename__ = "online_wallet_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount_delta_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    balance_after_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    business_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingReservation(TimestampMixin, OnlineBase):
    __tablename__ = "online_billing_reservations"
    __table_args__ = (
        CheckConstraint("amount_cny > 0", name="ck_online_reservation_amount_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelUsageLedger(TimestampMixin, OnlineBase):
    __tablename__ = "online_model_usage_ledger"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="ck_online_usage_input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="ck_online_usage_output_tokens_nonnegative"),
        CheckConstraint("provider_cost_cny >= 0", name="ck_online_usage_provider_cost_nonnegative"),
        CheckConstraint("customer_charge_cny >= 0", name="ck_online_usage_charge_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invocation_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    analysis_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_cost_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    customer_charge_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class OnlineBookUpload(TimestampMixin, OnlineBase):
    __tablename__ = "online_book_uploads"
    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="ck_online_upload_size_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OnlineAnalysisJob(TimestampMixin, OnlineBase):
    __tablename__ = "online_analysis_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_online_job_user_idempotency"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_online_job_progress_range"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_online_job_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    upload_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    pipeline: Mapped[str] = mapped_column(String(32), nullable=False, default="phase2a_smoke")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    public_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
