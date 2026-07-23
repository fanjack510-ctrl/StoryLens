"""Agent D: Narrative Entity / Alias directed tests (Phase 1B).

Scoped suite only — not full pytest / frontend / publish gates.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, Base, Book, BookSnapshot, NarrativeEntity, NarrativeEntityAlias
from app.narrative_core.enums import (
    AliasReviewStatus,
    AliasType,
    EntityLifecycleStatus,
    EntityType,
    SnapshotStatus,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations import (
    MIGRATION_NARRATIVE_ENTITIES_ALIASES,
    migration_checksum,
)
from app.narrative_core.migrations.runner import (
    SQL_006,
    apply_narrative_phase1p_migrations,
    migrate_narrative_20260723_006_narrative_entities_aliases,
)
from app.narrative_core.services.entity_repository import normalize_alias_text
from app.narrative_core.services.entity_service import NarrativeEntityServiceImpl
from app.narrative_core.services.migration_ledger import MigrationLedgerService


def _fk_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _factory(tmp_path, name: str = "entity.db"):
    engine = _fk_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _seed_book(session: Session, *, title: str = "Entity Book") -> Book:
    book = Book(
        title=title,
        source_file_name=f"{title}.txt",
        source_file_hash=f"hash-{title}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    return book


def _seed_run_and_snapshot(session: Session, book: Book) -> tuple[AnalysisRun, BookSnapshot]:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="local",
        model="test",
        prompt_version="1",
        schema_version="1",
        input_hash="in",
        prompt_hash="ph",
        status="completed",
        progress_current=1,
        progress_total=1,
        created_at=datetime.now(timezone.utc),
        queued_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        book_id=book.id,
    )
    session.add(run)
    session.flush()
    snapshot = BookSnapshot(
        book_id=book.id,
        content_hash="snap-hash",
        chapter_count=0,
        paragraph_count=0,
        character_count=0,
        snapshot_status=SnapshotStatus.COMPLETED,
        source_fingerprint="fp",
        created_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()
    return run, snapshot


# ---------------------------------------------------------------------------
# Migration 006
# ---------------------------------------------------------------------------


def test_migration_006_applies_and_registers_checksum(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'm006.db'}")
    # Minimal books table so FK DDL is valid on empty upgrade path.
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    author VARCHAR(255),
                    source_file_name VARCHAR(500) NOT NULL,
                    source_file_hash VARCHAR(64) NOT NULL,
                    import_status VARCHAR(32) NOT NULL DEFAULT 'ready',
                    language VARCHAR(32) NOT NULL DEFAULT 'zh',
                    revision_number INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_runs (
                    id INTEGER PRIMARY KEY,
                    task_type VARCHAR(100) NOT NULL,
                    subject_type VARCHAR(50) NOT NULL,
                    subject_id VARCHAR(100) NOT NULL,
                    provider VARCHAR(100) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    prompt_version VARCHAR(50) NOT NULL,
                    schema_version VARCHAR(50) NOT NULL,
                    input_hash VARCHAR(64) NOT NULL,
                    prompt_hash VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    progress_current INTEGER NOT NULL,
                    progress_total INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    queued_at DATETIME NOT NULL,
                    started_at DATETIME NOT NULL,
                    execution_mode VARCHAR(16) NOT NULL DEFAULT 'local',
                    analysis_mode VARCHAR(40) NOT NULL DEFAULT 'local',
                    cloud_consent INTEGER NOT NULL DEFAULT 0,
                    sends_content_to_cloud INTEGER NOT NULL DEFAULT 0,
                    retryable INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE book_snapshots (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    content_hash VARCHAR(64) NOT NULL,
                    chapter_count INTEGER NOT NULL DEFAULT 0,
                    paragraph_count INTEGER NOT NULL DEFAULT 0,
                    character_count INTEGER NOT NULL DEFAULT 0,
                    snapshot_status VARCHAR(32) NOT NULL DEFAULT 'building',
                    source_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
                """
            )
        )
    apply_narrative_phase1p_migrations(engine)
    migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    names = set(inspect(engine).get_table_names())
    assert "narrative_entities" in names
    assert "narrative_entity_aliases" in names
    ledger = MigrationLedgerService(engine)
    row = ledger.get_applied_migration(MIGRATION_NARRATIVE_ENTITIES_ALIASES)
    assert row is not None
    assert row["checksum"] == migration_checksum(SQL_006)
    index_names = {idx["name"] for idx in inspect(engine).get_indexes("narrative_entities")}
    assert "ix_narrative_entities_book_type" in index_names
    assert "ix_narrative_entities_book_normalized" in index_names
    engine.dispose()


