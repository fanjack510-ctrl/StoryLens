from __future__ import annotations

from decimal import ROUND_HALF_UP, ROUND_UP, Decimal

from storylens_online.contracts.billing import (
    AnalysisInvoice,
    ModelUsageEntry,
    UsageCharge,
    UsageDisposition,
)

MILLION = Decimal(1000000)
PROVIDER_PRECISION = Decimal("0.000001")
CUSTOMER_PRECISION = Decimal("0.01")


def calculate_usage_charge(entry: ModelUsageEntry, multiplier: Decimal) -> UsageCharge:
    if multiplier < Decimal("1.0"):
        raise ValueError("billing multiplier cannot be below 1.0")

    if entry.disposition is not UsageDisposition.BILLABLE:
        return UsageCharge(
            invocation_id=entry.invocation_id,
            provider_cost_cny=Decimal(0),
            customer_charge_cny=Decimal(0),
            multiplier=multiplier,
            disposition=entry.disposition,
        )

    raw_cost = (
        Decimal(entry.input_tokens) * entry.pricing.input_per_million_cny / MILLION
        + Decimal(entry.output_tokens) * entry.pricing.output_per_million_cny / MILLION
    )
    provider_cost = raw_cost.quantize(PROVIDER_PRECISION, rounding=ROUND_HALF_UP)
    customer_charge = (provider_cost * multiplier).quantize(
        PROVIDER_PRECISION, rounding=ROUND_HALF_UP
    )
    return UsageCharge(
        invocation_id=entry.invocation_id,
        provider_cost_cny=provider_cost,
        customer_charge_cny=customer_charge,
        multiplier=multiplier,
        disposition=entry.disposition,
    )


def build_analysis_invoice(
    analysis_run_id: str,
    entries: list[ModelUsageEntry] | tuple[ModelUsageEntry, ...],
    multiplier: Decimal,
) -> AnalysisInvoice:
    if any(entry.analysis_run_id != analysis_run_id for entry in entries):
        raise ValueError("all usage entries must belong to the invoiced analysis run")
    charges = tuple(calculate_usage_charge(entry, multiplier) for entry in entries)
    provider_cost = sum((item.provider_cost_cny for item in charges), Decimal(0))
    unrounded_customer_charge = sum((item.customer_charge_cny for item in charges), Decimal(0))
    customer_charge = (
        unrounded_customer_charge.quantize(CUSTOMER_PRECISION, rounding=ROUND_UP)
        if unrounded_customer_charge > 0
        else Decimal(0)
    )
    return AnalysisInvoice(
        analysis_run_id=analysis_run_id,
        provider_cost_cny=provider_cost,
        unrounded_customer_charge_cny=unrounded_customer_charge,
        settlement_rounding_cny=customer_charge - unrounded_customer_charge,
        customer_charge_cny=customer_charge,
        multiplier=multiplier,
        charges=charges,
    )
