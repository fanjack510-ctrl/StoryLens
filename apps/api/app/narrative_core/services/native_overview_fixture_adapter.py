"""Public ↔ Private Fixture Adapter boundary for STEP 2.2 walking skeleton.

Swap point (Integration / PYTHONPATH):
  Prefer real Private package when available::

      from storylens_private_engine.modules.book_overview.fixture_adapter import (
          run_window_fixture,
          run_synthesis_fixture,
      )

  Until Agent B merges, this module provides ``NativeOverviewFixtureAdapter``
  Protocol + deterministic ``FakeFixtureAdapter`` that emits candidates matching
  frozen WholeBookOverview*V1 DTO shapes. Results are Fixture Development Mode
  only — not real AI / Provider output.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_DEVELOPMENT_WARNING,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION,
    CandidateAssetV1,
    CandidateEntityV1,
    CandidateEvidenceV1,
    OverviewField,
    PriorStateV1,
    StateDeltaV1,
    WholeBookOverviewProjectionCandidateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
    WindowParagraph,
    WindowQualityV1,
)
from app.narrative_core.enums import OverviewFieldStatus


def compute_window_input_hash(paragraphs: Sequence[WindowParagraph | Mapping[str, Any]]) -> str:
    """Stable SHA-256 hex — must match Private fixture_adapter.compute_window_input_hash."""

    normalized: list[tuple[int, str, str]] = []
    for raw in paragraphs:
        if isinstance(raw, WindowParagraph):
            pid = raw.paragraph_id
            text = raw.text
            idx = raw.paragraph_index
        elif isinstance(raw, Mapping):
            pid = str(raw.get("paragraph_id") or "")
            text = str(raw.get("text") or "")
            idx = int(raw.get("paragraph_index") or 0)
        else:
            pid = str(getattr(raw, "paragraph_id", "") or "")
            text = str(getattr(raw, "text", "") or "")
            idx = int(getattr(raw, "paragraph_index", 0) or 0)
        normalized.append((idx, pid, text))
    normalized.sort(key=lambda item: (item[0], item[1]))
    payload = "".join(f"{pid}\n{text}\n" for _, pid, text in normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_input_hash(value: str) -> str:
    text = (value or "").strip()
    if text.lower().startswith("sha256:"):
        return text[7:].strip()
    return text


@runtime_checkable
class NativeOverviewFixtureAdapter(Protocol):
    """Private Fixture Adapter surface used by Public orchestrator."""

    def run_window(
        self, window_input: WholeBookOverviewWindowInputV1
    ) -> WholeBookOverviewWindowResultV1: ...

    def run_synthesis(
        self, synthesis_input: WholeBookOverviewSynthesisInputV1
    ) -> WholeBookOverviewProjectionCandidateV1: ...


class FakeFixtureAdapter:
    """In-process deterministic Fake — swap to real Private via get_fixture_adapter()."""

    def run_window(
        self, window_input: WholeBookOverviewWindowInputV1
    ) -> WholeBookOverviewWindowResultV1:
        paragraphs = list(window_input.window.paragraphs)
        if not paragraphs:
            raise RuntimeError("fixture adapter requires at least one paragraph")

        p0 = paragraphs[0]
        p_mid = paragraphs[min(2, len(paragraphs) - 1)]
        p_last = paragraphs[-1]

        quote_entity = _pick_quote(p0.text, preferred="林澈")
        quote_goal = _pick_quote(p0.text, preferred="灯塔")
        quote_conflict = _pick_quote(p_mid.text, preferred="风暴")
        quote_ending = _pick_quote(p_last.text, preferred="光")

        entities = [
            CandidateEntityV1(
                candidate_id="ce-protagonist",
                entity_type="character",
                canonical_name="林澈",
                aliases=["他"],
                description="港口启程、点亮灯塔的主角",
                confidence=0.92,
                evidence_refs=["ev-protagonist"],
            )
        ]
        assets = [
            CandidateAssetV1(
                candidate_id="ca-goal",
                asset_type="goal",
                title="点亮灯塔",
                summary="点亮灯塔以拯救全城",
                subject_candidate_ids=["ce-protagonist"],
                confidence=0.88,
                evidence_refs=["ev-goal"],
                deduplication_key="goal:light_lighthouse",
            ),
            CandidateAssetV1(
                candidate_id="ca-conflict",
                asset_type="conflict",
                title="风暴与自我放弃",
                summary="风暴与自我放弃念头",
                subject_candidate_ids=["ce-protagonist"],
                confidence=0.84,
                evidence_refs=["ev-conflict"],
                deduplication_key="conflict:storm_self_doubt",
            ),
            CandidateAssetV1(
                candidate_id="ca-question",
                asset_type="question",
                title="灯塔能否被点亮",
                summary="今夜能否点亮灯塔拯救全城？",
                subject_candidate_ids=["ce-protagonist"],
                confidence=0.8,
                evidence_refs=["ev-goal"],
                deduplication_key="question:can_light_beacon",
            ),
            CandidateAssetV1(
                candidate_id="ca-turning",
                asset_type="event",
                title="半路风暴撕开甲板",
                summary="半路风暴撕开甲板",
                subject_candidate_ids=["ce-protagonist"],
                confidence=0.86,
                evidence_refs=["ev-conflict"],
                deduplication_key="event:storm_deck",
            ),
            CandidateAssetV1(
                candidate_id="ca-ending",
                asset_type="final_payoff",
                title="灯塔点燃",
                summary="灯塔点燃，全城重获光明",
                subject_candidate_ids=["ce-protagonist"],
                confidence=0.9,
                evidence_refs=["ev-ending"],
                deduplication_key="ending:beacon_lit",
            ),
        ]
        evidence = [
            CandidateEvidenceV1(
                evidence_id="ev-protagonist",
                paragraph_id=p0.paragraph_id,
                chapter_id=p0.chapter_id,
                quote=quote_entity,
                evidence_role="support",
                confidence=0.95,
                supports_candidate_ids=["ce-protagonist"],
            ),
            CandidateEvidenceV1(
                evidence_id="ev-goal",
                paragraph_id=p0.paragraph_id,
                chapter_id=p0.chapter_id,
                quote=quote_goal,
                evidence_role="support",
                confidence=0.9,
                supports_candidate_ids=["ca-goal", "ca-question"],
            ),
            CandidateEvidenceV1(
                evidence_id="ev-conflict",
                paragraph_id=p_mid.paragraph_id,
                chapter_id=p_mid.chapter_id,
                quote=quote_conflict,
                evidence_role="support",
                confidence=0.9,
                supports_candidate_ids=["ca-conflict", "ca-turning"],
            ),
            CandidateEvidenceV1(
                evidence_id="ev-ending",
                paragraph_id=p_last.paragraph_id,
                chapter_id=p_last.chapter_id,
                quote=quote_ending,
                evidence_role="support",
                confidence=0.93,
                supports_candidate_ids=["ca-ending"],
            ),
        ]
        return WholeBookOverviewWindowResultV1(
            contract_version=CONTRACT_VERSION,
            run_id=window_input.run.run_id,
            window_id=window_input.window.window_id,
            input_hash=window_input.window.input_hash,
            candidate_entities=entities,
            candidate_assets=assets,
            candidate_evidence=evidence,
            state_delta=StateDeltaV1(
                characters=[{"candidate_id": "ce-protagonist", "name": "林澈"}],
                aliases=[{"alias": "他", "entity_candidate_id": "ce-protagonist"}],
                protagonist_candidates=[{"candidate_id": "ce-protagonist"}],
                goal_candidates=[{"candidate_id": "ca-goal"}],
                conflict_candidates=[{"candidate_id": "ca-conflict"}],
                central_question_candidates=[{"candidate_id": "ca-question"}],
                major_event_candidates=[{"candidate_id": "ca-turning"}],
                climax_candidates=[],
                ending_state_candidates=[{"candidate_id": "ca-ending"}],
            ),
            warnings=[FIXTURE_DEVELOPMENT_WARNING],
            quality=WindowQualityV1(confidence=0.85),
        )

    def run_synthesis(
        self, synthesis_input: WholeBookOverviewSynthesisInputV1
    ) -> WholeBookOverviewProjectionCandidateV1:
        evidence_ids = [
            e.evidence_id if hasattr(e, "evidence_id") else str(e.get("evidence_id", "ev-1"))
            for e in (synthesis_input.selected_evidence or [])
        ]
        if not evidence_ids:
            evidence_ids = ["ev-protagonist"]
        primary = evidence_ids[0]
        refs_multi = evidence_ids[:2] if len(evidence_ids) > 1 else [primary]

        def field(value, confidence: float, refs: list[str], status: OverviewFieldStatus):
            return OverviewField(
                value=value,
                confidence=confidence,
                evidence_refs=refs,
                status=status,
            )

        return WholeBookOverviewProjectionCandidateV1(
            contract_version=CONTRACT_VERSION,
            run_id=synthesis_input.run_id,
            novel_type=field("奇幻试炼", 0.7, [primary], OverviewFieldStatus.SUPPORTED),
            narrative_features=field(
                ["灯塔意象", "跨章转折"],
                0.65,
                refs_multi,
                OverviewFieldStatus.LOW_CONFIDENCE,
            ),
            core_setting=field("港口与灯塔之城", 0.7, [primary], OverviewFieldStatus.SUPPORTED),
            protagonist=field("林澈", 0.92, [primary], OverviewFieldStatus.SUPPORTED),
            protagonist_core_goal=field(
                "点亮灯塔以拯救全城", 0.88, refs_multi, OverviewFieldStatus.SUPPORTED
            ),
            primary_conflict=field(
                "风暴与自我放弃念头", 0.84, refs_multi, OverviewFieldStatus.SUPPORTED
            ),
            central_question=field(
                "今夜能否点亮灯塔拯救全城？",
                0.8,
                refs_multi,
                OverviewFieldStatus.SUPPORTED,
            ),
            key_turning_points=field(
                ["半路风暴撕开甲板"], 0.86, refs_multi, OverviewFieldStatus.SUPPORTED
            ),
            climax=field(None, 0.0, [], OverviewFieldStatus.INSUFFICIENT_EVIDENCE),
            resolved_problem=field(
                "全城陷入黑暗的危机", 0.75, refs_multi, OverviewFieldStatus.SUPPORTED
            ),
            ending_state=field(
                "灯塔点燃，全城重获光明", 0.9, refs_multi, OverviewFieldStatus.SUPPORTED
            ),
            logline=field(
                "林澈必须点亮灯塔，才能在风暴中拯救全城。",
                0.85,
                refs_multi,
                OverviewFieldStatus.SUPPORTED,
            ),
            synopsis=field(
                "林澈带着点亮灯塔的旧信启程；风暴撕开甲板后，他战胜放弃念头并点燃灯塔。",
                0.82,
                refs_multi,
                OverviewFieldStatus.SUPPORTED,
            ),
            warnings=[FIXTURE_DEVELOPMENT_WARNING],
        )


class _PrivateBridgeAdapter:
    """Adapts Private module functions to NativeOverviewFixtureAdapter.

    Public and Private ship separate Pydantic class objects for the same wire
    shape. Always cross the boundary via ``model_dump`` / ``model_validate`` so
    Private never sees Public isinstance mismatches (e.g. WindowParagraph).
    """

    def __init__(self, run_window_fn, run_synthesis_fn) -> None:  # noqa: ANN001
        self._run_window = run_window_fn
        self._run_synthesis = run_synthesis_fn

    def run_window(
        self, window_input: WholeBookOverviewWindowInputV1
    ) -> WholeBookOverviewWindowResultV1:
        from storylens_private_engine.contracts.whole_book_overview_v1 import (  # type: ignore
            WholeBookOverviewWindowInputV1 as PrivateWindowInput,
        )

        private_req = PrivateWindowInput.model_validate(
            window_input.model_dump(mode="json")
        )
        raw = self._run_window(private_req)
        payload = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        return WholeBookOverviewWindowResultV1.model_validate(payload)

    def run_synthesis(
        self, synthesis_input: WholeBookOverviewSynthesisInputV1
    ) -> WholeBookOverviewProjectionCandidateV1:
        from storylens_private_engine.contracts.whole_book_overview_v1 import (  # type: ignore
            WholeBookOverviewSynthesisInputV1 as PrivateSynthesisInput,
        )

        private_req = PrivateSynthesisInput.model_validate(
            synthesis_input.model_dump(mode="json")
        )
        raw = self._run_synthesis(private_req)
        payload = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        return WholeBookOverviewProjectionCandidateV1.model_validate(payload)


def try_import_private_fixture_adapter() -> NativeOverviewFixtureAdapter | None:
    """Return Private adapter when package is on PYTHONPATH; else None."""

    try:
        from storylens_private_engine.modules.book_overview.fixture_adapter import (  # type: ignore
            run_synthesis_fixture,
            run_window_fixture,
        )
    except Exception:
        return None
    return _PrivateBridgeAdapter(run_window_fixture, run_synthesis_fixture)


def get_fixture_adapter(
    *, prefer_private: bool = True, force_fake: bool = False
) -> NativeOverviewFixtureAdapter:
    """Resolve adapter. Integration can force Private via PYTHONPATH without code change."""

    if force_fake:
        return FakeFixtureAdapter()
    if prefer_private:
        private = try_import_private_fixture_adapter()
        if private is not None:
            return private
    return FakeFixtureAdapter()


def empty_prior_state() -> PriorStateV1:
    return PriorStateV1(state_version=0)


def _pick_quote(text: str, *, preferred: str, min_len: int = 4) -> str:
    text = (text or "").strip()
    if not text:
        return "…"
    if preferred and preferred in text:
        idx = text.index(preferred)
        start = max(0, idx - 4)
        end = min(len(text), idx + len(preferred) + 8)
        quote = text[start:end].strip()
        if len(quote) >= min_len:
            return quote
    return text[: min(24, len(text))]
