"""Agent F: Analysis Conflict directed tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, NarrativeAsset
from app.narrative_core.enums import (
    ConflictRefType,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations.runner import apply_narrative_phase1bp_migrations
from app.narrative_core.services.conflict_service import (
    AnalysisConflictServiceImpl,
    ConflictCreateRequest,
    RESOLUTION_SCHEMA,
    RESOLUTION_VERSION,
    normalize_resolution_json,
)
from app.narrative_core.services.relation_service import NarrativeRelationServiceImpl


def _factory(tmp_path, name: str = "conflict.db"):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _book(session: Session) -> Book:
    book = Book(
        title="Conflict Book",
        source_file_name="c.txt",
        source_file_hash=f"c-hash-{id(session)}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.commit()
    return book


def _asset(session: Session, book_id: int, key: str) -> NarrativeAsset:
    asset = NarrativeAsset(
        book_id=book_id,
        asset_key=key,
        lifecycle_status="active",
        is_locked=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(asset)
    session.flush()
    return asset


def _relation_fixture(session: Session, book: Book):
    a = _asset(session, book.id, "na_conflict_a")
    b = _asset(session, book.id, "na_conflict_b")
    rel_service = NarrativeRelationServiceImpl(session)
    relation = rel_service.create_candidate_relation(
        book.id,
        source_asset_id=a.id,
        target_asset_id=b.id,
        relation_type="causes",
        identity_fingerprint="causes",
    )
    version = rel_service.get_relation_versions(relation.id)[0]
    session.commit()
    return relation, version


def test_create_open_resolve_dismiss(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _book(session)
        relation, version = _relation_fixture(session, book)
        service = AnalysisConflictServiceImpl(session)
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.RELATION_CONFLICT.value,
            left_ref_type=ConflictRefType.RELATION.value,
            left_ref_id=str(relation.id),
            right_ref_type=ConflictRefType.RELATION_VERSION.value,
            right_ref_id=str(version.id),
            description="candidate contradiction note",
            severity=ConflictSeverity.WARNING.value,
        )
        assert conflict.status == ConflictStatus.OPEN.value
        listed = service.list_analysis_conflicts(book.id, status=ConflictStatus.OPEN.value)
        assert len(listed) == 1
        assert service.get_analysis_conflict(conflict.id).id == conflict.id

        resolved = service.resolve_analysis_conflict(
            conflict.id,
            resolved_by="user",
            resolution_json={"decision": "keep_left"},
        )
        assert resolved.status == ConflictStatus.RESOLVED.value
        payload = json.loads(resolved.resolution_json)
        assert payload["schema"] == RESOLUTION_SCHEMA
        assert payload["version"] == RESOLUTION_VERSION
        assert payload["decision"] == "keep_left"

        with pytest.raises(NarrativeCoreError) as exc:
            service.resolve_analysis_conflict(
                conflict.id, resolved_by="user", resolution_json={}
            )
            assert exc.value.code == NarrativeCoreErrorCode.CONFLICT_ALREADY_CLOSED

        from app.db.models import BookSnapshot

        snapshot = BookSnapshot(
            book_id=book.id,
            content_hash="snap",
            chapter_count=0,
            paragraph_count=0,
            character_count=0,
            snapshot_status="completed",
            source_fingerprint="fp",
            created_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)
        session.flush()

        other = service.create_from_request(
            ConflictCreateRequest(
                book_id=book.id,
                conflict_type=ConflictType.EVIDENCE_STALE.value,
                left_ref_type=ConflictRefType.SNAPSHOT.value,
                left_ref_id=str(snapshot.id),
                right_ref_type=ConflictRefType.SNAPSHOT.value,
                right_ref_id=str(snapshot.id),
                description="stale evidence marker",
                severity=ConflictSeverity.INFO.value,
            )
        )
        dismissed = service.dismiss_analysis_conflict(
            other.id, resolved_by="system", resolution_json="{}"
        )
        assert dismissed.status == ConflictStatus.DISMISSED.value
        with pytest.raises(NarrativeCoreError) as exc:
            service.dismiss_analysis_conflict(
                other.id, resolved_by="system", resolution_json="{}"
            )
        assert exc.value.code == NarrativeCoreErrorCode.CONFLICT_ALREADY_CLOSED
    engine.dispose()


def test_legacy_alias_ref_type_mapped(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _book(session)
        from app.narrative_core.services.entity_service import NarrativeEntityServiceImpl

        entities = NarrativeEntityServiceImpl(session)
        entity = entities.create_entity(
            book.id, entity_type="character", canonical_name="Legacy"
        )
        alias = entities.add_alias_candidate(entity.id, alias_text="legacy-alias")
        session.commit()
        service = AnalysisConflictServiceImpl(session)
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.ENTITY_IDENTITY.value,
            left_ref_type="alias",
            left_ref_id=str(alias.id),
            right_ref_type=ConflictRefType.ENTITY.value,
            right_ref_id=str(entity.id),
            description="legacy alias mapped",
        )
        assert conflict.left_ref_type == ConflictRefType.ENTITY_ALIAS.value
    engine.dispose()


def test_legacy_evidence_ref_type_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _book(session)
        service = AnalysisConflictServiceImpl(session)
        with pytest.raises(NarrativeCoreError) as exc:
            service.create_analysis_conflict(
                book.id,
                conflict_type=ConflictType.EVIDENCE_STALE.value,
                left_ref_type="evidence",
                left_ref_id="1",
                right_ref_type=ConflictRefType.SNAPSHOT.value,
                right_ref_id="1",
            )
        assert exc.value.code == NarrativeCoreErrorCode.CONFLICT_REF_INVALID
    engine.dispose()


def test_resolution_json_schema_version_required(tmp_path) -> None:
    normalized = normalize_resolution_json("{}")
    data = json.loads(normalized)
    assert data["schema"] == RESOLUTION_SCHEMA
    assert data["version"] == RESOLUTION_VERSION

    with pytest.raises(ValueError):
        normalize_resolution_json('{"schema":"wrong","version":"1"}')

    with pytest.raises(ValueError):
        normalize_resolution_json("[]")


def test_blocking_not_auto_resolved(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _book(session)
        relation, version = _relation_fixture(session, book)
        service = AnalysisConflictServiceImpl(session)
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN.value,
            left_ref_type=ConflictRefType.RELATION.value,
            left_ref_id=str(relation.id),
            right_ref_type=ConflictRefType.RELATION_VERSION.value,
            right_ref_id=str(version.id),
            description="locked vs new run",
            severity=ConflictSeverity.BLOCKING.value,
        )
        session.commit()
        # Creating a blocking conflict must leave it open — no auto decision.
        assert conflict.status == ConflictStatus.OPEN.value
        open_rows = service.list_analysis_conflicts(
            book.id,
            status=ConflictStatus.OPEN.value,
            severity=ConflictSeverity.BLOCKING.value,
        )
        assert len(open_rows) == 1
        assert open_rows[0].resolved_at is None
        assert open_rows[0].resolved_by is None
    engine.dispose()


def test_conflict_description_not_full_body_and_no_delete(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _book(session)
        from app.db.models import BookSnapshot

        s1 = BookSnapshot(
            book_id=book.id,
            content_hash="a",
            chapter_count=0,
            paragraph_count=0,
            character_count=0,
            snapshot_status="completed",
            source_fingerprint="fp",
            created_at=datetime.now(timezone.utc),
        )
        s2 = BookSnapshot(
            book_id=book.id,
            content_hash="b",
            chapter_count=0,
            paragraph_count=0,
            character_count=0,
            snapshot_status="completed",
            source_fingerprint="fp2",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([s1, s2])
        session.flush()
        service = AnalysisConflictServiceImpl(session)
        long_body = "正文" * 400
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.SNAPSHOT_MISMATCH.value,
            left_ref_type=ConflictRefType.SNAPSHOT.value,
            left_ref_id=str(s1.id),
            right_ref_type=ConflictRefType.SNAPSHOT.value,
            right_ref_id=str(s2.id),
            description=long_body,
        )
        assert len(conflict.description) <= 500
        # No physical delete API — row remains after dismiss.
        service.dismiss_analysis_conflict(
            conflict.id, resolved_by="user", resolution_json={"note": "noise"}
        )
        session.commit()
        still = service.get_analysis_conflict(conflict.id)
        assert still.status == ConflictStatus.DISMISSED.value
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM analysis_conflicts WHERE id=:id"),
                {"id": conflict.id},
            ).scalar()
        assert count == 1
    engine.dispose()
