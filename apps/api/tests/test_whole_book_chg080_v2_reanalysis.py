"""CHG-080: formal V2 reanalysis creates a new hierarchical run and preserves old results."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1
from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
    ENGINE_ID,
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
from app.narrative_core.whole_book_v2.result_origin import (
    detect_scaffold,
    product_flags_for_result,
    resolve_result_origin,
)
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


class QueueGateway:
    def __init__(self, items):
        self.items = list(items)
        self.calls = []
        self.disallow_local_merge = False
        self.deterministic_extraction = True

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


def _make_run(session, *, request_id: str, book=None, snap_id=None):
    if book is None:
        book, snap_id = seed_sample_s_book(session)
    run = create_whole_book_run_v1(
        session,
        book.id,
        snap_id,
        "whole_book_native",
        request_id,
        "formal",
    )
    run.provider_name = "fake"
    run.model_name = "fixture"
    session.commit()
    session.refresh(run)
    return book, snap_id, run


def test_reanalyse_creates_new_run_id_and_preserves_old_result(tmp_path):
    engine = make_engine(tmp_path, "chg080-reanalyse.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id, run1 = _make_run(session, request_id="chg080-a")
        from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
            _source_chapters,
        )

        chapters = _source_chapters(session, run1)
        out1 = execute_hierarchical_v2_pipeline_v1(
            session, int(run1.id), use_fake_gateway=QueueGateway(_payloads(chapters))
        )
        session.commit()
        assert out1["pipeline"] == "hierarchical_v2"
        old = WholeBookV2Repository(session).load_result(int(run1.id))
        assert old is not None
        old_dump = old.model_dump_json()

        book, snap_id, run2 = _make_run(
            session, request_id="chg080-b", book=book, snap_id=snap_id
        )
        assert int(run2.id) != int(run1.id)

        # Safe reuse: copy intermediates from old run into new run.
        copied = WholeBookV2Repository(session).copy_intermediates(
            source_run_id=int(run1.id), target_run_id=int(run2.id)
        )
        assert copied >= 0

        out2 = execute_hierarchical_v2_pipeline_v1(
            session,
            int(run2.id),
            use_fake_gateway=QueueGateway(_payloads(chapters)),
            force_full_reanalysis=False,
            previous_run_id=int(run1.id),
        )
        session.commit()
        assert out2["run_id"] == int(run2.id)
        assert out2["engine_id"] == ENGINE_ID

        # Old result still present and unchanged.
        still_old = WholeBookV2Repository(session).load_result(int(run1.id))
        assert still_old is not None
        assert still_old.model_dump_json() == old_dump
        new = WholeBookV2Repository(session).load_result(int(run2.id))
        assert new is not None
        assert int(new.analysis_metadata.run_id) == int(run2.id)


def test_force_full_reanalysis_skips_intermediate_copy_contract(tmp_path):
    engine = make_engine(tmp_path, "chg080-force.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id, run1 = _make_run(session, request_id="chg080-f1")
        from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
            _source_chapters,
        )

        chapters = _source_chapters(session, run1)
        execute_hierarchical_v2_pipeline_v1(
            session, int(run1.id), use_fake_gateway=QueueGateway(_payloads(chapters))
        )
        session.commit()

        _, _, run2 = _make_run(session, request_id="chg080-f2", book=book, snap_id=snap_id)
        out = execute_hierarchical_v2_pipeline_v1(
            session,
            int(run2.id),
            use_fake_gateway=QueueGateway(_payloads(chapters)),
            force_full_reanalysis=True,
            previous_run_id=int(run1.id),
        )
        session.commit()
        assert out["intermediates_reused"] == 0
        assert WholeBookV2Repository(session).load_result(int(run1.id)) is not None
        assert WholeBookV2Repository(session).load_result(int(run2.id)) is not None


def test_scaffold_origin_detection_and_product_flags():
    chapters = [
        SourceChapter(1000 + i, i, f"第{i}章", f"@林 chapter {i} chooses.", 77, "rev")
        for i in range(1, 4)
    ]
    result = WholeBookV2Engine(DeterministicPrimitiveExtractor(), window_size=3, overlap=0).run(
        run_id=9, book_id=1, title="scaffold", chapters=chapters
    )
    assert detect_scaffold(result) is True
    flags = product_flags_for_result(result)
    assert flags["needs_reanalysis"] is True
    assert flags["is_real_provider_result"] is False
    assert resolve_result_origin(result) in {
        "deterministic_local_merge",
        "deterministic_test",
        "unknown",
    }


def test_formal_paths_never_call_minimal_pipeline():
    import app.services.whole_book_free_background as bg
    import app.narrative_core.services.whole_book_free_product_v1_service as free_svc

    assert "execute_hierarchical_v2_pipeline_v1" in Path(bg.__file__).read_text(encoding="utf-8")
    assert "execute_minimal_pipeline_v1" not in Path(bg.__file__).read_text(encoding="utf-8")
    free_src = Path(free_svc.__file__).read_text(encoding="utf-8")
    assert "execute_hierarchical_v2_pipeline_v1" in free_src
    assert "execute_minimal_pipeline_v1(" not in free_src


def test_failed_reanalysis_preserves_old_result(tmp_path):
    engine = make_engine(tmp_path, "chg080-fail.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id, run1 = _make_run(session, request_id="chg080-ok")
        from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
            _source_chapters,
        )

        chapters = _source_chapters(session, run1)
        execute_hierarchical_v2_pipeline_v1(
            session, int(run1.id), use_fake_gateway=QueueGateway(_payloads(chapters))
        )
        session.commit()
        old = WholeBookV2Repository(session).load_result(int(run1.id))
        assert old is not None

        _, _, run2 = _make_run(session, request_id="chg080-bad", book=book, snap_id=snap_id)

        class BoomGateway:
            disallow_local_merge = True

            async def generate(self, provider, request):
                raise RuntimeError("provider down")

        try:
            execute_hierarchical_v2_pipeline_v1(
                session, int(run2.id), use_fake_gateway=BoomGateway()
            )
            session.commit()
            raised = False
        except Exception:
            session.rollback()
            raised = True
        assert raised
        # Old result remains.
        assert WholeBookV2Repository(session).load_result(int(run1.id)) is not None