def test_migration_006_idempotent(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    first = MigrationLedgerService(engine).get_applied_migration(
        MIGRATION_NARRATIVE_ENTITIES_ALIASES
    )
    migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    second = MigrationLedgerService(engine).get_applied_migration(
        MIGRATION_NARRATIVE_ENTITIES_ALIASES
    )
    assert first is not None and second is not None
    assert first["checksum"] == second["checksum"] == migration_checksum(SQL_006)
    engine.dispose()


def test_migration_006_upgrade_from_phase1a_db(tmp_path) -> None:
    """Old Phase 1A DB (001–005 applied, no 006 tables) upgrades cleanly."""
    engine = _fk_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    # Drop Phase 1B tables if create_all added them — simulate Phase 1A-only.
    with engine.begin() as connection:
        for table in (
            "narrative_entity_aliases",
            "narrative_entities",
            "narrative_asset_evidence",
            "narrative_asset_versions",
            "narrative_assets",
            "narrative_relation_evidence",
            "narrative_relation_versions",
            "narrative_relations",
            "analysis_conflicts",
        ):
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
        connection.execute(
            text(
                "DELETE FROM schema_migrations WHERE migration_id LIKE '20260723_00%'"
                " AND migration_id >= '20260723_006'"
            )
        )
    assert "narrative_entities" not in set(inspect(engine).get_table_names())
    migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    names = set(inspect(engine).get_table_names())
    assert "narrative_entities" in names
    assert "narrative_entity_aliases" in names
    row = MigrationLedgerService(engine).get_applied_migration(
        MIGRATION_NARRATIVE_ENTITIES_ALIASES
    )
    assert row is not None
    engine.dispose()


def test_migration_006_failure_does_not_register(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'fail.db'}")
    # Pre-register wrong checksum — re-apply must refuse and leave corrupt row.
    from app.narrative_core.migrations.runner import _ensure_schema_migrations_table

    _ensure_schema_migrations_table(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO schema_migrations "
                "(migration_id, checksum, app_version, applied_at) "
                "VALUES (:id, :checksum, '1.0.5', '2026-01-01')"
            ),
            {"id": MIGRATION_NARRATIVE_ENTITIES_ALIASES, "checksum": "deadbeef" * 8},
        )
    Base.metadata.create_all(engine)
    with pytest.raises(NarrativeCoreError) as exc_info:
        migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    assert exc_info.value.code == NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH
    row = MigrationLedgerService(engine).get_applied_migration(
        MIGRATION_NARRATIVE_ENTITIES_ALIASES
    )
    assert row is not None
    assert row["checksum"] == "deadbeef" * 8
    engine.dispose()


# ---------------------------------------------------------------------------
# Entity CRUD / lifecycle
# ---------------------------------------------------------------------------


def test_create_entities_of_different_types(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        a = svc.create_entity(book.id, entity_type=EntityType.CHARACTER, canonical_name="李明")
        b = svc.create_entity(book.id, entity_type=EntityType.LOCATION, canonical_name="青石镇")
        c = svc.create_entity(
            book.id, entity_type=EntityType.ORGANIZATION, canonical_name="青云门"
        )
        session.commit()
        assert a.entity_type == EntityType.CHARACTER
        assert b.entity_type == EntityType.LOCATION
        assert c.entity_type == EntityType.ORGANIZATION
        assert a.normalized_name == normalize_alias_text("李明")
        # Same book, same name, different entities allowed.
        twin = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="李明"
        )
        session.commit()
        assert twin.id != a.id
        assert twin.canonical_name == a.canonical_name
    engine.dispose()


