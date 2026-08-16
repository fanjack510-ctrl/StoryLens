"""Formal run → LongNovelAnalysisEngine, for books whose profile has been confirmed.

Until this existed, nothing in the product called ``RunCoordinator``: pressing 重新分析 V2
ran the hierarchical window engine, and every result produced by the long-novel engine had
been inserted by hand. This is the wire.

**Which engine a run gets is decided by the book's profile, not by a hidden flag.** A book
whose five axes have been confirmed goes through here; a book without one keeps the old path.
That is the rule the design already states — the profile is a prerequisite for the engine
(10_ADAPTIVE_PROFILE_LAYER §4.0) — and it has the property a flag does not: the user can see
why a given book took a given path, and can change it.

The document this produces is the same ``WholeBookAnalysisV2`` the UI already renders, saved
through the same repository, so nothing downstream distinguishes the two engines except the
``pipeline_version`` stamp and the sections the old engine could not fill.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Book, WholeBookRun
from app.model_gateway.base import ModelRequest
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel.budget import ContextCosts, joint_resolve
from app.narrative_core.long_novel.contracts.density import profile as density_profile
from app.narrative_core.long_novel.deltas import delta_prompt, deltas_for
from app.narrative_core.long_novel.extractor import BlockExtractor
from app.narrative_core.long_novel.orchestrator import RunCoordinator
from app.narrative_core.long_novel.planner import BlockPlanner
from app.narrative_core.long_novel.profile_repository import BookProfileRepository
from app.narrative_core.long_novel.chapter_focus import hook_vocabulary
from app.narrative_core.long_novel.prompts import (
    CAST_FUNCTION_INSTRUCTION,
    FINAL_INSTRUCTION,
    FOUR_BEATS_INSTRUCTION,
    REUSABLE_INSTRUCTION,
    STAGE_INSTRUCTION,
    SYSTEM_PROMPT,
    TOPIC_INSTRUCTION,
    build_assessment_instruction,
    build_standout_prompt,
    build_reversal_prompt,
    build_suspense_pairing_prompt,
    build_user_prompt,
    prompt_template_hash,
)
from app.narrative_core.long_novel.snapshot_source import load_chapters, to_planned_chapters
from app.narrative_core.services.whole_book_gateway_transport_v1 import _run_async
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1
from app.narrative_core.whole_book_v2.contracts import ProgressV2, WholeBookAnalysisV2
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository, pinned_provider

logger = logging.getLogger(__name__)

ENGINE_ID = "long_novel_engine"
ENGINE_VERSION = "long-novel-engine-1.0"

#: Context accounting for the planner. These are the shares the block planner reserves for
#: system prompt, schema, carry slate and repair headroom.
_COSTS = ContextCosts(3000, 1200, 1800, 400)
_CONTEXT_WINDOW = 128_000
_PROVIDER_MAX_OUTPUT = 32_768
#: Character cap on a synthesis unit's JSON payload. Sized off the largest declared unit budget
#: at roughly two characters per token; the old flat 12,000 was under it and sat close enough to
#: the real payloads that growing any projection would have started cutting them mid-value.
_UNIT_PAYLOAD_MAX_CHARS = C.FINAL_INPUT_MAX_TOKENS * 2


class _GatewayProvider:
    """The gateway, shaped the way ``BlockExtractor`` and the L2–L4 units expect.

    Two entry points because the engine asks for two different things: ``complete`` is the
    block extraction, whose prompt the engine assembles and whose raw text it parses itself;
    ``json_unit`` is every bounded synthesis call above it.

    Usage is recorded per call through the same ledger the hierarchical engine uses, so a run
    on this path is billed and displayed identically. A call that has been made is a call that
    has been paid for, so it is recorded before the caller has a chance to fail.
    """

    def __init__(
        self,
        gateway: Any,
        *,
        provider_name: str,
        model_name: str,
        density: Any,
        delta_instructions: str,
        session: Session | None = None,
        run_id: int = 0,
        repository: Any | None = None,
        on_call: Callable[[int, str], None] | None = None,
    ) -> None:
        self._on_call = on_call
        self._gateway = gateway
        self._provider_name = provider_name
        self._model_name = model_name
        self._density = density
        self._delta_instructions = delta_instructions
        self._session = session
        self._run_id = int(run_id)
        self._repository = repository
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def _send(self, unit_key: str, prompt: str, max_output_tokens: int) -> Any:
        response = _run_async(
            self._gateway.generate(
                self._provider_name,
                ModelRequest(
                    model=self._model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_output_tokens=max_output_tokens,
                    response_format_mode="json_object",
                    enable_thinking=False,
                ),
            )
        )
        self.calls += 1
        self.input_tokens += int(getattr(response, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(response, "output_tokens", 0) or 0)
        if self._session is not None and self._run_id:
            from app.narrative_core.whole_book_v2.usage_ledger import record_provider_call

            record_provider_call(
                self._session,
                whole_book_run_id=self._run_id,
                unit_key=unit_key,
                provider=self._provider_name,
                model=self._model_name,
                response=response,
                repair=unit_key.endswith(":repair"),
            )
            if self._repository is not None and hasattr(self._repository, "commit_usage"):
                self._repository.commit_usage()
        # Progress is emitted per *completed provider call* and nowhere else. A percentage
        # driven by stage transitions moves in jumps and then sits still for the twenty
        # minutes that extraction actually takes; a percentage driven by paid calls is the
        # one number that cannot claim work that did not happen.
        if self._on_call is not None:
            try:
                self._on_call(self.calls, unit_key)
            except Exception:  # noqa: BLE001 — reporting must never fail the run
                logger.warning("long_novel_progress_write_failed run_id=%s", self._run_id)
        return response

    # ------------------------------------------------------------------ L1
    def complete(self, *, payload: dict[str, Any], max_output_tokens: int, repair_note: str | None = None):
        prompt = build_user_prompt(
            rendered_text=payload["text"],
            profile=self._density,
            delta_instructions=self._delta_instructions,
            carry_in_summary=str(payload.get("carry_summary", "")),
        )
        if repair_note:
            prompt += "\n\n" + repair_note
        response = self._send("block:repair" if repair_note else "block", prompt, max_output_tokens)
        return (
            str(getattr(response, "text", "") or ""),
            str(getattr(response, "finish_reason", "") or ""),
            int(getattr(response, "output_tokens", 0) or 0),
        )

    # ------------------------------------------------------------- L2 – L4
    def json_unit(
        self, label: str, instruction: str, payload: Any, prompt: str | None = None
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False)
        if len(body) > _UNIT_PAYLOAD_MAX_CHARS:
            # Logged rather than trimmed in silence: a payload over the cap means a projection
            # upstream stopped being bounded, and the symptom — a model reading a blob that
            # stops in the middle of a value — does not look like a budget problem from here.
            logger.warning(
                "long_novel_unit_payload_over_cap run_id=%s label=%s chars=%s cap=%s",
                self._run_id, label, len(body), _UNIT_PAYLOAD_MAX_CHARS,
            )
            body = body[:_UNIT_PAYLOAD_MAX_CHARS]
        message = prompt or (instruction + "\n\n只输出 JSON。\n\n输入：\n" + body)
        response = self._send(label, message, 4000)
        body = str(getattr(response, "text", "") or "").strip()
        if body.startswith("```"):
            body = body.split("```")[1].lstrip("json").strip()
        try:
            parsed = json.loads(body)
        except (ValueError, IndexError):
            # A malformed synthesis unit costs that section, not the run. The section is then
            # marked unavailable downstream, which is the honest outcome — the alternative,
            # substituting plausible text, is the failure this engine exists to end.
            logger.warning("long_novel_unit_unparsable run_id=%s label=%s", self._run_id, label)
            return {}
        return parsed if isinstance(parsed, dict) else {}


#: The long-novel engine's phases, named in the vocabulary the progress UI already knows.
#: Inventing new stage codes would mean the client had no label for them, and an unlabelled
#: stage reads to a user as a stalled one.
_STAGE_PLAN = "plan_windows"
_STAGE_EXTRACT = "extract_windows"
_STAGE_SYNTHESIS = "generate_overview"


def _progress_writer(
    repo: Any,
    *,
    run_id: int,
    total_blocks: int,
    expected_calls: int,
    total_chapters: int,
    chapters_per_block: int,
    provider_name: str,
    model_name: str,
    started_at: float,
    tokens: Callable[[], tuple[int, int]],
    commit: Callable[[], None],
) -> Callable[[int, str], None]:
    """Build the per-call progress callback.

    The estimate of what remains is extrapolated from the calls already made rather than from
    a fixed per-call guess: this engine's blocks are uniform, so the mean of what has actually
    happened is a better predictor than anything decided before the run started.
    """

    def write(calls_done: int, unit_key: str) -> None:
        blocks_done = min(total_blocks, calls_done) if unit_key.startswith("block") else total_blocks
        extracting = unit_key.startswith("block")
        stage = _STAGE_EXTRACT if extracting else _STAGE_SYNTHESIS
        ratio = min(1.0, calls_done / max(1, expected_calls))
        elapsed = max(0.0, time.monotonic() - started_at)
        per_call = elapsed / max(1, calls_done)
        input_tokens, output_tokens = tokens()
        repo.save_progress(
            run_id,
            ProgressV2(
                overall_percent=round(min(99.0, 3.0 + 94.0 * ratio), 2),
                current_stage=stage,
                stage_percent=round(100.0 * (blocks_done / max(1, total_blocks) if extracting else ratio), 2),
                current_window=blocks_done,
                total_windows=total_blocks,
                current_chapter=min(total_chapters, blocks_done * max(1, chapters_per_block)),
                total_chapters=total_chapters,
                provider_calls_completed=calls_done,
                provider_calls_estimated=expected_calls,
                successful_calls=calls_done,
                failed_calls=0,
                retry_calls=0,
                repair_calls=0,
                elapsed_seconds=int(elapsed),
                estimated_remaining_seconds=int(per_call * max(0, expected_calls - calls_done)),
                estimated_cost=0.0,
                # Priced from tokens actually returned, so the number a user watches is spend
                # already incurred rather than a forecast.
                estimated_actual_cost=round(input_tokens / 1e6 + output_tokens / 1e6 * 2, 4),
                provider=provider_name,
                model=model_name,
                last_completed_action=(
                    f"已抽取 {blocks_done}/{total_blocks} 块" if extracting else f"已完成 {unit_key}"
                ),
                current_action=("正在抽取分块事实" if extracting else "正在合成全书结论"),
                last_activity_at=datetime.now(timezone.utc),
            ),
        )
        commit()

    return write


def _one_based(chapters: list[Any]) -> list[Any]:
    """Shift a 0-based snapshot onto 1-based chapter numbers.

    Some snapshots number chapters from 0. Every chapter reference in the engine is declared
    ``ge=1``, so a 0-based book fails validation on **every** block and the run finishes
    reporting zero chapters — which is what happened the first time this pipeline was run.
    The hierarchical path has carried the same shift for the same reason; this is not a
    special case, it is the snapshot format being two things.
    """
    if not chapters or min(c.chapter_order for c in chapters) >= 1:
        return chapters
    from dataclasses import replace

    return [replace(c, chapter_order=c.chapter_order + 1) for c in chapters]


#: Token model fitted to three complete runs, every figure read from the usage ledger rather
#: than forecast. Repair attempts are excluded from every figure, because the estimate is of a
#: run that goes right and a repair is by definition unplanned:
#:
#:   《深海余烬》 806 章 / 2,402,385 字 → 114 calls (99 block + 15 unit), 1,885,739 in, 281,485 out
#:   《凶宅笔记》 277 章 /   797,953 字 →  46 calls (35 block + 11 unit),   671,493 in, 104,393 out
#:   《系统豪横》  84 章 /   195,269 字 →  24 calls (11 block + 13 unit),   210,225 in,  44,524 out
#:
#: A call is one of two things and they cost differently, so the model counts them separately.
#: A **block call** carries a slice of the book plus the extraction contract and returns a whole
#: block asset; a **bounded unit** — stage interpretation, topic projection, assessment, final
#: synthesis, reversal detection, thread pairing — carries digests and returns a short JSON
#: object. The earlier model had one blended rate per call, which held only while blocks
#: dominated: 87% of 《深海余烬》's calls are blocks against 46% of 《系统豪横》's, and on the
#: short book the blended rate over-charged output by 25% and priced each stage interpretation
#: at six times what one costs.
#:
#: Input: the two shorter books fit ``_TOKENS_PER_CHAR`` and the block overhead off their
#: differing chapters-per-block, which makes 《深海余烬》 validation rather than interpolation —
#: it lands 3.4% high. Output agrees within 8% across all three and no tighter, because the same
#: book run twice over the same text returned 2,882 and then 3,323 output tokens per block. That
#: 15% is the provider's, and an estimate cannot be more precise than the thing it estimates.
_TOKENS_PER_CHAR = 0.4687
_INPUT_TOKENS_PER_BLOCK_CALL = 7385
_INPUT_TOKENS_PER_UNIT_CALL = 2920
_OUTPUT_TOKENS_PER_BLOCK_CALL = 2959
_OUTPUT_TOKENS_PER_UNIT_CALL = 613


def estimate_tokens(*, character_count: int, blocks: int, units: int) -> tuple[int, int]:
    """``(input, output)`` for a run of this shape. Separated from the plan so it can be
    checked against a measured run's *actual* call mix rather than against a re-planned one.

    Without that separation the fit could not be tested at all once the planner changed: the
    call mix moves, the totals move with it, and a test comparing a new plan's estimate to an
    old run's ledger fails without either the model or the run being wrong.
    """
    return (
        round(character_count * _TOKENS_PER_CHAR
              + blocks * _INPUT_TOKENS_PER_BLOCK_CALL
              + units * _INPUT_TOKENS_PER_UNIT_CALL),
        round(blocks * _OUTPUT_TOKENS_PER_BLOCK_CALL + units * _OUTPUT_TOKENS_PER_UNIT_CALL),
    )

#: Provider calls above L1 besides the per-stage interpretations: the four provider-backed
#: topic projections, then assessment, final synthesis, reversal detection and thread pairing.
#: ``len(Topic)`` was standing in for the topic count and includes ``chapters``, which is a
#: deterministic local merge and has never cost a call.
_UNITS_BESIDES_STAGES = C.TOPIC_PROVIDER_CALLS_BEFORE_ASSESSMENT + 4
#: 拆文's units above the stage interpretations: 起承转合, 爆点选择, 配角功能, 可复用点.
_BREAKDOWN_UNITS = 4


def estimate_long_novel_plan(*, chapter_count: int, character_count: int) -> dict[str, int]:
    """How many blocks and calls this engine will actually make.

    The prepare panel priced a run that was not going to happen: it reported the hierarchical
    planner's 12 windows / 30 calls for a book this engine analyses in 101 blocks and 114
    calls. The *token* total was close, because both engines read the book once — which is why
    the mistake survived a real run without the cost being far out — but the counts a user
    reads to judge duration and risk were wrong by 4x.

    Deliberately derived from the same ``joint_resolve`` the run itself uses, so the number
    shown and the number spent cannot drift apart.
    """
    chapters = max(1, int(chapter_count))
    # ~1.6 characters per token for Chinese prose, the same ratio the planner assumes.
    mean_chapter_tokens = max(1, int(character_count / chapters / 1.6)) if character_count else 1200
    resolved = joint_resolve(
        context_window=_CONTEXT_WINDOW,
        provider_max_output_tokens=_PROVIDER_MAX_OUTPUT,
        provider_max_output_tokens_source="probed",
        costs=_COSTS,
        mean_chapter_tokens=mean_chapter_tokens,
        mean_paragraphs_per_chapter=30,
    )
    per_block = max(1, resolved.chapters_per_block)
    blocks = (chapters + per_block - 1) // per_block
    # Stage interpretations scale with the book; the rest are the fixed bounded units. Taken
    # from the planner's own arithmetic rather than a second formula — ``blocks // 16`` was a
    # third opinion on the stage count, and it under-reported every book short enough for the
    # partition floor to apply.
    stages = BlockPlanner.stage_count(BlockPlanner.partition_count(blocks))
    units = stages + _UNITS_BESIDES_STAGES
    input_tokens, output_tokens = estimate_tokens(
        character_count=character_count, blocks=blocks, units=units
    )
    return {
        "blocks": blocks,
        "chapters_per_block": per_block,
        "estimated_provider_calls": blocks + units,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
    }


def profile_confirmation_state(session: Session, book_id: int) -> str:
    """"confirmed" | "draft" | "none" — what the analysis gates dispatch on.

    Both analysis entries (single-chapter and whole-book) hard-gate on "confirmed"
    (10_ADAPTIVE_PROFILE_LAYER §4.3: the confirmation gate sits before the FIRST analysis,
    whichever pipeline it is — otherwise a user who only ever runs chapter analysis never
    reaches it). Reads defensively: an unreadable profile store reports "none" and the
    gate's message sends the user to the profile page, which can repair it.
    """
    try:
        stored = BookProfileRepository(session).get(int(book_id))
    except Exception:  # noqa: BLE001 — unreadable profile = no profile
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return "none"
    if not stored:
        return "none"
    return "confirmed" if stored.get("confirmed_at") else "draft"


def book_uses_long_novel_engine(session: Session, book_id: int) -> bool:
    """Does this book have a confirmed profile, and therefore take the new engine?

    A draft is not enough. An inferred profile can be wrong, and the axes dispatch extraction
    deltas that cost money and change the report's shape — INV-P2 says human confirmation
    outranks inference, so an unconfirmed book stays on the path it is already on.

    A confirmed profile is necessary but not sufficient: the engine plans in blocks of at
    least ``MIN_VIABLE_CHAPTERS_PER_BLOCK`` chapters, so a book whose chapters never got
    detected (one "chapter" holding the whole file) cannot be planned at all. Measured on
    《剩女遇见爱情》: 1 detected chapter, confirmed profile — the planner raised
    OUTPUT_BUDGET_TOO_LOW and 500'd the whole-book page before it could render. Such a book
    keeps the old engine, which has no block floor.
    """
    stored = BookProfileRepository(session).get(int(book_id))
    if not (stored and stored.get("confirmed_at")):
        return False
    chapters = session.execute(
        text(
            "SELECT chapter_count FROM book_snapshots WHERE book_id = :book_id "
            "AND snapshot_status = 'completed' ORDER BY id DESC LIMIT 1"
        ),
        {"book_id": int(book_id)},
    ).scalar()
    if chapters is None:
        chapters = session.execute(
            text("SELECT COUNT(*) FROM chapters WHERE book_id = :book_id"),
            {"book_id": int(book_id)},
        ).scalar()
    return int(chapters or 0) >= C.MIN_VIABLE_CHAPTERS_PER_BLOCK


#: What the run is reading *for*. ``story_breakdown`` is 拆文 — the same book, read to learn
#: from rather than to find fault in (docs/whole-book/STORY_BREAKDOWN_DESIGN). It is not a
#: second engine: same planner, same extraction, different units above L1.
ANALYSIS_MODES = ("diagnostic", "story_breakdown")


def execute_long_novel_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    use_fake_gateway: Any | None = None,
    commit_progress: bool = False,
    mode: str = "diagnostic",
) -> dict[str, Any]:
    """Run the long-novel engine for an existing ``WholeBookRun`` and persist the result."""
    if mode not in ANALYSIS_MODES:
        raise ValueError(f"unknown analysis mode: {mode}")
    breakdown = mode == "story_breakdown"
    run = get_run(session, int(run_id))
    book = session.get(Book, int(run.book_id))
    if book is None:
        raise ValueError(f"book not found: {run.book_id}")
    if run.snapshot_id is None:
        raise ValueError("whole-book run missing snapshot_id")
    provider_name, model_name = pinned_provider(session, int(run_id))

    def _persist_commit() -> None:
        if commit_progress:
            session.commit()

    repo = WholeBookV2Repository(session, on_persist=_persist_commit if commit_progress else None)
    chapters, stats = load_chapters(session, int(run.snapshot_id))
    chapters = _one_based(chapters)
    planned = to_planned_chapters(chapters)
    resolved = joint_resolve(
        context_window=_CONTEXT_WINDOW,
        provider_max_output_tokens=_PROVIDER_MAX_OUTPUT,
        provider_max_output_tokens_source="probed",
        costs=_COSTS,
        mean_chapter_tokens=sum(p.text_tokens for p in planned) // max(1, len(planned)),
        mean_paragraphs_per_chapter=max(1, sum(p.n_paragraphs for p in planned) // max(1, len(planned))),
    )
    density = density_profile(resolved.density_profile)
    plan = BlockPlanner(
        profile=density,
        output_budget=resolved.output_budget,
        context_window=_CONTEXT_WINDOW,
        costs=_COSTS,
    ).plan(planned)

    stored = BookProfileRepository(session).get(int(run.book_id)) or {}
    axes = stored.get("axes") or {}
    # The 拆文 addition rides the same delta mechanism as the profile axes, keyed on a
    # pseudo-axis the mode sets. One extraction prompt, assembled one way, whichever reading
    # the run is doing — which is what lets the two modes ever share an L1 pass.
    deltas = deltas_for({**axes, "mode": mode} if mode else axes)
    instructions = delta_prompt(deltas)
    logger.info(
        "long_novel_run_start run_id=%s mode=%s chapters=%s blocks=%s deltas=%s",
        run_id, mode or "diagnostic", stats.chapter_count, len(plan.blocks),
        [d.key for d in deltas],
    )

    if use_fake_gateway is not None:
        gateway = use_fake_gateway
    else:
        from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
            _bind_formal_gateway,
        )

        gateway = _bind_formal_gateway(session, provider_name=provider_name)

    # One call per block, plus the bounded units above it: stage interpretations, then either
    # the diagnostic's thirteen or 拆文's four.
    expected_calls = len(plan.blocks) + len(plan.stages) + (
        _BREAKDOWN_UNITS if breakdown else _UNITS_BESIDES_STAGES
    )
    provider = _GatewayProvider(
        gateway,
        provider_name=provider_name,
        model_name=model_name,
        density=density,
        delta_instructions=instructions,
        session=session,
        run_id=int(run_id),
        repository=repo,
        on_call=_progress_writer(
            repo,
            run_id=int(run_id),
            total_blocks=len(plan.blocks),
            expected_calls=expected_calls,
            total_chapters=stats.chapter_count,
            chapters_per_block=resolved.chapters_per_block,
            provider_name=provider_name,
            model_name=model_name,
            started_at=time.monotonic(),
            tokens=lambda: (provider.input_tokens, provider.output_tokens),
            commit=_persist_commit,
        ),
    )
    coordinator = RunCoordinator(
        extractor=BlockExtractor(
            provider=provider,
            profile=density,
            output_budget=resolved.output_budget,
            prompt_template_hash=prompt_template_hash(density, instructions),
        ),
        profile=density,
        # The stage interpretations are the one unit both readings need: 拆文 re-segments the
        # book into 起承转合 and needs to know what happened in each act to do it.
        stage_interpreter=lambda payload: provider.json_unit("stage", STAGE_INSTRUCTION, payload),
        # Everything below is the diagnostic reading, and a 拆文 run passes None for all of it —
        # which is how the mode costs four calls above L1 instead of thirteen. The coordinator
        # already treats a missing unit as "that section was not produced", so nothing here
        # needed a branch.
        topic_synthesizer=None if breakdown else (
            lambda topic, payload: provider.json_unit(
                f"topic:{topic.value}", TOPIC_INSTRUCTION.format(topic=topic.value), payload
            )
        ),
        assessor=None if breakdown else (
            lambda payload: provider.json_unit(
                "assessment",
                build_assessment_instruction(payload.get("pacing_regions", ())),
                payload,
            )
        ),
        finaliser=None if breakdown else (
            lambda payload: provider.json_unit("final", FINAL_INSTRUCTION, payload)
        ),
        thread_pairer=None if breakdown else (
            lambda payload: provider.json_unit(
                "pairing", "", payload,
                prompt=build_suspense_pairing_prompt(payload["threads"], payload["reveals"]),
            )
        ),
        # One more bounded whole-book call, for the judgement a block structurally cannot
        # make: which beats overturned an earlier one.
        reversal_finder=None if breakdown else (
            lambda reveals: provider.json_unit(
                "reversal", "", reveals, prompt=build_reversal_prompt(reveals)
            )
        ),
        # ------------------------------------------------------------------ 拆文
        beat_shaper=(
            lambda payload: provider.json_unit("beats", FOUR_BEATS_INSTRUCTION, payload)
        ) if breakdown else None,
        moment_selector=(
            lambda candidates: provider.json_unit(
                "moments", "", candidates,
                prompt=build_standout_prompt(candidates, hook_vocabulary(axes)),
            )
        ) if breakdown else None,
        cast_reader=(
            lambda payload: provider.json_unit("cast", CAST_FUNCTION_INSTRUCTION, payload)
        ) if breakdown else None,
        technique_reader=(
            lambda payload: provider.json_unit("techniques", REUSABLE_INSTRUCTION, payload)
        ) if breakdown else None,
    )

    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, int(run_id))
        session.refresh(run)
        _persist_commit()
    run.engine_id = ENGINE_ID
    run.engine_version = ENGINE_VERSION
    session.flush()
    _persist_commit()

    snapshot_revision = str(chapters[0].content_hash or "") if chapters else ""
    report = coordinator.run(
        plan=plan,
        chapters_by_order={c.chapter_order: c for c in chapters},
        character_count=stats.character_count,
        book_id=int(run.book_id),
        snapshot_id=int(run.snapshot_id),
        revision_hash=snapshot_revision,
        title=str(book.title or ""),
        run_id=int(run_id),
        provider_name=provider_name,
        model_name=model_name,
        profile_axes=axes,
    )
    if not report.document:
        raise ValueError("long-novel run produced no document")
    # A run that reached no provider at all is a local merge wearing a real run's clothes, and
    # the formal product refuses to store one — the same rule the hierarchical path enforces.
    if not provider.calls:
        run.status = WholeBookRunStatus.failed.value
        run.failure_code = "LONG_NOVEL_NO_PROVIDER_CALLS"
        run.failure_message_safe = "全书分析未产生任何真实模型调用，未写入完成态。请重新分析。"
        session.flush()
        _persist_commit()
        raise ValueError("long-novel run made no provider calls")

    result = WholeBookAnalysisV2.model_validate(report.document)
    version_id = repo.save_result(result)
    run.status = WholeBookRunStatus.completed.value
    run.current_stage_code = "complete"
    # The last progress write a client sees must say "complete", not 99% — a run that
    # finishes while the progress row still reads "extracting" is indistinguishable from one
    # that hung there.
    repo.save_progress(
        int(run_id),
        ProgressV2(
            overall_percent=100.0, current_stage="complete", stage_percent=100.0,
            current_window=report.blocks_extracted, total_windows=report.blocks_total,
            current_chapter=stats.chapter_count, total_chapters=stats.chapter_count,
            provider_calls_completed=provider.calls, provider_calls_estimated=provider.calls,
            successful_calls=provider.calls, failed_calls=len(report.blocks_failed),
            retry_calls=0, repair_calls=0,
            elapsed_seconds=0, estimated_remaining_seconds=0, estimated_cost=0.0,
            estimated_actual_cost=round(
                provider.input_tokens / 1e6 + provider.output_tokens / 1e6 * 2, 4
            ),
            provider=provider_name, model=model_name,
            last_completed_action="全书分析完成", current_action="",
            last_activity_at=datetime.now(timezone.utc),
        ),
    )
    session.flush()
    from app.narrative_core.whole_book_v2.usage_ledger import ensure_task_projection

    ensure_task_projection(session, run)
    _persist_commit()
    coverage = report.chapter_coverage(stats.chapter_count)
    logger.info(
        "long_novel_run_ok run_id=%s blocks=%s/%s chapter_coverage=%.3f calls=%s",
        run_id, report.blocks_extracted, report.blocks_total, coverage, provider.calls,
    )
    return {
        "run_id": int(run_id),
        "engine_id": ENGINE_ID,
        "engine_version": ENGINE_VERSION,
        "schema_version": result.schema_version,
        "asset_version_id": version_id,
        "provider_calls": provider.calls,
        "pipeline": "long_novel_engine",
        "blocks_extracted": report.blocks_extracted,
        "blocks_total": report.blocks_total,
        "chapter_coverage": round(coverage, 4),
        "journey_axis": result.journey.axis,
        "result_origin": result.analysis_metadata.result_origin,
    }


__all__ = [
    "ENGINE_ID",
    "ENGINE_VERSION",
    "book_uses_long_novel_engine",
    "profile_confirmation_state",
    "execute_long_novel_pipeline_v1",
]
