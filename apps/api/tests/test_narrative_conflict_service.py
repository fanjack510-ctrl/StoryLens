"""Agent F: Analysis Conflict directed tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book
from app.narrative_core.enums import (
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


def test_create_open_resolve_dismiss(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _book(session)
        service = AnalysisConflictServiceImpl(session)
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.RELATION_CONFLICT.value,
            left_ref_type="relation",
            left_ref_id="1",
            right_ref_type="relation_version",
            right_ref_id="2",
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

        other = service.create_from_request(
            ConflictCreateRequest(
                book_id=book.id,
                conflict_type=ConflictType.EVIDENCE_STALE.value,
                left_ref_type="evidence",
                left_ref_id="9",
                right_ref_type="snapshot",
                right_ref_id="3",
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
        service = AnalysisConflictServiceImpl(session)
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN.value,
            left_ref_type="relation",
            left_ref_id="11",
            right_ref_type="run",
            right_ref_id="22",
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
        service = AnalysisConflictServiceImpl(session)
        long_body = "正文" * 400
        conflict = service.create_analysis_conflict(
            book.id,
            conflict_type=ConflictType.SNAPSHOT_MISMATCH.value,
            left_ref_type="snapshot",
            left_ref_id="1",
            right_ref_type="snapshot",
            right_ref_id="2",
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
