"""Agent E: Narrative Asset / Version / Canonical / Lock directed tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, Chapter, NarrativeAsset, NarrativeAssetVersion, Paragraph
from app.narrative_core.asset_key import build_asset_key
from app.narrative_core.enums import AssetLifecycleStatus, AssetType, EvidenceRole, ReviewStatus, SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations import NARRATIVE_MIGRATION_ORDER, migration_checksum
from app.narrative_core.migrations.runner import (
    SQL_007,
    SQL_008,
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
    migrate_narrative_20260723_007_narrative_assets_versions,
    migrate_narrative_20260723_008_narrative_asset_evidence,
)
from app.db.models import AnalysisConflict
from app.narrative_core.services.asset_service import (
    AssetCanonicalConflictRequest,
    NarrativeAssetService,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _factory(tmp_path, name: str = "asset.db"):
    engine = _fk_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory, engine


def _seed_book(session: Session, *, suffix: str = "") -> Book:
    book = Book(
        title=f"Asset Book{suffix}",
        source_file_name=f"asset{suffix}.txt",
        source_file_hash=f"asset-hash{suffix}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        chapter_title="第一章",
        source_title_line="第一章",
        word_count=10,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="证据段落甲",
            normalized_text="证据段落甲",
            char_start=0,
            char_end=5,
        )
    )
    session.commit()
    return book


def _completed_snapshot(session: Session, book_id: int):
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book_id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED
    chapter = sorted(snapshot.chapters, key=lambda c: c.chapter_order)[0]
    paragraph = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)[0]
    return snapshot, chapter, paragraph


def _prepare_confirmable(
    session: Session,
    service: NarrativeAssetService,
    book: Book,
    version: NarrativeAssetVersion,
) -> None:
    snapshot, chapter, paragraph = _completed_snapshot(session, book.id)
    if version.book_snapshot_id is None:
        version.book_snapshot_id = snapshot.id
        session.flush()
    para_text = BookSnapshotServiceImpl(session).get_snapshot_paragraph_text(paragraph.id)
    service.attach_asset_evidence(
        version.id,
        book_snapshot_id=snapshot.id,
        snapshot_chapter_id=chapter.id,
        snapshot_paragraph_id=paragraph.id,
        paragraph_content_hash=paragraph.content_hash,
        start_offset=0,
        end_offset=min(2, len(para_text)),
        evidence_role=EvidenceRole.SUPPORT.value,
    )


# ---------------------------------------------------------------------------
# Migrations 007 / 008
# ---------------------------------------------------------------------------


def test_migration_007_008_order_and_checksum(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'mig_order.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)

    assert NARRATIVE_MIGRATION_ORDER[6] == "20260723_007_narrative_assets_versions"
    assert NARRATIVE_MIGRATION_ORDER[7] == "20260723_008_narrative_asset_evidence"

    migrate_narrative_20260723_007_narrative_assets_versions(engine)
    with engine.connect() as connection:
        rows = {
            r[0]: r[1]
            for r in connection.execute(
                text("SELECT migration_id, checksum FROM schema_migrations")
            )
        }
    assert "20260723_007_narrative_assets_versions" in rows
    assert rows["20260723_007_narrative_assets_versions"] == migration_checksum(SQL_007)
    assert "20260723_008_narrative_asset_evidence" not in rows

    migrate_narrative_20260723_008_narrative_asset_evidence(engine)
    with engine.connect() as connection:
        rows = {
            r[0]: r[1]
            for r in connection.execute(
                text("SELECT migration_id, checksum FROM schema_migrations")
            )
        }
    assert rows["20260723_008_narrative_asset_evidence"] == migration_checksum(SQL_008)

    names = set(inspect(engine).get_table_names())
    assert "narrative_assets" in names
    assert "narrative_asset_versions" in names
    assert "narrative_asset_evidence" in names

    with engine.connect() as connection:
        idx = connection.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='uq_narrative_asset_versions_one_canonical'"
            )
        ).fetchone()
    assert idx is not None
    engine.dispose()


def test_migration_007_008_idempotent(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'mig_idem.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    checksum_7 = migration_checksum(SQL_007)
    checksum_8 = migration_checksum(SQL_008)

    migrate_narrative_20260723_007_narrative_assets_versions(engine)
    migrate_narrative_20260723_008_narrative_asset_evidence(engine)
    migrate_narrative_20260723_007_narrative_assets_versions(engine)
    migrate_narrative_20260723_008_narrative_asset_evidence(engine)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT migration_id, checksum FROM schema_migrations "
                "WHERE migration_id IN "
                "('20260723_007_narrative_assets_versions',"
                " '20260723_008_narrative_asset_evidence')"
            )
        ).fetchall()
    assert len(rows) == 2
    by_id = {r[0]: r[1] for r in rows}
    assert by_id["20260723_007_narrative_assets_versions"] == checksum_7
    assert by_id["20260723_008_narrative_asset_evidence"] == checksum_8
    engine.dispose()


def test_upgrade_legacy_db_applies_007_008(tmp_path) -> None:
    """Old DB with Phase 1P tables only can upgrade to assets/evidence."""
    engine = _fk_engine(f"sqlite:///{tmp_path / 'legacy_up.db'}")
    # Minimal books table + phase1p migrations (no create_all of phase1b tables).
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
                    import_status VARCHAR(32) NOT NULL,
                    language VARCHAR(32) NOT NULL,
                    revision_number INTEGER NOT NULL,
                    import_diagnostics_json TEXT NOT NULL DEFAULT '{}',
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
                    execution_mode VARCHAR(16) NOT NULL,
                    analysis_mode VARCHAR(40) NOT NULL,
                    cloud_consent INTEGER NOT NULL,
                    sends_content_to_cloud INTEGER NOT NULL,
                    retryable INTEGER NOT NULL
                )
                """
            )
        )
    apply_narrative_phase1p_migrations(engine)
    migrate_narrative_20260723_007_narrative_assets_versions(engine)
    migrate_narrative_20260723_008_narrative_asset_evidence(engine)
    names = set(inspect(engine).get_table_names())
    assert "narrative_assets" in names
    assert "narrative_asset_evidence" in names
    engine.dispose()


