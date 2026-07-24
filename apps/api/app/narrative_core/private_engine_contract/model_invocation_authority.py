"""Phase 2B-R1 Lab Live provider call ledger authority.

STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE for Private Lab / BookOverview Live path.
model_invocations remains the ledger for legacy chapter/scene structured_output pipelines only.
Do not dual-write Lab Live attempts into model_invocations.
"""

from __future__ import annotations

AUTHORITY = "STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE"

__all__ = ["AUTHORITY"]
