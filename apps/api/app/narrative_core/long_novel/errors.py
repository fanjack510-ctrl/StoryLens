"""Frozen error taxonomy for the LongNovelAnalysisEngine (Phase 1 Foundation).

The taxonomy is part of the frozen contract (05 §3). Two properties matter more than the
list itself:

1. **Every code has exactly one disposition.** ``FailureClass`` says whether a code may be
   repaired, whether it escalates to the parent unit, and whether it is terminal. Code that
   branches on the string instead of the class will drift.
2. **Ambiguity is a failure, not a default.** Codes such as ``REBASE_AMBIGUOUS`` and
   ``MENTION_OCCURRENCE_AMBIGUOUS`` exist so the engine can refuse rather than guess. A
   wrong guess in either place is silent identity corruption that passes every other check.
"""

from __future__ import annotations

from enum import StrEnum


class LongNovelErrorCode(StrEnum):
    """Every failure the engine may raise. One code, one meaning, one disposition."""

    # -- planning / budget (raised before any spend) --------------------------------
    OUTPUT_BUDGET_TOO_LOW = "OUTPUT_BUDGET_TOO_LOW"
    INPUT_BUDGET_TOO_LOW = "INPUT_BUDGET_TOO_LOW"
    STAGE_INPUT_OVER_BUDGET = "STAGE_INPUT_OVER_BUDGET"
    PROJECTION_OVER_BUDGET = "PROJECTION_OVER_BUDGET"
    REPAIR_INPUT_OVER_BUDGET = "REPAIR_INPUT_OVER_BUDGET"
    PLAN_NOT_FEASIBLE = "PLAN_NOT_FEASIBLE"

    # -- transport / provider -------------------------------------------------------
    PROVIDER_TRANSPORT_FAILED = "PROVIDER_TRANSPORT_FAILED"
    PROVIDER_REFUSED = "PROVIDER_REFUSED"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    TRUNCATED_OUTPUT = "TRUNCATED_OUTPUT"
    CAPABILITY_DRIFT = "CAPABILITY_DRIFT"

    # -- contract (the model produced something ill-formed) -------------------------
    JSON_WRAPPER_DAMAGE = "JSON_WRAPPER_DAMAGE"
    KEY_RENAME_DETERMINISTIC = "KEY_RENAME_DETERMINISTIC"
    ENUM_NORMALISABLE = "ENUM_NORMALISABLE"
    OMITTED_OPTIONAL_CONTAINER = "OMITTED_OPTIONAL_CONTAINER"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    INVALID_ENUM = "INVALID_ENUM"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    CARDINALITY_VIOLATION = "CARDINALITY_VIOLATION"
    FORBIDDEN_INTERPRETATION_FIELD = "FORBIDDEN_INTERPRETATION_FIELD"

    # -- reference / anchoring ------------------------------------------------------
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
    EVIDENCE_REFERENCE_INVALID = "EVIDENCE_REFERENCE_INVALID"
    EVIDENCE_ANCHOR_MISMATCH = "EVIDENCE_ANCHOR_MISMATCH"
    MENTION_ANCHOR_MISMATCH = "MENTION_ANCHOR_MISMATCH"
    MENTION_OCCURRENCE_AMBIGUOUS = "MENTION_OCCURRENCE_AMBIGUOUS"
    COVERAGE_GAP = "COVERAGE_GAP"

    # -- identity / rebase ----------------------------------------------------------
    REBASE_AMBIGUOUS = "REBASE_AMBIGUOUS"
    REBASE_FAILED = "REBASE_FAILED"
    OCCURRENCE_LINEAGE_UNVERIFIED = "OCCURRENCE_LINEAGE_UNVERIFIED"

    # -- persistence / legality -----------------------------------------------------
    SCAFFOLD_FORBIDDEN = "SCAFFOLD_FORBIDDEN"
    PHASE_WRITE_FORBIDDEN = "PHASE_WRITE_FORBIDDEN"
    INVARIANT_VIOLATED = "INVARIANT_VIOLATED"
    ASSET_NOT_REPLACEABLE = "ASSET_NOT_REPLACEABLE"


class FailureClass(StrEnum):
    """What the engine is allowed to do about a failure.

    ``LOCALLY_REPAIRABLE`` is the only class the engine fixes itself, and it fixes it with
    **zero provider calls**. There is deliberately no "reduced provider repair" class: a
    reduced repair drops the parent payload and asks the model to rebuild a whole asset
    from a truncated head of its own output, which produces a schema-valid asset holding a
    fraction of the facts — every invariant green, content silently gone.
    """

    LOCALLY_REPAIRABLE = "LOCALLY_REPAIRABLE"
    REPAIRABLE_WITH_FULL_PAYLOAD = "REPAIRABLE_WITH_FULL_PAYLOAD"
    ESCALATE_TO_PARENT = "ESCALATE_TO_PARENT"
    TERMINAL = "TERMINAL"
    TRANSPORT_RETRYABLE = "TRANSPORT_RETRYABLE"


#: Defects the engine repairs itself, deterministically, from the schema plus the invalid
#: output alone (05 §2.3.1). Membership is the *whole* eligibility rule — a defect that
#: needs the source text to fix is never in here.
LOCALLY_REPAIRABLE: frozenset[LongNovelErrorCode] = frozenset(
    {
        LongNovelErrorCode.JSON_WRAPPER_DAMAGE,
        LongNovelErrorCode.KEY_RENAME_DETERMINISTIC,
        LongNovelErrorCode.ENUM_NORMALISABLE,
        LongNovelErrorCode.OMITTED_OPTIONAL_CONTAINER,
    }
)