# ---------------------------------------------------------------------------
# Asset / Version / Canonical / Lock
# ---------------------------------------------------------------------------


def test_create_candidate_not_auto_canonical(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        result = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="开场事件",
            summary="候选摘要",
            identity_fingerprint="event:opening:ch1",
        )
        session.commit()
        assert result.version.review_status == ReviewStatus.CANDIDATE
        assert result.version.is_canonical is False
        assert service.get_canonical_asset_version(result.asset.id) is None
    engine.dispose()


def test_add_version_and_confirm_canonical(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.HOOK,
            title="钩子A",
            identity_fingerprint="hook:a",
        )
        v2 = service.add_asset_version(
            created.asset.id,
            asset_type=AssetType.HOOK,
            title="钩子A-v2",
            summary="第二候选",
        )
        session.flush()
        assert v2.is_canonical is False
        _prepare_confirmable(session, service, book, v2)
        confirmed = service.confirm_asset_version(v2.id, make_canonical=True, actor="user")
        session.commit()
        assert confirmed.canonical_switched is True
        assert confirmed.version.is_canonical is True
        assert confirmed.version.review_status == ReviewStatus.CONFIRMED
        canon = service.get_canonical_asset_version(created.asset.id)
        assert canon is not None and canon.id == v2.id
        assert service._repo.count_canonical_flags(created.asset.id) == 1
    engine.dispose()


def test_correct_creates_new_version(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.CLUE,
            title="线索原版",
            identity_fingerprint="clue:1",
        )
        _prepare_confirmable(session, service, book, created.version)
        service.confirm_asset_version(created.version.id, actor="user")
        base_id = created.version.id
        corrected = service.correct_asset(
            created.asset.id,
            based_on_version_id=base_id,
            title="线索修正",
            summary="用户纠正",
            actor="user",
            make_canonical=False,
        )
        _prepare_confirmable(session, service, book, corrected.version)
        service.confirm_asset_version(corrected.version.id, actor="user")
        session.commit()
        assert corrected.version.id != base_id
        assert corrected.version.review_status == ReviewStatus.CORRECTED
        assert corrected.version.is_canonical is True
        prior = session.get(NarrativeAssetVersion, base_id)
        assert prior is not None
        assert prior.is_canonical is False
        assert prior.title == "线索原版"
        assert service._repo.count_canonical_flags(created.asset.id) == 1
    engine.dispose()


def test_rejected_cannot_be_canonical(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="将被拒绝",
            identity_fingerprint="event:rej",
        )
        service.reject_asset_version(created.version.id)
        with pytest.raises(NarrativeCoreError) as exc:
            service.confirm_asset_version(created.version.id, actor="user")
        assert exc.value.code == NarrativeCoreErrorCode.REJECTED_CANNOT_BE_CANONICAL
        assert service.get_canonical_asset_version(created.asset.id) is None
    engine.dispose()


