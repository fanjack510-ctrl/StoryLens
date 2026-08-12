"""``ProviderIO`` — truncation detection, safe JSON recovery and the repair ladder (05 §2–3).

Three responsibilities, in the order they matter:

**Detect truncation honestly.** A response cut off at the output ceiling is not a schema
problem, and treating it as one wastes a paid retry on a request that will be cut off again.
Truncation escalates at the *parent*: the unit gets smaller, or the run stops.

**Repair locally, for free, whenever the fix is determined by the schema plus the invalid
output alone.** Stripping a code fence, normalising an unambiguous enum, filling an omitted
optional container — these need no model. Sending them to a provider costs money and adds a
chance of making things worse.

**Never ask a model to rebuild an asset from a fragment of itself.** The ladder has exactly
three outcomes and no ambiguous middle. The retired "reduced repair" dropped the parent
payload and showed the model the first 800 tokens of its own broken output, then asked for a
complete valid asset — producing a schema-valid asset holding a fraction of the facts. Every
invariant stayed green while most of the chapter silently disappeared. That is why
``REPAIR_INVALID_HEAD_TOKENS`` exists to *show the defect*, never to *carry the content*.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel.contracts.enums import UnitKind
from app.narrative_core.long_novel.errors import (
    LOCALLY_REPAIRABLE,
    LongNovelError,
    LongNovelErrorCode,
)

__all__ = [
    "RepairDecision",
    "RepairPlan",
    "RecoveryOutcome",
    "detect_truncation",
    "recover_json",
    "plan_repair",
]

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


class RepairDecision(StrEnum):
    """The only three things that may happen to an invalid response."""

    #: Fixed by the engine. Zero provider calls, zero tokens, no risk of content loss.
    ENGINE_LOCAL = "engine_local"
    #: Re-ask with the **full** parent payload plus a bounded error appendix.
    FULL_PROVIDER_REPAIR = "full_provider_repair"
    #: Cannot be repaired at this unit: split the parent if it is splittable, else terminal.
    ESCALATE_AT_PARENT = "escalate_at_parent"


@dataclass(frozen=True)
class RepairPlan:
    decision: RepairDecision
    code: LongNovelErrorCode
    reason: str
    repair_input_tokens: int = 0
    parent_splittable: bool = False


@dataclass
class RecoveryOutcome:
    """What the engine managed to recover, and exactly what it did to get there.

    ``steps`` is not decoration: a silently repaired payload is indistinguishable from a
    clean one, and when a model's output degrades the only way to notice is to see which
    repairs started firing.
    """

    value: Any | None
    steps: list[str] = field(default_factory=list)
    code: LongNovelErrorCode | None = None
    message: str = ""

    @property
    def recovered(self) -> bool:
        return self.value is not None


def detect_truncation(
    *,
    finish_reason: str | None,
    raw_text: str,
    requested_output_tokens: int,
    output_tokens: int | None,
    declared_max_output_tokens: int,
) -> LongNovelErrorCode | None:
    """Classify a response as truncated, capability-drifted, or neither.

    Three independent signals, because no provider gives all three reliably:

    * an explicit ``length`` finish reason;
    * an output token count at the requested ceiling;
    * text that simply does not close its own JSON.

    ``CAPABILITY_DRIFT`` is separated from ``TRUNCATED_OUTPUT`` deliberately: a model that
    stops short of a budget it *declared* it could reach has an untrustworthy declared
    value, and continuing to plan against that value would keep producing truncated units.
    The declared value is quarantined to what was actually achieved.
    """
    hit_ceiling = (finish_reason or "").lower() in {"length", "max_tokens", "max_output_tokens"} or (
        output_tokens is not None and requested_output_tokens > 0 and output_tokens >= requested_output_tokens
    )
    if hit_ceiling:
        if requested_output_tokens < declared_max_output_tokens:
            return LongNovelErrorCode.CAPABILITY_DRIFT
        return LongNovelErrorCode.TRUNCATED_OUTPUT
    if raw_text and not _looks_closed(raw_text):
        return LongNovelErrorCode.TRUNCATED_OUTPUT
    return None


def _looks_closed(text: str) -> bool:
    """Cheap structural check: are all JSON delimiters balanced outside of strings?

    Cheap on purpose — this runs on every response, and a full parse would reject payloads
    that :func:`recover_json` can still repair for free.
    """
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


def _strip_wrapper(text: str) -> str:
    """P1/P2: remove a code fence and any prose around the outermost JSON value."""
    stripped = _FENCE.sub("", text.strip())
    first = min(
        (i for i in (stripped.find("{"), stripped.find("[")) if i >= 0),
        default=-1,
    )
    if first < 0:
        return stripped
    last = max(stripped.rfind("}"), stripped.rfind("]"))
    if last <= first:
        return stripped
    return stripped[first : last + 1]


def recover_json(
    raw_text: str,
    *,
    legal_keys: Mapping[str, Sequence[str]] | None = None,
    legal_enums: Mapping[str, Sequence[str]] | None = None,
    optional_containers: Mapping[str, Any] | None = None,
) -> RecoveryOutcome:
    """Recover a valid payload from a damaged one, using only the schema and the output.

    Every step is a *content-preserving* transformation: nothing here invents, drops or
    rewrites a value the model produced. That restriction is the whole eligibility rule for
    engine-local repair — a defect that needs the source text to fix is not repairable here
    and must not be smuggled in by a lenient step.

    A rename or enum normalisation is applied **only when exactly one legal target exists**.
    Two plausible targets is genuine ambiguity, and guessing would silently change meaning.
    """
    steps: list[str] = []

    if not raw_text or not raw_text.strip():
        return RecoveryOutcome(
            value=None,
            code=LongNovelErrorCode.SCHEMA_MISMATCH,
            message="empty provider response",
        )

    candidate = raw_text
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        stripped = _strip_wrapper(candidate)
        if stripped != candidate.strip():
            steps.append("strip_wrapper")
        candidate = stripped
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            de_comma = _TRAILING_COMMA.sub(r"\1", candidate)
            if de_comma != candidate:
                steps.append("remove_trailing_comma")
                candidate = de_comma
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError as exc:
                # Unbalanced delimiters here mean the text stopped mid-structure, which is
                # truncation, not wrapper damage — and truncation is not locally repairable.
                code = (
                    LongNovelErrorCode.TRUNCATED_OUTPUT
                    if not _looks_closed(candidate)
                    else LongNovelErrorCode.JSON_WRAPPER_DAMAGE
                )
                return RecoveryOutcome(
                    value=None, steps=steps, code=code, message=f"unparseable JSON: {exc.msg}"
                )

    if isinstance(value, dict):
        value = _apply_key_renames(value, legal_keys or {}, steps)
        value = _normalise_enums(value, legal_enums or {}, steps)
        value = _fill_optional_containers(value, optional_containers or {}, steps)

    return RecoveryOutcome(value=value, steps=steps)


def _apply_key_renames(
    payload: dict[str, Any], legal_keys: Mapping[str, Sequence[str]], steps: list[str]
) -> dict[str, Any]:
    """Rename a wrong key **only** when the schema offers exactly one legal target."""
    result = dict(payload)
    for wrong, targets in legal_keys.items():
        if wrong not in result:
            continue
        if len(targets) != 1:
            continue  # ambiguous: needs judgement the engine does not have
        target = targets[0]
        if target in result:
            continue  # both present: not a rename, and merging would lose data
        result[target] = result.pop(wrong)
        steps.append(f"rename_key:{wrong}->{target}")
    return result


def _normalise_enums(
    payload: dict[str, Any], legal_enums: Mapping[str, Sequence[str]], steps: list[str]
) -> dict[str, Any]:
    """Map a near-miss enum value to the one legal member it can only mean."""
    result = dict(payload)
    for field_name, members in legal_enums.items():
        raw = result.get(field_name)
        if not isinstance(raw, str) or raw in members:
            continue
        needle = raw.strip().lower().replace("-", "_").replace(" ", "_")
        matches = [m for m in members if m.lower() == needle]
        if len(matches) == 1:
            result[field_name] = matches[0]
            steps.append(f"normalise_enum:{field_name}")
    return result


def _fill_optional_containers(
    payload: dict[str, Any], defaults: Mapping[str, Any], steps: list[str]
) -> dict[str, Any]:
    """Fill an absent OPTIONAL container with its declared empty default.

    Only containers with a *declared empty* default: filling a required field would invent
    content, which is exactly the failure mode this module exists to prevent.
    """
    result = dict(payload)
    for field_name, default in defaults.items():
        if field_name in result:
            continue
        if default not in ([], {}, ""):
            continue
        result[field_name] = json.loads(json.dumps(default))
        steps.append(f"fill_optional:{field_name}")
    return result


def plan_repair(
    *,
    code: LongNovelErrorCode,
    parent_payload_tokens: int,
    repair_input_budget: int,
    parent_splittable: bool,
) -> RepairPlan:
    """Decide what to do about a failed unit. Exactly three outcomes, no middle ground.

    Raises nothing: the caller needs the decision, and ``ESCALATE_AT_PARENT`` is a decision,
    not an exception. It becomes ``REPAIR_INPUT_OVER_BUDGET`` only when the caller acts on
    it and the parent turns out not to be splittable.
    """
    if code in LOCALLY_REPAIRABLE:
        return RepairPlan(
            decision=RepairDecision.ENGINE_LOCAL,
            code=code,
            reason="deterministically fixable from the schema plus the invalid output",
            repair_input_tokens=0,
            parent_splittable=parent_splittable,
        )

    if code in {
        LongNovelErrorCode.TRUNCATED_OUTPUT,
        LongNovelErrorCode.OUTPUT_LIMIT_EXCEEDED,
    }:
        return RepairPlan(
            decision=RepairDecision.ESCALATE_AT_PARENT,
            code=code,
            reason=(
                "the response did not fit the output ceiling; re-asking with the same shape "
                "would be cut off again, so the unit must get smaller"
            ),
            parent_splittable=parent_splittable,
        )

    appendix = C.REPAIR_SCHEMA_TOKENS + C.REPAIR_ERROR_TOKENS + C.REPAIR_INVALID_HEAD_TOKENS
    full_repair_tokens = parent_payload_tokens + appendix
    if full_repair_tokens <= repair_input_budget:
        return RepairPlan(
            decision=RepairDecision.FULL_PROVIDER_REPAIR,
            code=code,
            reason="full parent payload plus a bounded error appendix fits the budget",
            repair_input_tokens=full_repair_tokens,
            parent_splittable=parent_splittable,
        )

    # There is deliberately no reduced form here. Dropping the parent payload would ask the
    # model to reconstruct content it can no longer see.
    return RepairPlan(
        decision=RepairDecision.ESCALATE_AT_PARENT,
        code=LongNovelErrorCode.REPAIR_INPUT_OVER_BUDGET,
        reason=(
            f"full repair needs {full_repair_tokens} tokens but only {repair_input_budget} "
            "are available, and no reduced form exists: a model is never asked to rebuild a "
            "whole asset from a truncated head of it"
        ),
        repair_input_tokens=full_repair_tokens,
        parent_splittable=parent_splittable,
    )


def escalate(plan: RepairPlan, unit_kind: UnitKind) -> LongNovelError:
    """Turn an un-actionable escalation into the terminal error for this unit."""
    if plan.parent_splittable:
        raise AssertionError("a splittable parent must be split, not escalated to terminal")
    return LongNovelError(
        plan.code,
        f"{unit_kind.value}: {plan.reason}; parent is not splittable, so this unit is terminal",
        detail={"decision": plan.decision.value, "repair_input_tokens": plan.repair_input_tokens},
    )
