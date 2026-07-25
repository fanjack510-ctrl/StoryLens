"""STEP 2.3-I0 — Adapter Protocol, Engine Loader, and Public↔Private parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WholeBookOverviewErrorCode,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION,
    ChapterRef,
    OverviewRunRef,
    PriorStateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WindowConstraints,
    WindowParagraph,
    WindowSlice,
)
from app.narrative_core.enums import WholeBookAnalysisMode, WindowStatus
from app.narrative_core.services.native_overview_fixture_adapter import (
    compute_window_input_hash,
    load_private_fixture_engine_adapter,
)
from app.narrative_core.services.whole_book_overview_engine_loader import (
    EngineLoadError,
    load_overview_engine,
)
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    WholeBookOverviewEngineAdapter,
)


SHORT_BOOK = Path("packages/contracts/fixtures/walking_skeleton/short_book_v1.json")


def _window_input_from_short_book() -> WholeBookOverviewWindowInputV1:
    book = json.loads(SHORT_BOOK.read_text(encoding="utf-8"))
    paragraphs: list[WindowParagraph] = []
    chapter_refs: list[ChapterRef] = []
    idx = 0
    for ci, ch in enumerate(book["chapters"]):
        cid = f"c{ci + 1}"
        chapter_refs.append(ChapterRef(chapter_id=cid, chapter_index=ci, title=ch["title"]))
        for text in ch["paragraphs"]:
            paragraphs.append(
                WindowParagraph(
                    paragraph_id=f"p{idx + 1}",
                    chapter_id=cid,
                    paragraph_index=idx,
                    text=text,
                )
            )
            idx += 1
    input_hash = compute_window_input_hash(paragraphs)
    return WholeBookOverviewWindowInputV1(
        contract_version=CONTRACT_VERSION,
        run=OverviewRunRef(
            run_id="parity-1",
            book_id="1",
            snapshot_id="1",
            mode=WholeBookAnalysisMode.NATIVE,
            engine_version="walking-skeleton-1",
            prompt_version="fixture-no-prompt",
        ),
        window=WindowSlice(
            window_id="w-0",
            window_index=0,
            total_windows=1,
            start_paragraph_id=paragraphs[0].paragraph_id,
            end_paragraph_id=paragraphs[-1].paragraph_id,
            chapter_refs=chapter_refs,
            paragraphs=paragraphs,
            input_hash=input_hash,
            status=WindowStatus.RUNNING,
        ),
        prior_state=PriorStateV1(),
        constraints=WindowConstraints(
            allowed_asset_types=["goal", "conflict", "consequence"],
            allowed_entity_types=["character"],
            evidence_required=True,
        ),
    )


def _shape(obj: object) -> object:
    """Normalize payloads to comparable JSON-compatible shapes (keys/types)."""

    if hasattr(obj, "model_dump"):
        return _shape(obj.model_dump(mode="json"))
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_shape(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return type(obj).__name__
    return type(obj).__name__


def test_fixture_engine_implements_protocol() -> None:
    adapter = load_overview_engine(FIXTURE_ENGINE_ID)
    assert isinstance(adapter, WholeBookOverviewEngineAdapter)
    assert adapter.engine_id == FIXTURE_ENGINE_ID


def test_private_native_engine_missing_does_not_silent_fallback() -> None:
    with pytest.raises(EngineLoadError) as exc:
        load_overview_engine(PRIVATE_NATIVE_OVERVIEW_ENGINE_ID)
    assert exc.value.code == WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value


def test_unknown_engine_incompatible() -> None:
    with pytest.raises(EngineLoadError) as exc:
        load_overview_engine("not-a-real-engine")
    assert exc.value.code == WholeBookOverviewErrorCode.PRIVATE_ENGINE_INCOMPATIBLE.value


def test_loader_and_direct_fixture_adapter_same_object_type() -> None:
    a = load_overview_engine(FIXTURE_ENGINE_ID)
    b = load_private_fixture_engine_adapter()
    assert type(a) is type(b)
    assert a.engine_id == b.engine_id == FIXTURE_ENGINE_ID


def test_public_bridge_matches_private_direct_payload_shapes() -> None:
    """Public bridge vs Private direct call — structure parity (values may differ)."""

    from storylens_private_engine.contracts.whole_book_overview_v1 import (
        WholeBookOverviewWindowInputV1 as PrivIn,
    )
    from storylens_private_engine.modules.book_overview.fixture_adapter import (
        run_synthesis_fixture,
        run_window_fixture,
    )

    public_adapter = load_overview_engine(FIXTURE_ENGINE_ID)
    win_in = _window_input_from_short_book()

    public_window = public_adapter.analyze_window(win_in)
    private_window = run_window_fixture(
        PrivIn.model_validate(win_in.model_dump(mode="json"))
    )

    pub_w = public_window.model_dump(mode="json")
    priv_w = private_window.model_dump(mode="json")
    assert set(pub_w.keys()) == set(priv_w.keys())
    assert _shape(pub_w["candidate_entities"]) == _shape(priv_w["candidate_entities"])
    assert _shape(pub_w["candidate_assets"]) == _shape(priv_w["candidate_assets"])
    assert _shape(pub_w["candidate_evidence"]) == _shape(priv_w["candidate_evidence"])
    assert _shape(pub_w["state_delta"]) == _shape(priv_w["state_delta"])
    # Values should match for deterministic fixture on identical input.
    assert pub_w == priv_w

    syn = WholeBookOverviewSynthesisInputV1(
        contract_version=CONTRACT_VERSION,
        run_id=win_in.run.run_id,
        book_id=win_in.run.book_id,
        snapshot_id=win_in.run.snapshot_id,
        engine_version=win_in.run.engine_version,
        prompt_version=win_in.run.prompt_version,
        entities=[e.model_dump(mode="json") for e in public_window.candidate_entities],
        assets=[a.model_dump(mode="json") for a in public_window.candidate_assets],
        evidence=[e.model_dump(mode="json") for e in public_window.candidate_evidence],
        final_state=PriorStateV1.model_validate(
            {**public_window.state_delta.model_dump(mode="json"), "state_version": 1}
        ),
        selected_evidence=list(public_window.candidate_evidence),
    )
    public_proj = public_adapter.synthesize_overview(syn)
    from storylens_private_engine.contracts.whole_book_overview_v1 import (
        WholeBookOverviewSynthesisInputV1 as PrivSyn,
    )

    private_proj = run_synthesis_fixture(
        PrivSyn.model_validate(syn.model_dump(mode="json"))
    )
    pub_p = public_proj.model_dump(mode="json")
    priv_p = private_proj.model_dump(mode="json")
    assert set(pub_p.keys()) == set(priv_p.keys())
    assert _shape(pub_p) == _shape(priv_p)
    assert pub_p == priv_p


def test_ending_asset_type_uses_public_asset_enum() -> None:
    adapter = load_overview_engine(FIXTURE_ENGINE_ID)
    result = adapter.analyze_window(_window_input_from_short_book())
    types = {a.asset_type for a in result.candidate_assets}
    assert "consequence" in types
    assert "ending_state" not in types
