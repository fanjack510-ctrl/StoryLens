"""CHG-078: formal Free create routes to hierarchical V2 — not minimal_pipeline_v1."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1
from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
    ENGINE_ID,
    ENGINE_VERSION,
    execute_hierarchical_v2_pipeline_v1,
)
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit,
    CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit,
    PacingSynthesisUnit,
    StorySynthesisUnit,
    SuspenseSynthesisUnit,
)
from app.narrative_core.whole_book_v2.engine import (
    DeterministicPrimitiveExtractor,
    SourceChapter,
    WholeBookV2Engine,
)
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


class QueueGateway:
    def __init__(self, items):
        self.items = list(items)
        self.calls = []

    async def generate(self, provider, request):
        self.calls.append((provider, request))
        item = self.items.pop(0)
        if isinstance(item, ModelResponse):
            return item
        return ModelResponse(
            text=json.dumps(item, ensure_ascii=False),
            model="fixture",
            finish_reason="stop",
            input_tokens=10,
            output_tokens=20,
        )


def _payloads(chapters: list[SourceChapter]):
    r = WholeBookV2Engine(DeterministicPrimitiveExtractor(), window_size=3, overlap=0).run(
        run_id=1, book_id=1, title="fixture", chapters=chapters
    )
    return [
        OverviewTypeSynthesisUnit(type_profile=r.type_profile, overview=r.overview).model_dump(
            mode="json"
        ),
        StorySynthesisUnit(story=r.story).model_dump(mode="json"),
        CharactersSynthesisUnit(characters=r.characters).model_dump(mode="json"),
        SuspenseSynthesisUnit(suspense=r.suspense).model_dump(mode="json"),
        PacingSynthesisUnit(pacing=r.pacing, chapters=r.chapters).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=r.assessment).model_dump(mode="json"),
    ]


def test_formal_pipeline_uses_hierarchical_v2_not_minimal(tmp_path):
    import app.services.whole_book_free_background as bg
    import app.narrative_core.services.whole_book_free_product_v1_service as free_svc

    bg_src = Path(bg.__file__).read_text(encoding="utf-8")
    assert "execute_hierarchical_v2_pipeline_v1" in bg_src
    assert "execute_minimal_pipeline_v1" not in bg_src

    free_src = Path(free_svc.__file__).read_text(encoding="utf-8")
    assert "execute_hierarchical_v2_pipeline_v1" in free_src
    assert "execute_minimal_pipeline_v1(" not in free_src

    engine = make_engine(tmp_path, "chg078-v2.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        run = create_whole_book_run_v1(
            session,
            book.id,
            snap_id,
            "whole_book_native",
            "chg078-formal-v2",
            "formal",
        )
        run.provider_name = "fake"
        run.model_name = "fixture"
        session.commit()
        session.refresh(run)

        from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
            _source_chapters,
        )

        chapters = _source_chapters(session, run)
        assert len(chapters) >= 1
        gateway = QueueGateway(_payloads(chapters))
        out = execute_hierarchical_v2_pipeline_v1(
            session, int(run.id), use_fake_gateway=gateway
        )
        session.commit()
        assert out["pipeline"] == "hierarchical_v2"
        assert out["engine_id"] == ENGINE_ID
        assert out["engine_version"] == ENGINE_VERSION
        assert out["provider_calls"] >= 1
        assert len(gateway.calls) >= 1
        assert "execute_minimal" not in str(out).lower()

        session.refresh(run)
        assert run.status == WholeBookRunStatus.completed.value
        assert run.engine_id == ENGINE_ID

        loaded = WholeBookV2Repository(session).load_result(int(run.id))
        assert loaded is not None
        assert loaded.schema_version == "whole-book-analysis-v2.0"
        assert loaded.characters.protagonist.stages
        assert loaded.pacing.points
        assert loaded.assessment.dimensions


def test_legacy_result_is_not_silently_promoted_to_v2(tmp_path):
    engine = make_engine(tmp_path, "chg078-legacy.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        run = create_whole_book_run_v1(
            session,
            book.id,
            snap_id,
            "whole_book_native",
            "chg078-legacy",
            "formal",
        )
        run.status = WholeBookRunStatus.completed.value
        run.engine_id = "whole_book_minimal_pipeline_v1"
        run.engine_version = "1.0.0"
        run.provider_name = "fake"
        run.model_name = "fixture"
        session.commit()
        assert WholeBookV2Repository(session).load_result(int(run.id)) is None