def test_at_most_one_canonical_per_asset(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.GOAL,
            title="目标1",
            identity_fingerprint="goal:1",
        )
        v1 = created.version
        v2 = service.add_asset_version(
            created.asset.id, asset_type=AssetType.GOAL, title="目标2"
        )
        _prepare_confirmable(session, service, book, v1)
        _prepare_confirmable(session, service, book, v2)
        service.confirm_asset_version(v1.id, actor="user")
        service.confirm_asset_version(v2.id, actor="user")
        session.commit()
        assert service._repo.count_canonical_flags(created.asset.id) == 1
        canon = service.get_canonical_asset_version(created.asset.id)
        assert canon is not None and canon.id == v2.id
    engine.dispose()


def test_model_cannot_replace_user_confirmed_canonical(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.REVEAL,
            title="用户确认版",
            identity_fingerprint="reveal:1",
        )
        _prepare_confirmable(session, service, book, created.version)
        service.confirm_asset_version(created.version.id, actor="user")
        model_v = service.add_asset_version(
            created.asset.id,
            asset_type=AssetType.REVEAL,
            title="新模型版",
            origin_type="model",
        )
        _prepare_confirmable(session, service, book, model_v)
        # Model path: confirm as model after marking confirmed would be atypical;
        # simulate model trying to promote a confirmed-eligible version.
        model_v.review_status = ReviewStatus.CONFIRMED
        session.flush()
        result = service.confirm_asset_version(
            model_v.id, make_canonical=True, actor="model"
        )
        session.commit()
        assert result.canonical_switched is False
        assert isinstance(result.conflict_request, AssetCanonicalConflictRequest)
        canon = service.get_canonical_asset_version(created.asset.id)
        assert canon is not None and canon.id == created.version.id
    engine.dispose()


def test_locked_blocks_model_canonical_allows_candidate(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.CONFLICT,
            title="锁定资产",
            identity_fingerprint="conflict:lock",
        )
        _prepare_confirmable(session, service, book, created.version)
        service.confirm_asset_version(created.version.id, actor="user")
        service.lock_asset(created.asset.id)

        candidate = service.add_asset_version(
            created.asset.id,
            asset_type=AssetType.CONFLICT,
            title="锁定后新候选",
        )
        assert candidate.review_status == ReviewStatus.CANDIDATE

        candidate.review_status = ReviewStatus.CONFIRMED
        session.flush()
        _prepare_confirmable(session, service, book, candidate)
        result = service.confirm_asset_version(candidate.id, actor="model")
        assert result.canonical_switched is False
        assert result.conflict_request is not None
        assert result.conflict_request.reason == "asset_locked"
        assert result.conflict_id is not None
        conflict = session.get(AnalysisConflict, result.conflict_id)
        assert conflict is not None
        assert conflict.status == "open"
        canon = service.get_canonical_asset_version(created.asset.id)
        assert canon is not None and canon.id == created.version.id
    engine.dispose()


def test_stale_mark_clear_and_supersede(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        a = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.STORYLINE,
            title="主线A",
            identity_fingerprint="story:a",
        )
        b = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.STORYLINE,
            title="主线B",
            identity_fingerprint="story:b",
        )
        service.mark_asset_stale(a.asset.id, reason="snapshot drifted")
        assert a.asset.lifecycle_status == AssetLifecycleStatus.STALE
        assert a.asset.stale_reason == "snapshot drifted"
        # stale ≠ rejected
        assert a.version.review_status == ReviewStatus.CANDIDATE

        service.clear_asset_stale(a.asset.id)
        assert a.asset.lifecycle_status == AssetLifecycleStatus.ACTIVE
        assert a.asset.stale_at is None

        service.supersede_asset(a.asset.id, superseded_by_asset_id=b.asset.id)
        session.commit()
        assert a.asset.lifecycle_status == AssetLifecycleStatus.SUPERSEDED
        assert a.asset.superseded_by_asset_id == b.asset.id

        listed = service.list_assets(book.id)
        ids = {x.id for x in listed}
        assert b.asset.id in ids
        assert a.asset.id not in ids  # default excludes superseded

        listed_all = service.list_assets(book.id, include_superseded=True)
        assert a.asset.id in {x.id for x in listed_all}
    engine.dispose()


