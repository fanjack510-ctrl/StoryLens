"""MockExecutionQuotaPolicy — synthetic Lab limits only (Phase 2A-P).

Not commercial quota. Not License. Not Cloud Budget. Not persisted across restart.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MockExecutionQuotaPolicy:
    max_concurrent_mock_runs: int = 1
    max_mock_chapters: int = 50
    max_mock_characters: int = 200_000
    max_synthetic_tokens: int = 50_000
    max_synthetic_cost: float = 0.0
    max_run_duration_seconds: int = 600
    non_production: bool = True
    writes_commercial_usage: bool = False
    mutates_license: bool = False
    separate_from_cloud_budget: bool = True
    persist_across_restart: bool = False
    new_quota_table_forbidden: bool = True

    def __post_init__(self) -> None:
        if not self.non_production:
            raise ValueError("mock quota must be non_production")
        if self.writes_commercial_usage or self.mutates_license:
            raise ValueError("mock quota must not touch commercial usage or license")
        if not self.separate_from_cloud_budget:
            raise ValueError("mock quota must stay separate from cloud budget")
        if self.persist_across_restart:
            raise ValueError("mock quota must not pretend persistence across restart")
        if not self.new_quota_table_forbidden:
            raise ValueError("new quota tables are forbidden in Phase 2A")
        if self.max_concurrent_mock_runs < 1:
            raise ValueError("max_concurrent_mock_runs must be >= 1")


DEFAULT_MOCK_EXECUTION_QUOTA_POLICY = MockExecutionQuotaPolicy()


@dataclass(frozen=True, slots=True)
class MockBudgetGuardDecision:
    allowed: bool
    stage_key: str | None
    reason_code: str | None
    synthetic: bool = True
    release_execution_slot_on_deny: bool = True
    write_assets_on_deny: bool = False

    def __post_init__(self) -> None:
        if not self.allowed and self.write_assets_on_deny:
            raise ValueError("budget deny must not write assets")
        if not self.synthetic:
            raise ValueError("mock budget decisions are synthetic")


def deny_budget_at_stage(stage_key: str) -> MockBudgetGuardDecision:
    return MockBudgetGuardDecision(
        allowed=False,
        stage_key=stage_key,
        reason_code="MOCK_RUN_BUDGET_EXCEEDED",
        synthetic=True,
        release_execution_slot_on_deny=True,
        write_assets_on_deny=False,
    )


MOCK_QUOTA_RULES: tuple[str, ...] = (
    "non_production",
    "no_commercial_billing_write",
    "no_license_mutation",
    "separate_from_cloud_budget",
    "budget_guard_may_simulate_deny",
    "over_limit_no_asset_write",
    "over_limit_releases_slot",
    "usage_display_marked_synthetic",
    "no_new_quota_table",
    "no_restart_persistence_fiction",
)