def test_empty_canonical_name_fails(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        with pytest.raises(NarrativeCoreError) as exc_info:
            svc.create_entity(book.id, entity_type=EntityType.CHARACTER, canonical_name="  ")
        assert exc_info.value.code == NarrativeCoreErrorCode.ENTITY_INVALID_NAME
    engine.dispose()


def test_entity_lock_unlock_archive(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="赵青"
        )
        session.commit()
        locked = svc.lock_entity(entity.id)
        assert locked.is_locked is True
        assert locked.locked_at is not None
        locked_again = svc.lock_entity(entity.id)
        assert locked_again.is_locked is True
        unlocked = svc.unlock_entity(entity.id)
        assert unlocked.is_locked is False
        archived = svc.archive_entity(entity.id)
        assert archived.lifecycle_status == EntityLifecycleStatus.ARCHIVED
        # Soft archive retains row.
        assert svc.get_entity(entity.id).id == entity.id
    engine.dispose()


def test_supersede_entity_status_only(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.FACTION, canonical_name="黑风寨"
        )
        session.commit()
        superseded = svc.supersede_entity(entity.id)
        assert superseded.lifecycle_status == EntityLifecycleStatus.SUPERSEDED
        # No superseded_by column on model.
        assert not hasattr(NarrativeEntity, "superseded_by_entity_id")
    engine.dispose()


# ---------------------------------------------------------------------------
# Alias review / lock / lookup
# ---------------------------------------------------------------------------


def test_alias_candidate_confirm_reject_lock(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        run, snapshot = _seed_run_and_snapshot(session, book)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="苏晚"
        )
        session.commit()
        alias = svc.add_alias_candidate(
            entity.id,
            alias_text="晚晚",
            alias_type=AliasType.NICKNAME,
            source_run_id=run.id,
            source_snapshot_id=snapshot.id,
        )
        session.commit()
        assert alias.review_status == AliasReviewStatus.CANDIDATE
        assert alias.source_run_id == run.id
        assert alias.source_snapshot_id == snapshot.id
        # Canonical unchanged.
        assert svc.get_entity(entity.id).canonical_name == "苏晚"

        confirmed = svc.confirm_alias(alias.id)
        assert confirmed.review_status == AliasReviewStatus.CONFIRMED
        locked = svc.lock_alias(alias.id)
        assert locked.is_locked is True
        with pytest.raises(NarrativeCoreError) as exc_info:
            svc.reject_alias(alias.id)
        assert exc_info.value.code == NarrativeCoreErrorCode.ALIAS_LOCKED
        unlocked = svc.unlock_alias(alias.id)
        rejected = svc.reject_alias(unlocked.id)
        assert rejected.review_status == AliasReviewStatus.REJECTED
    engine.dispose()


def test_duplicate_normalized_alias_idempotent(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="陈舟"
        )
        session.commit()
        a1 = svc.add_alias_candidate(entity.id, alias_text="舟子")
        a2 = svc.add_alias_candidate(entity.id, alias_text="  舟子  ")
        session.commit()
        assert a1.id == a2.id
        assert normalize_alias_text("舟子") == normalize_alias_text("  舟子  ")
    engine.dispose()


def test_ambiguous_alias_across_entities(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        e1 = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="人物甲"
        )
        e2 = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="人物乙"
        )
        session.commit()
        a1 = svc.add_alias_candidate(e1.id, alias_text="少主")
        a2 = svc.add_alias_candidate(e2.id, alias_text="少主")
        svc.confirm_alias(a1.id)
        svc.confirm_alias(a2.id)
        session.commit()
        result = svc.find_entity_by_alias(book.id, "少主")
        assert result.status == "ambiguous"
        assert result.entity is None
        assert {e.id for e in result.entities} == {e1.id, e2.id}
    engine.dispose()


def test_rejected_alias_excluded_from_formal_match(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="林深"
        )
        session.commit()
        alias = svc.add_alias_candidate(entity.id, alias_text="深哥")
        svc.reject_alias(alias.id)
        session.commit()
        result = svc.find_entity_by_alias(book.id, "深哥")
        assert result.status == "none"
        # Candidate also excluded.
        alias2 = svc.add_alias_candidate(entity.id, alias_text="林兄")
        session.commit()
        assert svc.find_entity_by_alias(book.id, "林兄").status == "none"
        svc.confirm_alias(alias2.id)
        session.commit()
        unique = svc.find_entity_by_alias(book.id, "林兄")
        assert unique.status == "unique"
        assert unique.entity is not None
        assert unique.entity.id == entity.id
    engine.dispose()


