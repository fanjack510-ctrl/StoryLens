"""WB-1.5 — materialization tests."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import NarrativeEntity, NarrativeEntityAlias, WholeBookCheckpoint
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
    materialize_minimal_narrative_assets_v1,
    normalize_entity_name_v1,
)
from tests.whole_book_minimal_test_helpers import make_engine, prepare_sample_s_run


def test_normalize_entity_name_strips_quotes() -> None:
    assert normalize_entity_name_v1("《林川》") == normalize_entity_name_v1("林川")


def test_linchuan_mrlin_merge(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb15-merge.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        execute_minimal_entity_event_extraction_v1(session, run_id)
        materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        entities = list(
            session.scalars(select(NarrativeEntity).where(NarrativeEntity.created_by == str(run_id))).all()
        )
        names = {e.canonical_name for e in entities}
        assert "林川" in names or "林先生" in names
        aliases = list(session.scalars(select(NarrativeEntityAlias)).all())
        alias_texts = {a.alias_text for a in aliases}
        assert "林先生" in alias_texts or "林川" in alias_texts
        assert len(entities) >= 3
    engine.dispose()


def test_repeat_materialization_no_growth(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb15-idem.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        execute_minimal_entity_event_extraction_v1(session, run_id)
        first = materialize_minimal_narrative_assets_v1(session, run_id)
        second = materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        assert first["asset_count"] == second["asset_count"]
        assert second["reused"] is True
    engine.dispose()


def test_checkpoint_has_no_body_text(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb15-chk.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        execute_minimal_entity_event_extraction_v1(session, run_id)
        materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        row = session.scalar(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.checkpoint_key == "minimal_asset_materialization_v1",
            )
        )
        assert row is not None
        payload = json.loads(row.checkpoint_payload_json)
        blob = json.dumps(payload)
        assert "林川" not in blob
    engine.dispose()
