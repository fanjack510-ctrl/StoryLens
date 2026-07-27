"""Quota contract re-exports (definitions live in capability.py)."""

from app.narrative_core.contracts.capability import QuotaDecision, QuotaPolicy

__all__ = ["QuotaPolicy", "QuotaDecision"]
