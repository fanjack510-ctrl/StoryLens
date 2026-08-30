from __future__ import annotations

from decimal import Decimal

import pytest
from storylens_online.contracts.billing import (
    ModelPricingSnapshot,
    ModelUsageEntry,
    UsageDisposition,
)
from storylens_online.services.pricing import build_analysis_invoice, calculate_usage_charge


def usage(
    invocation_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    disposition: UsageDisposition = UsageDisposition.BILLABLE,
) -> ModelUsageEntry:
    return ModelUsageEntry(
        invocation_id=invocation_id,
        analysis_run_id="run-1",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        disposition=disposition,
        pricing=ModelPricingSnapshot(
            provider="configured-provider",
            model="configured-model",
            pricing_version="2026-08-test",
            input_per_million_cny=Decimal(2),
            output_per_million_cny=Decimal(8),
        ),
    )


def test_actual_input_and_output_cost_is_charged_at_two_times() -> None:
    charge = calculate_usage_charge(
        usage("inv-1", input_tokens=1_000_000, output_tokens=500_000), Decimal("2.0")
    )
    assert charge.provider_cost_cny == Decimal("6.000000")
    assert charge.customer_charge_cny == Decimal("12.00")


def test_platform_retries_are_not_billed_to_user() -> None:
    charge = calculate_usage_charge(
        usage(
            "inv-retry",
            input_tokens=100_000,
            output_tokens=20_000,
            disposition=UsageDisposition.PLATFORM_RETRY,
        ),
        Decimal("2.0"),
    )
    assert charge.provider_cost_cny == 0
    assert charge.customer_charge_cny == 0


def test_invoice_rejects_usage_from_another_analysis() -> None:
    other = usage("inv-other", input_tokens=1, output_tokens=1).model_copy(
        update={"analysis_run_id": "run-other"}
    )
    with pytest.raises(ValueError, match="invoiced analysis run"):
        build_analysis_invoice("run-1", [other], Decimal("2.0"))


def test_invoice_rounds_once_for_the_whole_analysis() -> None:
    entries = [usage(f"inv-{index}", input_tokens=1, output_tokens=0) for index in range(10)]
    invoice = build_analysis_invoice("run-1", entries, Decimal("2.0"))

    assert invoice.provider_cost_cny == Decimal("0.000020")
    assert invoice.unrounded_customer_charge_cny == Decimal("0.000040")
    assert invoice.customer_charge_cny == Decimal("0.01")
    assert invoice.settlement_rounding_cny == Decimal("0.009960")
