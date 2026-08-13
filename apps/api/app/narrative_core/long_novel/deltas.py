"""Profile deltas — what each axis value adds to the extraction (10_ADAPTIVE_PROFILE_LAYER §9).

A delta is **additive and nothing else**. It may ask the model for fields the core schema
does not carry; it may never remove a field, loosen a cap, or narrow what is extracted. That
is INV-P1, and it is enforced here by construction: a delta owns a list of field names and a
fragment of prompt text, and there is no mechanism for it to subtract anything.

The invariant exists because a wrong profile that *removes* a signal fails silently. Nothing
downstream can distinguish "this book has no relationship beats" from "we stopped counting
them" — and a measured instance of that failure is on record: when 87% of chapter signal
counters came back zero, the assessor read the gap as an authorial flaw and graded the book
`chapter_efficiency: D`.

Only the deltas that are implemented and tested are registered. The rest of §9 is specified
but not built, and a registry entry pointing at a prompt fragment nobody has run would be a
promise the engine cannot keep — the two extraction fields that shipped broken (all-zero
counters, all-"advance" action kinds) were both paths nothing had exercised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

__all__ = ["Delta", "DELTAS", "deltas_for", "delta_prompt", "delta_fields"]


@dataclass(frozen=True)
class Delta:
    """One profile-driven addition to the L1 extraction."""

    key: str
    #: The axis value that switches it on, as ``(axis, value)``.
    trigger: tuple[str, str]
    #: Field names this delta adds to the block asset. Recorded so a test can assert that the
    #: core schema is unchanged when the delta is off.
    fields: tuple[str, ...]
    #: Appended to the L1 field descriptions. Written to the same rules the core prompt
    #: learned the hard way: say what the value *is*, say where it comes from, and never let
    #: the schema example double as a plausible answer.
    instruction: str


POV_ENTITY = Delta(
    key="pov_entity",
    trigger=("pov", "ensemble"),
    fields=("pov_entity",),
    instruction=(
        "- 在每个 `chapter_signals` 条目里**额外加一个键** `pov_entity`，"
        "填**这一章是通过谁的视角叙述的**，取值必须是该章正文里原样出现的人物称呼。\n"
        "  一章只填一个；若该章切换过视角，填占篇幅更多的那个。**每一章都必须填，不要留空。**"
    ),
)

#: Registered deltas. Adding one requires: the field on the asset contract, the prompt
#: fragment here, and a fixture in ``test_long_novel_document_sections.py`` (INV-P5).
DELTAS: tuple[Delta, ...] = (POV_ENTITY,)


def deltas_for(axes: Mapping[str, Mapping[str, str]] | Mapping[str, str]) -> tuple[Delta, ...]:
    """Which deltas a confirmed profile switches on.

    Accepts either the stored shape (``{"pov": {"value": "ensemble", ...}}``) or a plain
    mapping of axis to value, so a caller holding one does not have to reshape it.
    """
    resolved: dict[str, str] = {}
    for axis, value in (axes or {}).items():
        resolved[axis] = value.get("value", "") if isinstance(value, Mapping) else str(value)
    return tuple(
        delta for delta in DELTAS if resolved.get(delta.trigger[0]) == delta.trigger[1]
    )


def delta_fields(deltas: Sequence[Delta]) -> tuple[str, ...]:
    """Every field the active deltas add. Empty when no delta is active."""
    return tuple(field for delta in deltas for field in delta.fields)


def delta_prompt(deltas: Sequence[Delta]) -> str:
    """The prompt fragment for the active deltas, or an empty string.

    Empty is the important case: with no delta active the extraction prompt must be byte
    identical to the core one, or every book pays for a profile it does not use — and the
    prompt hash, which gates extraction reuse, would change for no reason.
    """
    if not deltas:
        return ""
    return "\n" + "\n".join(delta.instruction for delta in deltas)
