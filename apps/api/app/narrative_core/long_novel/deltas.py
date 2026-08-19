"""Profile deltas — what each axis value adds to the extraction (10_ADAPTIVE_PROFILE_LAYER §9).

A delta is **additive and nothing else**. It may ask the model for fields the core schema
does not carry; it may never remove a field, loosen a cap, or narrow what is extracted. That
is INV-P1, and it is enforced here by construction: a delta owns a list of field names and a
fragment of prompt text, and there is no mechanism for it to subtract anything.

**Additive in the schema is not additive in effect, and that is measured.** On 《一梦如初》 —
three blocks, temperature 0, each arm run twice so the noise floor was known — turning the
拆文 delta on returned FEWER items in 11 of the 12 fields both modes share, and more in none
(sign test p = 0.0005). Asking for two more things makes the model report less of everything
else.

It is not the output budget. The block was capped at 8 chapters by
``MAX_CHAPTERS_FOR_SIGNAL_FIDELITY`` while the budget afforded 24, and the responses ran about
3.5k tokens against 8k, so nothing was truncated and nothing was competing for room. Charging
the deltas against the budget was tried and reverted: it costs a 进阶流 book a shorter block
and more paid calls to fix a constraint that was never binding, and ``constants.py`` says in
as many words that the 0.80 utilisation margin exists to absorb this class of error.

So the effect is attention, not arithmetic, and nothing here fixes it. Two consequences worth
stating plainly: a 拆文 run's non-拆文 facts are thinner than the same book's diagnostic run
would produce, and an L1 pass made under one mode can never be reused for the other — the
saving would be paid for in coverage nobody would see go missing.

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
        "  一章只填一个；若该章切换过视角，填占篇幅更多的那个。**每一章都必须填，不要留空。**\n"
        '  形状：`"chapter_signals": [{"chapter_ref": 1, ..., "pov_entity": ""}]`'
    ),
)

POWER_BEATS = Delta(
    key="power_beats",
    trigger=("engine", "progression"),
    fields=("power_beats",),
    instruction=(
        "- **额外返回一个顶层数组** `power_beats`：主角（或其他重要人物）在实力/地位阶梯上的位置读数，"
        "以及推动它的那一下。每章最多 2 条，没有就不写。\n"
        "  `kind` 必须从这五个里选，**按这一处实际发生的事选**：\n"
        "  `promote`(在阶梯上往上走了一级) `gain`(得到手段、资源、靠山，位置未变但更强)\n"
        "  `faceslap`(压过此前压制自己的人) `setback`(受挫、被压制、失去依仗)\n"
        "  `demote`(在阶梯上往下掉了一级)。\n"
        "  `level` 填 `entity_ref` 这个人**自己当前所处**的等级/阶位，且必须是"
        "**正文里原样出现的名称**（例如「四阶」「大宗师」「三级演员」）。\n"
        "  **这一条最容易填错，看清楚**：正文写「获得四阶技能【审判庭】」，四阶是<技能>的阶，"
        "不是这个人的阶；正文写「击败二阶执法官」，二阶是<对手>的阶。"
        "这两种情况 `level` 一律**留空字符串**，只把事情写进 `why`。"
        "只有正文明确说明这个人本人处在某一阶时才填。\n"
        "  也**不要自己发明一套等级，不要套用别的小说的境界名**。\n"
        "  `why` 用 ≤20 字写清楚是什么事导致的。\n"
        "  注意 `setback` 和 `demote` 与上升同样重要：**一本书里如果一次下降都没有，通常是漏标了**。\n"
        '  形状：`"power_beats": [{"entity_ref": "", "chapter_ref": 1, "kind": "", '
        '"level": "", "why": "", "evidence": [{"paragraph_ref": 1}]}]`'
    ),
)

#: The 拆文 addition. Not a *profile* delta — no axis switches it on, the analysis mode does —
#: but the same shape and the same invariant: it may add fields, never remove or loosen one, so
#: a 拆文 run extracts everything a diagnostic run does and two things more.
#:
#: Both fields exist because L1 is the only layer that reads the prose. A whole-book unit can
#: decide which moments matter; it cannot quote a line it has never seen, and a breakdown whose
#: quotations are paraphrases is worse than one with none.
STORY_BREAKDOWN = Delta(
    key="story_breakdown",
    trigger=("mode", "story_breakdown"),
    fields=("end_hook_question", "standout_moments"),
    instruction=(
        "- 在每个 `chapter_signals` 条目里**额外加一个键** `end_hook_question`，"
        "填**这一章结尾留给读者的那个问题**，写成一句疑问句，≤30 字。\n"
        "  用这一章自己的说法，例如「他在书房要说的是什么？」「那笔钱到底进没进账？」。\n"
        "  **章末没有留问题就填空字符串，不要为了填满而编一个。**\n"
        '  形状：`"chapter_signals": [{"chapter_ref": 1, ..., "end_hook_question": ""}]`\n'
        "- **额外返回一个顶层数组** `standout_moments`：这一块里**最可能打动读者**的地方，"
        "每块最多 3 条，宁可少给。\n"
        "  `quote` 必须是**正文里原样出现的一句话**——照抄，一个字都不要改，"
        "不要合并两句，不要改标点。这一条会被逐字校验，改写过的会被丢弃。\n"
        "  优先选**有原话的**：一句台词、一句心理活动、一个具体动作的那一句。"
        "「两人和好了」这种概括不要选。\n"
        "  `why` 用 ≤50 字写**为什么这一处会打动人**——是身份倒转、是长期铺垫兑现、"
        "还是这个人第一次这样。写机制，不要写「很感人」「情绪强烈」。\n"
        '  形状：`"standout_moments": [{"chapter_ref": 1, "quote": "", "why": "", '
        '"evidence": [{"paragraph_ref": 1}]}]`'
        "——`quote` 可以是空串，`evidence` 不能空。"
    ),
)

#: Registered deltas. Adding one requires: the field on the asset contract, the prompt
#: fragment here, and a fixture in ``test_long_novel_document_sections.py`` (INV-P5).
DELTAS: tuple[Delta, ...] = (POV_ENTITY, POWER_BEATS, STORY_BREAKDOWN)


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

