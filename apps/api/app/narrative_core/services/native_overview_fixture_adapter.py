"""Public bridge to Private Fixture Adapter (STEP 2.3-I0).

Canonical fixture behavior lives in Private
``storylens_private_engine.modules.book_overview.fixture_adapter``.
Public does **not** maintain a divergent Fake payload schema.

Cross-repo Pydantic classes are converted via ``model_dump`` / ``model_validate``.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from app.narrative_core.contracts.pro_native_overview_flags import FIXTURE_ENGINE_ID
from app.narrative_core.contracts.whole_book_overview_errors import (
    WholeBookOverviewErrorCode,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    PriorStateV1,
    WholeBookOverviewProjectionCandidateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
    WindowParagraph,
)
from app.narrative_core.services.whole_book_overview_engine_loader import EngineLoadError
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    ProviderTransport,
    WholeBookOverviewEngineAdapter,
)


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


class PrivateFixtureEngineAdapter:
    """WholeBookOverviewEngineAdapter backed by Private fixture_adapter functions."""

    def __init__(self, run_window_fn, run_synthesis_fn) -> None:  # noqa: ANN001
        self._run_window = run_window_fn
        self._run_synthesis = run_synthesis_fn

    @property
    def engine_id(self) -> str:
        return FIXTURE_ENGINE_ID

    def analyze_window(
        self,
        payload: WholeBookOverviewWindowInputV1,
        transport: ProviderTransport | None = None,
    ) -> WholeBookOverviewWindowResultV1:
        del transport  # Fixture path ignores Provider transport.
        from storylens_private_engine.contracts.whole_book_overview_v1 import (  # type: ignore
            WholeBookOverviewWindowInputV1 as PrivateWindowInput,
        )

        private_req = PrivateWindowInput.model_validate(payload.model_dump(mode="json"))
        raw = self._run_window(private_req)
        data = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        return WholeBookOverviewWindowResultV1.model_validate(data)

    def synthesize_overview(
        self,
        payload: WholeBookOverviewSynthesisInputV1,
        transport: ProviderTransport | None = None,
    ) -> WholeBookOverviewProjectionCandidateV1:
        del transport
        from storylens_private_engine.contracts.whole_book_overview_v1 import (  # type: ignore
            WholeBookOverviewSynthesisInputV1 as PrivateSynthesisInput,
        )

        private_req = PrivateSynthesisInput.model_validate(payload.model_dump(mode="json"))
        raw = self._run_synthesis(private_req)
        data = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        return WholeBookOverviewProjectionCandidateV1.model_validate(data)

    # Back-compat aliases used by STEP 2.2 service call sites during I0 migration.
    def run_window(
        self, window_input: WholeBookOverviewWindowInputV1
    ) -> WholeBookOverviewWindowResultV1:
        return self.analyze_window(window_input)

    def run_synthesis(
        self, synthesis_input: WholeBookOverviewSynthesisInputV1
    ) -> WholeBookOverviewProjectionCandidateV1:
        return self.synthesize_overview(synthesis_input)


def load_private_fixture_engine_adapter() -> WholeBookOverviewEngineAdapter:
    """Import Private fixture adapter or raise EngineLoadError (no Fake fallback)."""

    try:
        from storylens_private_engine.modules.book_overview.fixture_adapter import (  # type: ignore
            FIXTURE_ENGINE_ID as PRIVATE_FIXTURE_ID,
            run_synthesis_fixture,
            run_window_fixture,
        )
    except Exception as exc:  # noqa: BLE001
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
            "Private fixture_adapter is not importable.",
            {"engine_id": FIXTURE_ENGINE_ID, "cause": type(exc).__name__},
        ) from exc

    if PRIVATE_FIXTURE_ID != FIXTURE_ENGINE_ID:
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_INCOMPATIBLE.value,
            "Private FIXTURE_ENGINE_ID mismatch.",
            {"expected": FIXTURE_ENGINE_ID, "actual": PRIVATE_FIXTURE_ID},
        )
    return PrivateFixtureEngineAdapter(run_window_fixture, run_synthesis_fixture)


def empty_prior_state() -> PriorStateV1:
    return PriorStateV1(state_version=0)


# Deprecated aliases — kept so existing imports resolve during I0 cutover.
def try_import_private_fixture_adapter() -> WholeBookOverviewEngineAdapter | None:
    try:
        return load_private_fixture_engine_adapter()
    except EngineLoadError:
        return None


def get_fixture_adapter(
    *, prefer_private: bool = True, force_fake: bool = False
) -> WholeBookOverviewEngineAdapter:
    """I0: always load Private fixture engine. ``force_fake`` is rejected."""

    del prefer_private
    if force_fake:
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
            "Public FakeFixtureAdapter was removed in STEP 2.3-I0; "
            "tests must load fixture-native-overview-v1 via Engine Loader.",
            {"engine_id": FIXTURE_ENGINE_ID},
        )
    return load_private_fixture_engine_adapter()
