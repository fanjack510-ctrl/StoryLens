"""CHG-20260726-006 — effective execution mode resolution."""

from __future__ import annotations

from app.services.execution_mode import resolve_effective_execution_mode


def test_aliyun_cloud_enabled_missing_mode_resolves_cloud():
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=True,
            configured_execution_mode=None,
        )
        == "cloud"
    )


def test_aliyun_cloud_enabled_stale_local_resolves_cloud():
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=True,
            configured_execution_mode="local",
        )
        == "cloud"
    )


def test_aliyun_explicit_cloud():
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=True,
            configured_execution_mode="cloud",
        )
        == "cloud"
    )


def test_aliyun_valid_hybrid():
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=True,
            configured_execution_mode="hybrid",
            local_provider_available=True,
        )
        == "hybrid"
    )


def test_aliyun_hybrid_without_local_falls_back_cloud():
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=True,
            configured_execution_mode="hybrid",
            local_provider_available=False,
        )
        == "cloud"
    )


def test_local_provider_resolves_local():
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=False,
            cloud_enabled=False,
            configured_execution_mode="local",
        )
        == "local"
    )


def test_cloud_provider_cloud_disabled_still_cloud_mode():
    # Callers raise switch/eligibility errors; must not become local.
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=False,
            configured_execution_mode="local",
        )
        == "cloud"
    )


def test_balanced_profile_string_is_not_execution_mode():
    # analysis profile names must not be treated as routing modes
    assert (
        resolve_effective_execution_mode(
            provider_is_cloud=True,
            cloud_enabled=True,
            configured_execution_mode="balanced",
        )
        == "cloud"
    )
