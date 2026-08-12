"""``BudgetManager`` — joint output/input resolution and the unit policy table.

Two budgets share one context window, so they cannot be solved separately. A *larger*
output reserve leaves *less* room for input, and on a 32K provider that can push a block
below the minimum viable size: at ``O = 8000`` Qwen admits only three chapters, which is
under the floor. Taking ``min(caps)`` — the obvious approach — therefore produces plans that
are individually reasonable and jointly infeasible. :func:`joint_resolve` searches the
candidate space instead, and prefers **fidelity first**: the highest density profile that
still yields a viable block, then the largest block, then the largest output budget.

Everything here happens at plan time, before any spend. ``OUTPUT_BUDGET_TOO_LOW`` costs
nothing; discovering the same fact after 90 % of a book has been paid for costs everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel.contracts.density import (
    PROFILES,
    DensityProfile,
    DensityProfileName,
    max_chapters_per_block,
)
from app.narrative_core.long_novel.contracts.enums import UnitKind
from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode

__all__ = [
    "UnitPolicy",
    "UNIT_POLICY",
    "ContextCosts",
    "BudgetResolution",
    "joint_resolve",
    "effective_raw_text_budget",
    "BudgetManager",
]


@dataclass(frozen=True)
class UnitPolicy:
    """Output target and behaviour for one unit kind (05 §2 is the normative owner).

    ``splittable`` is the difference between a recoverable over-budget unit and a terminal
    one: only a block can be cut into smaller pieces and retried, which is why every
    escalation path ends at a block or ends the run.
    """

    unit_kind: UnitKind
    output_target: int
    output_floor: int
    splittable: bool
    input_budget_ceiling: int | None


UNIT_POLICY: dict[UnitKind, UnitPolicy] = {
    UnitKind.BLOCK: UnitPolicy(
        unit_kind=UnitKind.BLOCK,
        output_target=8_000,
        output_floor=C.OUTPUT_FLOOR_BLOCK_EXTRACTION,
        splittable=True,
        input_budget_ceiling=None,  # derived per block from the moving anchor bound
    ),
    UnitKind.STAGE: UnitPolicy(
        unit_kind=UnitKind.STAGE,
        output_target=1_500,
        output_floor=800,
        splittable=False,
        input_budget_ceiling=C.STAGE_INPUT_MAX_TOKENS,
    ),
    UnitKind.TOPIC: UnitPolicy(
        unit_kind=UnitKind.TOPIC,
        output_target=6_000,
        output_floor=2_000,
        splittable=False,
        input_budget_ceiling=None,  # per (topic, provider); see the projection planners
    ),
    UnitKind.ASSESSMENT: UnitPolicy(
        unit_kind=UnitKind.ASSESSMENT,
        output_target=6_000,
        output_floor=2_000,
        splittable=False,
        input_budget_ceiling=C.ASSESSMENT_INPUT_MAX_TOKENS,
    ),
    UnitKind.FINAL: UnitPolicy(
        unit_kind=UnitKind.FINAL,
        output_target=4_000,
        output_floor=1_500,
        splittable=False,
        input_budget_ceiling=C.FINAL_INPUT_MAX_TOKENS,
    ),
}


@dataclass(frozen=True)
class ContextCosts:
    """Every non-text consumer of the context window, measured at build time.

    All of them are listed because the original derivation omitted two — the paragraph
    anchor cost and the provider message envelope — and an omitted term does not stop
    consuming context, it just stops being planned for.
    """

    system_prompt_tokens: int
    prompt_frame_tokens: int
    schema_tokens: int
    provider_envelope_tokens: int

    def fixed_total(self) -> int:
        return (
            self.system_prompt_tokens
            + self.prompt_frame_tokens
            + self.schema_tokens
            + self.provider_envelope_tokens
        )


@dataclass(frozen=True)
class BudgetResolution:
    """The resolved plan for one run. Pinned at run creation and carried in ``SCI``."""

    output_budget: int
    density_profile: DensityProfileName
    chapters_per_block: int
    max_chapters_by_output: int
    max_chapters_by_input: int
    max_chapters_by_retry_unit: int
    provider_max_output_tokens: int
    provider_max_output_tokens_source: str
    context_window: int
    safety_margin: int


def safety_margin(context_window: int) -> int:
    """``max(2000, 5 % of the window)`` — SAFETY GUARD.

    A flat margin is too tight on a large window and too wasteful on a small one.
    """
    return max(2_000, -(-context_window // 20))


def effective_raw_text_budget(
    *,
    context_window: int,
    output_budget: int,
    costs: ContextCosts,
    carry_forward_max_tokens: int,
    n_paragraphs: int,
) -> int:
    """The only budget raw novel text may consume, for a block of ``n_paragraphs``.

    ``E_anch`` grows with the block, so this bound *moves* as chapters are admitted. That is
    why block planning is a monotone accumulation against a recomputed bound rather than a
    division: a fixed bound silently overshoots on paragraph-dense chapters.
    """
    return (
        context_window
        - output_budget
        - costs.fixed_total()
        - carry_forward_max_tokens
        - safety_margin(context_window)
        - n_paragraphs * C.ANCHOR_TOKENS
    )


def max_chapters_by_input(
    *,
    context_window: int,
    output_budget: int,
    costs: ContextCosts,
    carry_forward_max_tokens: int,
    mean_chapter_tokens: int,
    mean_paragraphs_per_chapter: int,
) -> int:
    """Planning-time estimate of how many mean chapters fit the *input* side.

    An estimate by construction — it uses book means, while the real planner accumulates
    actual chapters against the moving bound. It exists so the joint search can reject a
    candidate that is input-infeasible before any block is built, not to replace the
    accumulation.
    """
    per_chapter = mean_chapter_tokens + mean_paragraphs_per_chapter * C.ANCHOR_TOKENS
    if per_chapter <= 0:
        raise ValueError("mean chapter cost must be positive")
    room = (
        context_window
        - output_budget
        - costs.fixed_total()
        - carry_forward_max_tokens
        - safety_margin(context_window)
    )
    if room <= 0:
        return 0
    return room // per_chapter


def joint_resolve(
    *,
    context_window: int,
    provider_max_output_tokens: int,
    provider_max_output_tokens_source: str,
    costs: ContextCosts,
    mean_chapter_tokens: int,
    mean_paragraphs_per_chapter: int,
    user_output_cap: int | None = None,
    consent_output_cap: int | None = None,
    output_ladder: Sequence[int] = C.OUTPUT_LADDER,
    profiles: Iterable[DensityProfile] = tuple(PROFILES.values()),
) -> BudgetResolution:
    """Search ``(O, density_profile)`` jointly and return the fidelity-best feasible plan.

    Raises ``OUTPUT_BUDGET_TOO_LOW`` when nothing is feasible — at plan time, with no spend.
    That is the honest outcome: continuing would mean either blocks too small to be worth
    their per-call overhead, or assets that truncate after they are paid for.
    """
    ceiling = min(
        v
        for v in (provider_max_output_tokens, user_output_cap, consent_output_cap)
        if v is not None and v > 0
    )
    candidates = [o for o in output_ladder if o <= ceiling]

    feasible: list[tuple[tuple[int, int, int], BudgetResolution]] = []
    for output_budget in candidates:
        for profile in profiles:
            by_output = max_chapters_per_block(profile, output_budget)
            by_input = max_chapters_by_input(
                context_window=context_window,
                output_budget=output_budget,
                costs=costs,
                carry_forward_max_tokens=profile.carry_forward_max_tokens,
                mean_chapter_tokens=mean_chapter_tokens,
                mean_paragraphs_per_chapter=mean_paragraphs_per_chapter,
            )
            # HARD_BLOCK_TOKENS is an absolute ceiling on the raw text in one block, and
            # it binds only once the provider's real output ceiling is high enough to allow
            # large blocks — which is exactly when it matters. The block is the retry unit:
            # a block that fails costs its whole input again, so an unbounded one turns a
            # single bad response into the most expensive event in the run.
            by_retry_unit = C.HARD_BLOCK_TOKENS // max(1, mean_chapter_tokens)
            # Per-chapter fidelity has a lower ceiling than schema validity. A block of 19
            # chapters returns a valid asset whose per-chapter counters are zero, and that
            # emptiness is invisible until it reaches a chart. Costing more calls is the
            # price of the signals every upper layer is built on.
            chapters = min(by_output, by_input, by_retry_unit, C.MAX_CHAPTERS_FOR_SIGNAL_FIDELITY)
            if chapters < C.MIN_VIABLE_CHAPTERS_PER_BLOCK:
                continue
            feasible.append(
                (
                    # fidelity first, then block size, then output headroom
                    (profile.density_rank, chapters, output_budget),
                    BudgetResolution(
                        output_budget=output_budget,
                        density_profile=profile.name,
                        chapters_per_block=chapters,
                        max_chapters_by_output=by_output,
                        max_chapters_by_input=by_input,
                        max_chapters_by_retry_unit=by_retry_unit,
                        provider_max_output_tokens=provider_max_output_tokens,
                        provider_max_output_tokens_source=provider_max_output_tokens_source,
                        context_window=context_window,
                        safety_margin=safety_margin(context_window),
                    ),
                )
            )

    if not feasible:
        raise LongNovelError(
            LongNovelErrorCode.OUTPUT_BUDGET_TOO_LOW,
            (
                "no (output budget, density profile) pair yields at least "
                f"{C.MIN_VIABLE_CHAPTERS_PER_BLOCK} chapters per block within a "
                f"{context_window}-token context and a {ceiling}-token output ceiling"
            ),
            detail={
                "context_window": context_window,
                "output_ceiling": ceiling,
                "provider_max_output_tokens": provider_max_output_tokens,
                "provider_max_output_tokens_source": provider_max_output_tokens_source,
                "candidates_considered": candidates,
            },
        )

    feasible.sort(key=lambda item: item[0], reverse=True)
    return feasible[0][1]


class BudgetManager:
    """Facade over the resolution above, plus the per-unit policy lookups."""

    def __init__(self, policy: dict[UnitKind, UnitPolicy] | None = None) -> None:
        self._policy = dict(policy or UNIT_POLICY)

    def policy_for(self, unit_kind: UnitKind) -> UnitPolicy:
        try:
            return self._policy[unit_kind]
        except KeyError:
            # Every provider unit must have a planner; a unit without one would be the
            # single exception that makes "every provider input is bounded" false.
            raise LongNovelError(
                LongNovelErrorCode.PLAN_NOT_FEASIBLE,
                f"no unit policy declared for {unit_kind.value}",
            ) from None

    def resolve(self, **kwargs: object) -> BudgetResolution:
        return joint_resolve(**kwargs)  # type: ignore[arg-type]

    def preflight(
        self, unit_kind: UnitKind, assembled_input_tokens: int, output_reserve: int, context_window: int
    ) -> None:
        """Assert a unit fits *before* the request is sent (INV-18).

        The check is here rather than at the transport layer because the point is to never
        send the request, not to notice afterwards that it was too big.
        """
        limit = context_window - safety_margin(context_window)
        if assembled_input_tokens + output_reserve > limit:
            code = (
                LongNovelErrorCode.STAGE_INPUT_OVER_BUDGET
                if unit_kind is UnitKind.STAGE
                else LongNovelErrorCode.PROJECTION_OVER_BUDGET
            )
            raise LongNovelError(
                code,
                (
                    f"{unit_kind.value} would send {assembled_input_tokens} input + "
                    f"{output_reserve} reserved output tokens, over the {limit}-token limit"
                ),
                detail={
                    "unit_kind": unit_kind.value,
                    "assembled_input_tokens": assembled_input_tokens,
                    "output_reserve": output_reserve,
                    "limit": limit,
                },
            )
