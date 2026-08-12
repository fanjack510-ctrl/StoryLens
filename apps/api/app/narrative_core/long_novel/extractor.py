"""``BlockExtractor`` — the only module that reads chapter prose (INV-8).

Everything above L1 works over the facts this module produces, never over the text again.
That single-read property is what makes the whole cost model true: a 542-chapter novel is
read once, into paragraph-anchored facts, and a seventh analysis module later costs one
bounded call instead of another full pass over the book.

Three things here are load-bearing and easy to get wrong:

**Paragraph anchors are block-local.** The provider sees ``[p:1]`` … ``[p:n]`` numbered
within *this block's* rendered text. They are not snapshot paragraph ids: a snapshot-assigned
number would renumber on every insertion, changing the rendered payload — and therefore the
provider input fingerprint — of every later block in the novel, destroying the reuse of a
tail that did not change.

**The fingerprint is taken over the exact payload sent.** Not over the ids that were
selected, not over a summary of them. It is the only value permitted to authorise skipping a
paid call, so it must be computed from the thing that was actually transmitted.

**Nothing is persisted that the model merely asserted.** Evidence anchors are checked against
the rendered range, mentions are bound to real textual occurrences, and both refuse rather
than guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel import ids
from app.narrative_core.long_novel.contracts.density import DensityProfile
from app.narrative_core.long_novel.contracts.enums import UnitKind
from app.narrative_core.long_novel.contracts.l1 import BlockAsset, CarryForwardState
from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode
from app.narrative_core.long_novel.mention_binding import EmittedMention, bind_mention_occurrences
from app.narrative_core.long_novel.provider_io import (
    RepairDecision,
    detect_truncation,
    plan_repair,
    recover_json,
)

__all__ = [
    "SourceParagraph",
    "SourceChapter",
    "RenderedBlock",
    "ExtractionResult",
    "BlockProvider",
    "BlockExtractor",
]


@dataclass(frozen=True)
class SourceParagraph:
    paragraph_order: int
    text: str
    content_hash: str


@dataclass(frozen=True)
class SourceChapter:
    chapter_order: int
    source_chapter_id: int | None
    content_hash: str
    snapshot_chapter_id: int | None
    paragraphs: Sequence[SourceParagraph]


@dataclass
class RenderedBlock:
    """A block's prose as the provider will see it, plus the maps back to identity."""

    text: str
    n_paragraphs: int
    #: block-local ``[p:N]`` → the paragraph's occurrence key
    occurrence_keys: dict[int, str] = field(default_factory=dict)
    #: block-local ``[p:N]`` → normalised paragraph text, for mention binding
    texts: dict[int, str] = field(default_factory=dict)
    #: block-local ``[p:N]`` → snapshot metadata for the evidence rows
    metadata: dict[int, dict[str, object]] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    block_key: str
    asset: BlockAsset
    provider_input_fingerprint: str
    mentions_bound: int
    repairs_applied: list[str]
    provider_calls: int


class BlockProvider(Protocol):
    """What the extractor needs from a provider. A fake satisfying this runs the whole
    pipeline at full scale for nothing, which is how the engine is validated before a single
    real token is bought."""

    def complete(
        self,
        *,
        payload: dict[str, object],
        max_output_tokens: int,
        repair_note: str | None = None,
    ) -> tuple[str, str | None, int | None]:
        """Return ``(raw_text, finish_reason, output_tokens)``.

        ``repair_note`` is the bounded error appendix on a repair attempt. The parent payload
        is re-sent unchanged alongside it — never a reduced form, because a model asked to
        rebuild an asset it can no longer see returns a valid-looking fraction of it.
        """
        ...