def test_asset_key_stable_and_book_isolated(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book1 = _seed_book(session, suffix="-1")
        book2 = _seed_book(session, suffix="-2")
        service = NarrativeAssetService(session)

        key1 = NarrativeAssetService.resolve_asset_key(
            book_id=book1.id,
            asset_type=AssetType.EVENT,
            identity_fingerprint="same-fingerprint",
        )
        key1b = NarrativeAssetService.resolve_asset_key(
            book_id=book1.id,
            asset_type=AssetType.EVENT,
            identity_fingerprint="same-fingerprint",
        )
        key2 = NarrativeAssetService.resolve_asset_key(
            book_id=book2.id,
            asset_type=AssetType.EVENT,
            identity_fingerprint="same-fingerprint",
        )
        assert key1 == key1b
        assert key1 != key2
        assert key1 == build_asset_key(
            book_id=book1.id,
            asset_type=AssetType.EVENT,
            stable_label="same-fingerprint",
        )

        r1 = service.create_candidate_asset(
            book1.id,
            asset_type=AssetType.EVENT,
            title="可变标题一",
            identity_fingerprint="same-fingerprint",
        )
        r2 = service.create_candidate_asset(
            book2.id,
            asset_type=AssetType.EVENT,
            title="可变标题二",
            identity_fingerprint="same-fingerprint",
        )
        session.commit()
        assert r1.asset.asset_key != r2.asset.asset_key
        assert r1.asset.book_id != r2.asset.book_id

        # Independent candidates without fingerprint do not force-merge.
        i1 = service.create_candidate_asset(
            book1.id,
            asset_type=AssetType.EVENT,
            title="无指纹1",
            independent=True,
        )
        i2 = service.create_candidate_asset(
            book1.id,
            asset_type=AssetType.EVENT,
            title="无指纹2",
            independent=True,
        )
        assert i1.asset.id != i2.asset.id
        assert i1.asset.asset_key != i2.asset.asset_key
    engine.dispose()


def test_concurrent_confirm_one_canonical(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "concurrent_canon.db")
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="并发确认",
            identity_fingerprint="event:concurrent",
        )
        v1 = created.version
        v2 = service.add_asset_version(
            created.asset.id, asset_type=AssetType.EVENT, title="并发B"
        )
        session.commit()
        asset_id = created.asset.id
        book_id = book.id
        v1_id, v2_id = v1.id, v2.id

    def _confirm(version_id: int) -> str:
        with factory() as s:
            svc = NarrativeAssetService(s)
            book = s.get(Book, book_id)
            version = s.get(NarrativeAssetVersion, version_id)
            assert book is not None and version is not None
            _prepare_confirmable(s, svc, book, version)
            result = svc.confirm_asset_version(version_id, actor="user")
            s.commit()
            return "switched" if result.canonical_switched else "skipped"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_confirm, v1_id), pool.submit(_confirm, v2_id)]
        outcomes = [f.result() for f in futures]
    assert "switched" in outcomes

    with factory() as session:
        service = NarrativeAssetService(session)
        assert service._repo.count_canonical_flags(asset_id) == 1
        # DB partial unique also holds
        rows = session.execute(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_id == asset_id,
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        ).scalars().all()
        assert len(rows) == 1
    engine.dispose()


def test_canonical_switch_rollback_on_failure(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "rollback.db")
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="回滚基线",
            identity_fingerprint="event:rollback",
        )
        _prepare_confirmable(session, service, book, created.version)
        service.confirm_asset_version(created.version.id, actor="user")
        session.commit()
        baseline_id = created.version.id

        rejected = service.add_asset_version(
            created.asset.id, asset_type=AssetType.EVENT, title="拒绝版"
        )
        service.reject_asset_version(rejected.id)
        with pytest.raises(NarrativeCoreError):
            service._try_switch_canonical(created.asset, rejected, actor="user")
        session.rollback()

        # Re-open and verify prior canonical intact.
        session.expire_all()
        with factory() as session2:
            svc2 = NarrativeAssetService(session2)
            canon = svc2.get_canonical_asset_version(created.asset.id)
            assert canon is not None and canon.id == baseline_id
            assert svc2._repo.count_canonical_flags(created.asset.id) == 1
    engine.dispose()


def test_sqlite_fk_and_integrity_asset_tables(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "fk_asset.db")
    with factory() as session:
        book = _seed_book(session)
        service = NarrativeAssetService(session)
        created = service.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="FK",
            identity_fingerprint="event:fk",
        )
        session.commit()
        asset_id = created.asset.id

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        try:
            connection.execute(
                text(
                    "INSERT INTO narrative_asset_versions ("
                    "asset_id,asset_type,title,summary,narrative_function,"
                    "attributes_json,confidence,importance,source_fingerprint,"
                    "origin_type,review_status,is_canonical,created_at) VALUES "
                    "(99999,'event','x','','','{}',0,0,'','model','candidate',0,"
                    "'2026-01-01')"
                )
            )
            raised = False
        except Exception:
            raised = True
    assert raised

    with factory() as session:
        # Unique (book_id, asset_key)
        asset = session.get(NarrativeAsset, asset_id)
        assert asset is not None
        with pytest.raises(Exception):
            session.add(
                NarrativeAsset(
                    book_id=asset.book_id,
                    asset_key=asset.asset_key,
                    lifecycle_status="active",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            session.flush()
        session.rollback()
    engine.dispose()
