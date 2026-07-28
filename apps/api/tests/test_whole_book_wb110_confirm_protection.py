"""WB-1.10 — confirmed narrative asset protection tests."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import AnalysisConflict, NarrativeAssetVersion
from app.narrative_core.enums import ReviewStatus
from app.narrative_core.services.whole_book_confirm_protection_v1_service import (
    confirm_narrative_asset_v1,
    confirm_narrative_entity_v1,
    materialize_with_confirmed_protection_v1,
)
from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
    materialize_minimal_narrative_assets_v1,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from tests.whole_book_minimal_test_helpers import make_engine, prepare_sample_s_run


def test_candidate_can_update(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb110-candidate.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
            execute_minimal_entity_event_extraction_v1,
        )

        execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        first = materialize_minimal_narrative_assets_v1(session, run_id)
        second = materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        assert second["reused"] is True
        assert first["entity_count"] == second["entity_count"]
    engine.dispose()


def test_confirmed_same_signature_reused(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb110-reuse.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
            execute_minimal_entity_event_extraction_v1,
        )

        execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        version = session.scalar(
            select(NarrativeAssetVersion).where(NarrativeAssetVersion.is_canonical.is_(True))
        )
        assert version is not None
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        canonical_id = version.id
        attrs = json.loads(version.attributes_json or "{}")
        signature = attrs.get("signature", "sig-test")
        asset = version.asset
        run = get_run(session, run_id)
        row, new_version, reused, conflict = materialize_with_confirmed_protection_v1(
            session,
            book_id=book_id,
            run_id=run_id,
            snapshot_id=run.snapshot_id,
            asset_key=asset.asset_key,
            signature=signature,
            candidate_payload={"summary": version.summary},
            title=version.title,
            summary=version.summary,
            asset_type=version.asset_type,
            mapped_entities=[],
            window_id=1,
            core_locator={"snapshot_paragraph_id": 1, "start_offset": 0, "end_offset": 1},
        )
        session.commit()
        assert reused is True
        assert conflict is None
        canonical = session.get(NarrativeAssetVersion, canonical_id)
        assert canonical.review_status == ReviewStatus.CONFIRMED.value
    engine.dispose()


def test_confirmed_different_content_creates_conflict(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb110-conflict.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
            execute_minimal_entity_event_extraction_v1,
        )

        execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        version = session.scalar(
            select(NarrativeAssetVersion).where(NarrativeAssetVersion.is_canonical.is_(True))
        )
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        canonical_id = version.id
        asset = version.asset
        run = get_run(session, run_id)
        _row, _proposed, reused, conflict = materialize_with_confirmed_protection_v1(
            session,
            book_id=book_id,
            run_id=run_id,
            snapshot_id=run.snapshot_id,
            asset_key=asset.asset_key,
            signature="different-signature",
            candidate_payload={"summary": "changed"},
            title="changed title",
            summary="changed summary",
            asset_type=version.asset_type,
            mapped_entities=[],
            window_id=2,
            core_locator={"snapshot_paragraph_id": 1, "start_offset": 0, "end_offset": 2},
        )
        session.commit()
        assert reused is False
        assert conflict is not None
        canonical = session.get(NarrativeAssetVersion, canonical_id)
        assert canonical.review_status == ReviewStatus.CONFIRMED.value
        dup = session.scalar(
            select(AnalysisConflict).where(
                AnalysisConflict.book_id == book_id,
                AnalysisConflict.status == "open",
            )
        )
        assert dup is not None
    engine.dispose()


def test_confirm_entity_service(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb110-entity.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
            execute_minimal_entity_event_extraction_v1,
        )

        execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        materialize_minimal_narrative_assets_v1(session, run_id)
        session.commit()
        from app.db.models import NarrativeEntity

        entity = session.scalar(select(NarrativeEntity).where(NarrativeEntity.book_id == book_id))
        result = confirm_narrative_entity_v1(session, entity.id)
        session.commit()
        assert result["state"] == "confirmed"
        assert result["user_confirmed_at"]