class BlockExtractor:
    def __init__(
        self,
        *,
        provider: BlockProvider,
        profile: DensityProfile,
        output_budget: int,
        prompt_template_hash: str = "",
    ) -> None:
        self._provider = provider
        self._profile = profile
        self._output_budget = output_budget
        self._prompt_template_hash = prompt_template_hash

    # ------------------------------------------------------------------ rendering
    def render(self, chapters: Sequence[SourceChapter]) -> RenderedBlock:
        """Render chapters with inline ``[p:N]`` markers, N block-local and 1-based.

        The marker costs about four tokens and sits adjacent to the text it anchors, which is
        why it replaced a separate paragraph catalogue: the catalogue cost thousands of tokens
        per block and appeared in no budget term.
        """
        lines: list[str] = []
        rendered = RenderedBlock(text="", n_paragraphs=0)
        anchor = 0
        for chapter in chapters:
            # Chapter boundaries must be visible in the rendered text. Without them the block
            # is one undifferentiated run of paragraphs, and a contract that demands one
            # signal per chapter and a chapter_ref on every fact is asking the model for
            # something the text it was given does not contain. A real model returned one
            # signal for a two-chapter block, repaired, and returned one again — correctly,
            # because the boundary was never shown to it.
            lines.append(f"=== 第 {chapter.chapter_order} 章 ===")
            chapter_occurrence = ids.chapter_occurrence_key(
                chapter.content_hash,
                chapter.source_chapter_id
                if chapter.source_chapter_id is not None
                else f"prov:{chapter.chapter_order}",
            )
            seen: dict[str, int] = {}
            for paragraph in chapter.paragraphs:
                anchor += 1
                duplicate_index = seen.get(paragraph.content_hash, 0)
                seen[paragraph.content_hash] = duplicate_index + 1
                occurrence = ids.paragraph_occurrence_key(
                    chapter_occurrence, paragraph.content_hash, duplicate_index
                )
                lines.append(f"[p:{anchor}] {paragraph.text}")
                rendered.occurrence_keys[anchor] = occurrence
                rendered.texts[anchor] = paragraph.text
                rendered.metadata[anchor] = {
                    "chapter_order": chapter.chapter_order,
                    "snapshot_chapter_id": chapter.snapshot_chapter_id,
                    "paragraph_content_hash": paragraph.content_hash,
                    "stable_paragraph_id": str(paragraph.paragraph_order),
                    "start_offset": 0,
                    "end_offset": len(paragraph.text),
                }
        rendered.text = "\n".join(lines)
        rendered.n_paragraphs = anchor
        return rendered

    # ------------------------------------------------------------------ payload
    def build_payload(
        self, rendered: RenderedBlock, carry_in: CarryForwardState
    ) -> dict[str, object]:
        """The exact semantic payload that will be sent — this is what the fingerprint hashes."""
        p = self._profile
        return {
            "unit": "block_extract.v1",
            "text": rendered.text,
            "carry_in": carry_in.model_dump(),
            "caps": {
                "events_per_chapter": p.events_per_chapter,
                "state_changes_per_chapter": p.state_changes_per_chapter,
                "causal_per_chapter": p.causal_per_chapter,
                "suspense_actions_per_chapter": p.suspense_actions_per_chapter,
                "mentions_per_chapter": p.mentions_per_chapter,
                "relationships_per_block": p.relationships_per_block,
                "goals_per_block": p.goals_per_block,
                "choices_per_block": p.choices_per_block,
                "threads_per_block": p.threads_per_block,
                "identities_per_block": p.identities_per_block,
                "max_provisional_entities": p.max_provisional_entities,
            },
            "prompt_template": self._prompt_template_hash,
        }

    # ------------------------------------------------------------------ extraction
    def extract(
        self,
        *,
        block_key: str,
        chapters: Sequence[SourceChapter],
        carry_in: CarryForwardState | None = None,
    ) -> ExtractionResult:
        carry = carry_in or CarryForwardState()
        rendered = self.render(chapters)
        payload = self.build_payload(rendered, carry)
        fingerprint = ids.provider_input_fingerprint(
            UnitKind.BLOCK.value, C.SEMANTIC_CONTRACT_VERSION, payload
        )

        raw, finish_reason, output_tokens = self._provider.complete(
            payload=payload, max_output_tokens=self._output_budget
        )
        calls = 1

        truncation = detect_truncation(
            finish_reason=finish_reason,
            raw_text=raw,
            requested_output_tokens=self._output_budget,
            output_tokens=output_tokens,
            declared_max_output_tokens=self._output_budget,
        )
        if truncation is not None:
            # Not repairable by re-asking: the unit must get smaller, so it escalates to the
            # planner, which splits the block. Spending another call on the same shape would
            # buy the same truncation twice.
            raise LongNovelError(
                truncation,
                f"{block_key} did not fit the output ceiling; split the block and retry",
                unit_key=block_key,
                detail={"finish_reason": finish_reason, "output_tokens": output_tokens},
            )

        outcome = recover_json(
            raw,
            optional_containers={
                "mentions": [],
                "provisional_entities": [],
                "causal_links": [],
                "identity_assertions": [],
            },
        )
        if not outcome.recovered:
            plan = plan_repair(
                code=outcome.code or LongNovelErrorCode.SCHEMA_MISMATCH,
                parent_payload_tokens=len(rendered.text) // 2,
                repair_input_budget=0,
                parent_splittable=True,
            )
            raise LongNovelError(
                plan.code,
                f"{block_key}: {outcome.message or plan.reason}",
                unit_key=block_key,
                detail={"decision": plan.decision.value, "steps": outcome.steps},
            )

        try:
            asset = self._validate(block_key, outcome.value, expected_chapters=len(chapters))
            bound = self._bind_mentions(block_key, asset, rendered)
            self._check_evidence_anchors(block_key, asset, rendered)
        except LongNovelError as first_failure:
            asset, bound, extra_calls = self._repair_once(
                block_key=block_key,
                failure=first_failure,
                payload=payload,
                rendered=rendered,
                expected_chapters=len(chapters),
            )
            calls += extra_calls

        return ExtractionResult(
            block_key=block_key,
            asset=asset,
            provider_input_fingerprint=fingerprint,
            mentions_bound=len(bound),
            repairs_applied=outcome.steps,
            provider_calls=calls,
        )

    # ------------------------------------------------------------------ repair
    def _repair_once(
        self,
        *,
        block_key: str,
        failure: LongNovelError,
        payload: dict[str, object],
        rendered: RenderedBlock,
        expected_chapters: int,
    ):
        """One full repair attempt, then terminal. No reduced form, ever.

        The ladder is deliberately short. A second and third attempt at the same defect
        mostly buys the same defect again, and every attempt is billed; the design would
        rather split the unit or stop than keep paying for the same mistake.
        """
        plan = plan_repair(
            code=failure.code,
            parent_payload_tokens=len(str(payload["text"])) // 2,
            repair_input_budget=self._output_budget * 4,
            parent_splittable=True,
        )
        if plan.decision is not RepairDecision.FULL_PROVIDER_REPAIR:
            raise failure

        note = (
            f"上一次响应不合规：{failure.message}\n"
            "请重新输出**完整**的 JSON，修正该问题，其余内容保持不变。"
        )
        raw, finish_reason, output_tokens = self._provider.complete(
            payload=payload, max_output_tokens=self._output_budget, repair_note=note
        )
        outcome = recover_json(raw)
        if not outcome.recovered:
            raise failure

        # A repair that fails the same check is not retried again: it is terminal for this
        # revision, and the planner may split the block instead.
        asset = self._validate(block_key, outcome.value, expected_chapters=expected_chapters)
        bound = self._bind_mentions(block_key, asset, rendered)
        self._check_evidence_anchors(block_key, asset, rendered)
        return asset, bound, 1

    # ------------------------------------------------------------------ validation
    def _validate(self, block_key: str, value: object, *, expected_chapters: int) -> BlockAsset:
        if not isinstance(value, dict):
            raise LongNovelError(
                LongNovelErrorCode.SCHEMA_MISMATCH,
                f"{block_key}: expected a JSON object at the top level",
                unit_key=block_key,
            )
        payload = dict(value)
        payload.setdefault("asset_schema_version", C.ASSET_SCHEMA_VERSION)
        try:
            asset = BlockAsset.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError
            raise LongNovelError(
                LongNovelErrorCode.SCHEMA_MISMATCH,
                f"{block_key}: {exc}",
                unit_key=block_key,
            ) from exc
        self._check_caps(block_key, asset)
        self._check_chapter_coverage(block_key, asset, expected_chapters)
        return asset

    def _check_chapter_coverage(
        self, block_key: str, asset: BlockAsset, expected_chapters: int
    ) -> None:
        """Exactly one ``ChapterSignal`` per chapter in the block — mandatory, not a cap.

        Checked because the failure is silent and expensive: chapter signals feed the pacing
        curve and the per-chapter output, so a missing one drops that chapter out of the
        analysis while every other check stays green. Upper bounds alone would let it
        through, which is exactly what happened the first time a real model returned one
        signal for a two-chapter block.
        """
        actual = len(asset.chapter_signals)
        if actual != expected_chapters:
            raise LongNovelError(
                LongNovelErrorCode.CARDINALITY_VIOLATION,
                f"{block_key}: {actual} chapter signal(s) for {expected_chapters} chapter(s); "
                "exactly one per chapter is mandatory",
                unit_key=block_key,
                detail={"expected": expected_chapters, "actual": actual},
            )
        refs = [s.chapter_ref for s in asset.chapter_signals]
        if len(set(refs)) != len(refs):
            raise LongNovelError(
                LongNovelErrorCode.CARDINALITY_VIOLATION,
                f"{block_key}: duplicate chapter_ref in chapter signals: {sorted(refs)}",
                unit_key=block_key,
                detail={"chapter_refs": sorted(refs)},
            )

    def _check_caps(self, block_key: str, asset: BlockAsset) -> None:
        """Per-block caps are a contract, not a suggestion.

        Accepting an over-cap asset would silently break the output budget the whole plan
        rests on: the next block would be sized against an estimate the model has already
        exceeded.
        """
        p = self._profile
        for field_name, cap in (
            ("relationship_changes", p.relationships_per_block),
            ("goal_changes", p.goals_per_block),
            ("choices", p.choices_per_block),
            ("suspense_threads", p.threads_per_block),
            ("identity_assertions", p.identities_per_block),
            ("provisional_entities", p.max_provisional_entities),
        ):
            actual = len(getattr(asset, field_name))
            if actual > cap:
                raise LongNovelError(
                    LongNovelErrorCode.CARDINALITY_VIOLATION,
                    f"{block_key}: {field_name} returned {actual}, cap is {cap}",
                    unit_key=block_key,
                    detail={"field": field_name, "actual": actual, "cap": cap},
                )

    def _bind_mentions(self, block_key: str, asset: BlockAsset, rendered: RenderedBlock):
        emitted: list[EmittedMention] = []
        cluster_of: dict[int, str] = {}
        for cluster_index, cluster in enumerate(asset.provisional_entities):
            for member in cluster.member_mention_indexes:
                cluster_of[member] = f"le{cluster_index}"
        for index, mention in enumerate(asset.mentions):
            emitted.append(
                EmittedMention(
                    surface_norm=mention.surface_norm,
                    paragraph_ref=mention.paragraph_ref,
                    cluster_ref=cluster_of.get(index),
                )
            )
        try:
            return bind_mention_occurrences(emitted, rendered.texts, rendered.occurrence_keys)
        except LongNovelError as exc:
            exc.unit_key = block_key
            raise

    def _check_evidence_anchors(
        self, block_key: str, asset: BlockAsset, rendered: RenderedBlock
    ) -> None:
        """A returned anchor outside the rendered range is a fabrication, not a near miss."""
        for field_name in (
            "chapter_signals",
            "events",
            "character_state_changes",
            "causal_links",
            "suspense_actions",
            "relationship_changes",
            "goal_changes",
            "choices",
            "suspense_threads",
            "identity_assertions",
        ):
            for item in getattr(asset, field_name):
                for ref in item.evidence:
                    if ref.paragraph_ref not in rendered.occurrence_keys:
                        raise LongNovelError(
                            LongNovelErrorCode.EVIDENCE_ANCHOR_MISMATCH,
                            f"{block_key}: [p:{ref.paragraph_ref}] is outside the block's "
                            f"rendered range of 1..{rendered.n_paragraphs}",
                            unit_key=block_key,
                            detail={"field": field_name, "paragraph_ref": ref.paragraph_ref},
                        )