_DISPOSITION: dict[LongNovelErrorCode, FailureClass] = {
    # planning failures happen before spend and never retry against a provider
    LongNovelErrorCode.OUTPUT_BUDGET_TOO_LOW: FailureClass.TERMINAL,
    LongNovelErrorCode.INPUT_BUDGET_TOO_LOW: FailureClass.TERMINAL,
    LongNovelErrorCode.PLAN_NOT_FEASIBLE: FailureClass.TERMINAL,
    LongNovelErrorCode.STAGE_INPUT_OVER_BUDGET: FailureClass.TERMINAL,
    LongNovelErrorCode.PROJECTION_OVER_BUDGET: FailureClass.TERMINAL,
    LongNovelErrorCode.REPAIR_INPUT_OVER_BUDGET: FailureClass.ESCALATE_TO_PARENT,
    # transport
    LongNovelErrorCode.PROVIDER_TRANSPORT_FAILED: FailureClass.TRANSPORT_RETRYABLE,
    LongNovelErrorCode.PROVIDER_REFUSED: FailureClass.TERMINAL,
    LongNovelErrorCode.CAPABILITY_DRIFT: FailureClass.TRANSPORT_RETRYABLE,
    # a truncated or over-long output cannot be repaired by re-asking with the same shape:
    # the unit must get smaller, so it escalates at the parent
    LongNovelErrorCode.OUTPUT_LIMIT_EXCEEDED: FailureClass.ESCALATE_TO_PARENT,
    LongNovelErrorCode.TRUNCATED_OUTPUT: FailureClass.ESCALATE_TO_PARENT,
    # engine-local, zero provider calls
    LongNovelErrorCode.JSON_WRAPPER_DAMAGE: FailureClass.LOCALLY_REPAIRABLE,
    LongNovelErrorCode.KEY_RENAME_DETERMINISTIC: FailureClass.LOCALLY_REPAIRABLE,
    LongNovelErrorCode.ENUM_NORMALISABLE: FailureClass.LOCALLY_REPAIRABLE,
    LongNovelErrorCode.OMITTED_OPTIONAL_CONTAINER: FailureClass.LOCALLY_REPAIRABLE,
    # need the model, and need it to see the whole parent payload
    LongNovelErrorCode.SCHEMA_MISMATCH: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.INVALID_ENUM: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.MISSING_REQUIRED_FIELD: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.CARDINALITY_VIOLATION: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.FORBIDDEN_INTERPRETATION_FIELD: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.UNRESOLVED_REFERENCE: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.EVIDENCE_REFERENCE_INVALID: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.EVIDENCE_ANCHOR_MISMATCH: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.MENTION_ANCHOR_MISMATCH: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.MENTION_OCCURRENCE_AMBIGUOUS: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    LongNovelErrorCode.COVERAGE_GAP: FailureClass.REPAIRABLE_WITH_FULL_PAYLOAD,
    # identity: refuse, never guess
    LongNovelErrorCode.REBASE_AMBIGUOUS: FailureClass.ESCALATE_TO_PARENT,
    LongNovelErrorCode.REBASE_FAILED: FailureClass.ESCALATE_TO_PARENT,
    LongNovelErrorCode.OCCURRENCE_LINEAGE_UNVERIFIED: FailureClass.ESCALATE_TO_PARENT,
    # persistence
    LongNovelErrorCode.SCAFFOLD_FORBIDDEN: FailureClass.TERMINAL,
    LongNovelErrorCode.PHASE_WRITE_FORBIDDEN: FailureClass.TERMINAL,
    LongNovelErrorCode.INVARIANT_VIOLATED: FailureClass.TERMINAL,
    LongNovelErrorCode.ASSET_NOT_REPLACEABLE: FailureClass.TERMINAL,
}


def failure_class(code: LongNovelErrorCode) -> FailureClass:
    """Disposition of ``code``.

    Raises rather than defaulting: an unclassified code is a contract gap, and silently
    treating it as terminal (or as repairable) would hide that gap behind behaviour.
    """
    try:
        return _DISPOSITION[code]
    except KeyError:  # pragma: no cover - guarded by test_error_taxonomy_is_total
        raise AssertionError(f"{code} has no declared failure class") from None


def is_locally_repairable(code: LongNovelErrorCode) -> bool:
    """True iff the engine may fix this defect itself, sending nothing to a provider."""
    return code in LOCALLY_REPAIRABLE


class LongNovelError(RuntimeError):
    """A failure carrying its frozen code, its disposition and structured detail."""

    def __init__(
        self,
        code: LongNovelErrorCode,
        message: str = "",
        *,
        unit_key: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.failure_class = failure_class(code)
        self.unit_key = unit_key
        self.detail: dict[str, object] = dict(detail or {})
        # The message is never empty: an empty provider/engine error is unactionable in a
        # log, and this class is what the run reports to the user.
        self.message = message or code.value
        super().__init__(f"[{code.value}] {self.message}")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"LongNovelError(code={self.code.value!r}, "
            f"failure_class={self.failure_class.value!r}, unit_key={self.unit_key!r})"
        )