def test_book_id_isolation(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book_a = _seed_book(session, title="BookA")
        book_b = _seed_book(session, title="BookB")
        svc = NarrativeEntityServiceImpl(session)
        ea = svc.create_entity(
            book_a.id, entity_type=EntityType.CHARACTER, canonical_name="共享名"
        )
        eb = svc.create_entity(
            book_b.id, entity_type=EntityType.CHARACTER, canonical_name="共享名"
        )
        aa = svc.add_alias_candidate(ea.id, alias_text="别称X")
        ab = svc.add_alias_candidate(eb.id, alias_text="别称X")
        svc.confirm_alias(aa.id)
        svc.confirm_alias(ab.id)
        session.commit()
        ra = svc.find_entity_by_alias(book_a.id, "别称X")
        rb = svc.find_entity_by_alias(book_b.id, "别称X")
        assert ra.status == "unique" and ra.entity is not None and ra.entity.id == ea.id
        assert rb.status == "unique" and rb.entity is not None and rb.entity.id == eb.id
        assert ea.id != eb.id
    engine.dispose()


def test_source_run_and_snapshot_preserved(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        run, snapshot = _seed_run_and_snapshot(session, book)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.OBJECT, canonical_name="玉佩"
        )
        alias = svc.add_alias_candidate(
            entity.id,
            alias_text="那块玉",
            source_run_id=run.id,
            source_snapshot_id=snapshot.id,
        )
        session.commit()
        loaded = session.get(NarrativeEntityAlias, alias.id)
        assert loaded is not None
        assert loaded.source_run_id == run.id
        assert loaded.source_snapshot_id == snapshot.id
    engine.dispose()


def test_normalization_preserves_cjk_and_digits(tmp_path) -> None:
    assert normalize_alias_text("  张三丰  ") == "张三丰"
    assert normalize_alias_text("Hero  42") == "hero 42"
    assert normalize_alias_text("甲1号") == "甲1号"
    assert "丰" in normalize_alias_text("张三丰")


# ---------------------------------------------------------------------------
# merge_entities boundary
# ---------------------------------------------------------------------------


def test_merge_entities_explicitly_unsupported(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        a = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="源"
        )
        b = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="目标"
        )
        alias = svc.add_alias_candidate(a.id, alias_text="源别名")
        svc.confirm_alias(alias.id)
        session.commit()
        with pytest.raises(NarrativeCoreError) as exc_info:
            svc.merge_entities(b.id, a.id)
        assert exc_info.value.code == NarrativeCoreErrorCode.ENTITY_MERGE_NOT_SUPPORTED
        # No mutation / rollback of pre-merge state.
        session.refresh(a)
        session.refresh(alias)
        assert a.lifecycle_status == EntityLifecycleStatus.ACTIVE
        assert alias.entity_id == a.id
        assert alias.review_status == AliasReviewStatus.CONFIRMED
    engine.dispose()


def test_merge_entities_failure_leaves_db_unchanged(tmp_path) -> None:
    """Transaction failure path: unsupported merge must not mutate rows."""
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        survivor = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="存活"
        )
        absorbed = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="吸收"
        )
        session.commit()
        try:
            with session.begin_nested():
                svc.merge_entities(survivor.id, absorbed.id)
        except NarrativeCoreError as exc:
            assert exc.code == NarrativeCoreErrorCode.ENTITY_MERGE_NOT_SUPPORTED
        session.expire_all()
        assert svc.get_entity(survivor.id).lifecycle_status == EntityLifecycleStatus.ACTIVE
        assert svc.get_entity(absorbed.id).lifecycle_status == EntityLifecycleStatus.ACTIVE
    engine.dispose()


# ---------------------------------------------------------------------------
# SQLite FK / integrity / concurrency
# ---------------------------------------------------------------------------


def test_sqlite_foreign_key_alias_requires_entity(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        session.commit()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(
                    text(
                        "INSERT INTO narrative_entity_aliases "
                        "(id, entity_id, alias_text, normalized_alias, alias_type, "
                        "review_status, is_locked, created_at, updated_at) "
                        "VALUES (1, 99999, 'x', 'x', 'display', 'candidate', 0, "
                        "'2026-01-01', '2026-01-01')"
                    )
                )
        # book_id FK on entities
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(
                    text(
                        "INSERT INTO narrative_entities "
                        "(id, book_id, entity_type, canonical_name, normalized_name, "
                        "lifecycle_status, is_locked, created_at, updated_at) "
                        "VALUES (1, 99999, 'character', 'x', 'x', 'active', 0, "
                        "'2026-01-01', '2026-01-01')"
                    )
                )
    engine.dispose()


def test_sqlite_unique_constraint_entity_normalized_alias(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="唯一约束"
        )
        session.commit()
        svc.add_alias_candidate(entity.id, alias_text="别名A")
        session.commit()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(
                    text(
                        "INSERT INTO narrative_entity_aliases "
                        "(entity_id, alias_text, normalized_alias, alias_type, "
                        "review_status, is_locked, created_at, updated_at) "
                        "VALUES (:eid, '别名A', :norm, 'display', 'candidate', 0, "
                        "'2026-01-01', '2026-01-01')"
                    ),
                    {"eid": entity.id, "norm": normalize_alias_text("别名A")},
                )
    engine.dispose()


def test_concurrent_alias_candidate_inserts(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "concurrent.db")
    with factory() as session:
        book = _seed_book(session)
        svc = NarrativeEntityServiceImpl(session)
        entity = svc.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="并发"
        )
        session.commit()
        entity_id = entity.id

    def _add(i: int) -> int:
        with factory() as s:
            local = NarrativeEntityServiceImpl(s)
            alias = local.add_alias_candidate(entity_id, alias_text="同名别称")
            s.commit()
            return alias.id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(_add, range(4)))
    assert len(set(ids)) == 1
    engine.dispose()
