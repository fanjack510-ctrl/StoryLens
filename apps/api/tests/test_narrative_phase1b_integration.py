"""Phase 1B Integration: migrations 001–010 + Entity→Asset→Relation E2E.

Cross-module verification only. Does not call models, wire Pattern routes,
or start Phase 2 analysis engines.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Base,
    Book,
    BookSnapshot,
    Chapter,
    Paragraph,
)
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    AssetType,
    ConflictRefType,
    ConflictStatus,
    ConflictType,
    EntityType,
    EvidenceRole,
    RelationType,
    ReviewStatus,
    SnapshotStatus,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations import (
    MIGRATION_ANALYSIS_CONFLICTS,
    MIGRATION_NARRATIVE_ASSET_EVIDENCE,
    MIGRATION_NARRATIVE_ASSETS_VERSIONS,
    MIGRATION_NARRATIVE_ENTITIES_ALIASES,
    MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE,
    NARRATIVE_MIGRATION_ORDER,
    migration_checksum,
)
from app.narrative_core.migrations.runner import (
    SQL_006,
    SQL_007,
    SQL_008,
    SQL_009,
    SQL_010,
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.conflict_service import AnalysisConflictServiceImpl
from app.narrative_core.services.entity_service import NarrativeEntityServiceImpl
from app.narrative_core.services.pattern_projection import build_pattern_projection_input
from app.narrative_core.services.relation_service import NarrativeRelationServiceImpl
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _factory(tmp_path, name: str = "phase1b-int.db"):
    engine = _fk_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory, engine


def _seed_book(session: Session, *, suffix: str = "") -> Book:
    book = Book(
        title=f"Integration Book{suffix}",
        source_file_name=f"int{suffix}.txt",
        source_file_hash=f"int-hash{suffix}-{id(session)}"[:64],
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    for chapter_index, (title, paragraphs) in enumerate(
        [("第一章", ["甲段证据", "乙段"]), ("第二章", ["丙段"])],
        start=1,
    ):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=chapter_index,
            title=title,
            display_title=title,
            chapter_title=title,
            source_title_line=title,
            word_count=sum(len(p) for p in paragraphs),
        )
        session.add(chapter)
        session.flush()
        offset = 0
        for p_index, body in enumerate(paragraphs, start=1):
            session.add(
                Paragraph(
                    id=f"B{book.id:04d}-C{chapter_index:04d}-P{p_index:04d}",
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=p_index,
                    raw_text=body,
                    normalized_text=body,
                    char_start=offset,
                    char_end=offset + len(body),
                )
            )
            offset += len(body) + 1
    session.commit()
    return book


def _completed_snapshot(session: Session, book_id: int) -> BookSnapshot:
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book_id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED
    return snapshot


def _first_paragraph(snapshot: BookSnapshot):
    chapter = sorted(snapshot.chapters, key=lambda c: c.chapter_order)[0]
    paragraph = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)[0]
    return chapter, paragraph


def _attach_asset_support(
    assets: NarrativeAssetService,
    version_id: int,
    snapshot: BookSnapshot,
    chapter,
    paragraph,
) -> None:
    assets.attach_asset_evidence(
        version_id,
        book_snapshot_id=snapshot.id,
        snapshot_chapter_id=chapter.id,
        snapshot_paragraph_id=paragraph.id,
        paragraph_content_hash=paragraph.content_hash,
        start_offset=0,
        end_offset=max(1, paragraph.end_offset - paragraph.start_offset),
        evidence_role=EvidenceRole.SUPPORT,
    )


def _attach_relation_support(
    relations: NarrativeRelationServiceImpl,
    version_id: int,
    snapshot: BookSnapshot,
    chapter,
    paragraph,
) -> None:
    relations.attach_relation_evidence(
        version_id,
        book_snapshot_id=snapshot.id,
        snapshot_chapter_id=chapter.id,
        snapshot_paragraph_id=paragraph.id,
        paragraph_content_hash=paragraph.content_hash,
        start_offset=0,
        end_offset=max(1, paragraph.end_offset - paragraph.start_offset),
        evidence_role=EvidenceRole.SUPPORT.value,
    )


# ---------------------------------------------------------------------------
# A. Migrations 001–010
# ---------------------------------------------------------------------------


def test_migrations_001_to_010_order_checksum_idempotent(tmp_path) -> None:
    assert len(NARRATIVE_MIGRATION_ORDER) == 10
    engine = _fk_engine(f"sqlite:///{tmp_path / 'm010.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    apply_narrative_phase1bp_migrations(engine)  # idempotent

    tables = set(inspect(engine).get_table_names())
    for name in (
        "narrative_entities",
        "narrative_entity_aliases",
        "narrative_assets",
        "narrative_asset_versions",
        "narrative_asset_evidence",
        "narrative_relations",
        "narrative_relation_versions",
        "narrative_relation_evidence",
        "analysis_conflicts",
    ):
        assert name in tables

    expected_checksums = {
        MIGRATION_NARRATIVE_ENTITIES_ALIASES: migration_checksum(SQL_006),
        MIGRATION_NARRATIVE_ASSETS_VERSIONS: migration_checksum(SQL_007),
        MIGRATION_NARRATIVE_ASSET_EVIDENCE: migration_checksum(SQL_008),
        MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE: migration_checksum(SQL_009),
        MIGRATION_ANALYSIS_CONFLICTS: migration_checksum(SQL_010),
    }
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT migration_id, checksum FROM schema_migrations")
        ).fetchall()
    stored = {r[0]: r[1] for r in rows}
    for mid, expected in expected_checksums.items():
        assert stored[mid] == expected

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE schema_migrations SET checksum='deadbeef' "
                "WHERE migration_id=:m"
            ),
            {"m": MIGRATION_NARRATIVE_ASSET_EVIDENCE},
        )
    with pytest.raises(NarrativeCoreError) as exc:
        apply_narrative_phase1bp_migrations(engine)
    assert exc.value.code == NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH
    engine.dispose()


def test_upgrade_phase1a_db_to_010(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'legacy1a.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    source_file_name VARCHAR(500) NOT NULL,
                    source_file_hash VARCHAR(64) NOT NULL,
                    import_status VARCHAR(32) NOT NULL DEFAULT 'imported',
                    language VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
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
                    prompt_hash VARCHAR(64) NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL,
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
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
                "INSERT INTO books (id,title,source_file_name,source_file_hash,created_at) "
                "VALUES (1,'legacy','l.txt','lh','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs ("
                "id,task_type,subject_type,subject_id,provider,model,"
                "prompt_version,schema_version,input_hash,status,"
                "created_at,queued_at,started_at) VALUES "
                "(1,'scene_pipeline','chapter','1','local','m','p','s','i',"
                "'completed','2026-01-01','2026-01-01','2026-01-01')"
            )
        )
    apply_narrative_phase1p_migrations(engine)
    apply_narrative_phase1bp_migrations(engine)
    with engine.connect() as connection:
        run = connection.execute(
            text("SELECT status FROM analysis_runs WHERE id=1")
        ).fetchone()
        assert run is not None and run[0] == "completed"
        mid = connection.execute(
            text(
                "SELECT migration_id FROM schema_migrations "
                "WHERE migration_id=:m"
            ),
            {"m": MIGRATION_ANALYSIS_CONFLICTS},
        ).fetchone()
        assert mid is not None
    engine.dispose()


def test_sqlite_fk_pragma_and_integrity_check(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "fk-int.db")
    with factory() as session:
        book = _seed_book(session, suffix="-fk")
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.CLUE,
            title="FK asset",
            identity_fingerprint="clue:fk",
            book_snapshot_id=snapshot.id,
        )
        session.commit()
        snap_id = snapshot.id
        chapter_id = chapter.id
        paragraph_id = paragraph.id
        paragraph_hash = paragraph.content_hash

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        result = connection.scalar(text("PRAGMA integrity_check"))
        assert result == "ok"

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        with pytest.raises(Exception):
            connection.execute(
                text(
                    "INSERT INTO narrative_asset_evidence ("
                    "asset_version_id,book_snapshot_id,snapshot_chapter_id,"
                    "snapshot_paragraph_id,paragraph_content_hash,start_offset,"
                    "end_offset,evidence_role,evidence_label,created_at) VALUES "
                    "(99999,:sid,:cid,:pid,:hash,0,1,'support','','2026-01-01')"
                ),
                {
                    "sid": snap_id,
                    "cid": chapter_id,
                    "pid": paragraph_id,
                    "hash": paragraph_hash,
                },
            )

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(
                    text(
                        "INSERT INTO narrative_asset_versions ("
                        "asset_id,asset_type,title,summary,narrative_function,"
                        "attributes_json,confidence,importance,source_fingerprint,"
                        "origin_type,review_status,is_canonical,created_at) VALUES "
                        "(:aid,'clue','dup','','','{}',0,0,'','model','confirmed',1,'2026-01-01')"
                    ),
                    {"aid": created.asset.id},
                )
                session.execute(
                    text(
                        "INSERT INTO narrative_asset_versions ("
                        "asset_id,asset_type,title,summary,narrative_function,"
                        "attributes_json,confidence,importance,source_fingerprint,"
                        "origin_type,review_status,is_canonical,created_at) VALUES "
                        "(:aid,'clue','dup2','','','{}',0,0,'','model','confirmed',1,'2026-01-01')"
                    ),
                    {"aid": created.asset.id},
                )
    engine.dispose()


# ---------------------------------------------------------------------------
# B. Entity merge / casefold / superseded (smoke)
# ---------------------------------------------------------------------------


def test_entity_merge_superseded_smoke(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "entity-smoke.db")
    with factory() as session:
        book = _seed_book(session, suffix="-ent")
        entities = NarrativeEntityServiceImpl(session)
        source = entities.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="张三"
        )
        target = entities.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="张三丰"
        )
        alias = entities.add_alias_candidate(source.id, alias_text="三哥")
        entities.confirm_alias(alias.id)
        result = entities.merge_entities(source.id, target.id)
        session.commit()
        assert result.source.lifecycle_status == "superseded"
        assert result.source.superseded_by_entity_id == target.id
        found = entities.find_entity_by_alias(book.id, "三哥")
        assert found is not None
        assert found.entity.id == target.id
    engine.dispose()


# ---------------------------------------------------------------------------
# C. Entity→Asset→Relation E2E (main test)
# ---------------------------------------------------------------------------


def test_entity_asset_relation_e2e_lock_conflict_projection(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "e2e.db")
    with factory() as session:
        book = _seed_book(session, suffix="-e2e")
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        source_chapter_id = chapter.source_chapter_id
        assert source_chapter_id is not None

        run = RunStageService(session).create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
            book_id=book.id,
            book_snapshot_id=snapshot.id,
        )
        assert run.book_id == book.id
        assert run.book_snapshot_id == snapshot.id

        entities = NarrativeEntityServiceImpl(session)
        entity = entities.create_entity(
            book.id, entity_type=EntityType.CHARACTER, canonical_name="主角"
        )
        alias = entities.add_alias_candidate(entity.id, alias_text="他")
        entities.confirm_alias(alias.id)

        assets = NarrativeAssetService(session)
        relations = NarrativeRelationServiceImpl(session)
        conflicts = AnalysisConflictServiceImpl(session)

        entity_ids_json = json.dumps({"entity_ids": [entity.id]})

        asset1 = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.CLUE,
            title="线索甲",
            identity_fingerprint="clue:alpha",
            run_id=run.id,
            book_snapshot_id=snapshot.id,
            attributes_json=entity_ids_json,
        )
        _attach_asset_support(
            assets, asset1.version.id, snapshot, chapter, paragraph
        )
        assets.confirm_asset_version(asset1.version.id, actor="user")
        session.commit()
        assert assets.get_canonical_asset_version(asset1.asset.id).id == asset1.version.id

        asset2 = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="事件乙",
            identity_fingerprint="event:beta",
            run_id=run.id,
            book_snapshot_id=snapshot.id,
        )
        _attach_asset_support(
            assets, asset2.version.id, snapshot, chapter, paragraph
        )
        assets.confirm_asset_version(asset2.version.id, actor="user")
        session.commit()

        relation = relations.create_candidate_relation(
            book.id,
            source_asset_id=asset1.asset.id,
            target_asset_id=asset2.asset.id,
            relation_type=RelationType.CAUSES.value,
            identity_fingerprint="causes:alpha-beta",
            run_id=run.id,
            book_snapshot_id=snapshot.id,
        )
        rel_v1 = relations.get_relation_versions(relation.id)[0]
        _attach_relation_support(
            relations, rel_v1.id, snapshot, chapter, paragraph
        )
        relations.confirm_relation_version(rel_v1.id, make_canonical=True)
        session.commit()
        assert relations.get_canonical_relation_version(relation.id).id == rel_v1.id

        assets.lock_asset(asset1.asset.id)
        candidate = assets.add_asset_version(
            asset1.asset.id,
            asset_type=AssetType.CLUE,
            title="模型新解读",
            run_id=run.id,
            book_snapshot_id=snapshot.id,
            origin_type="model",
            review_status=ReviewStatus.CONFIRMED.value,
            attributes_json=entity_ids_json,
        )
        _attach_asset_support(
            assets, candidate.id, snapshot, chapter, paragraph
        )
        result = assets.confirm_asset_version(candidate.id, actor="model")
        session.commit()
        assert result.canonical_switched is False
        assert result.conflict_id is not None
        assert assets.get_canonical_asset_version(asset1.asset.id).id == asset1.version.id

        open_conflicts = conflicts.list_analysis_conflicts(
            book.id, status=ConflictStatus.OPEN.value
        )
        assert any(c.id == result.conflict_id for c in open_conflicts)
        assert open_conflicts[0].conflict_type == ConflictType.LOCKED_ASSET_VS_NEW_RUN.value

        assets.unlock_asset(asset1.asset.id)
        user_result = assets.confirm_asset_version(candidate.id, actor="user")
        session.commit()
        assert user_result.canonical_switched is True
        assert assets.get_canonical_asset_version(asset1.asset.id).id == candidate.id

        all_versions = assets.get_asset_versions(asset1.asset.id)
        assert len(all_versions) == 2
        old_evidence = assets.list_asset_version_evidence(asset1.version.id)
        assert len(old_evidence) >= 1

        projection = build_pattern_projection_input(session, book.id)
        assert projection.book_id == book.id
        assert len(projection.assets) == 2
        assert len(projection.relations) == 1

        proj_asset1 = next(a for a in projection.assets if a.asset_id == asset1.asset.id)
        assert proj_asset1.version_id == candidate.id
        assert proj_asset1.evidence_count >= 1
        assert entity.id in proj_asset1.entity_ids
        assert source_chapter_id in proj_asset1.chapter_ids
        assert paragraph.content_hash in proj_asset1.paragraph_hashes

        proj_rel = projection.relations[0]
        assert proj_rel.relation_id == relation.id
        assert proj_rel.relation_type == RelationType.CAUSES.value
        assert proj_rel.evidence_count >= 1
    engine.dispose()


# ---------------------------------------------------------------------------
# D. Consistency negatives
# ---------------------------------------------------------------------------


def test_version_evidence_snapshot_mismatch_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "neg-ev.db")
    with factory() as session:
        book = _seed_book(session, suffix="-neg")
        snap_a = _completed_snapshot(session, book.id)
        chapter_a, para_a = _first_paragraph(snap_a)

        live = session.scalar(select(Paragraph).where(Paragraph.book_id == book.id).limit(1))
        assert live is not None
        live.normalized_text = live.normalized_text + "改"
        live.raw_text = live.normalized_text
        session.commit()
        snap_b = _completed_snapshot(session, book.id)
        assert snap_b.id != snap_a.id
        chapter_b, para_b = _first_paragraph(snap_b)

        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.HOOK,
            title="快照不一致",
            identity_fingerprint="hook:mismatch",
            book_snapshot_id=snap_a.id,
        )
        with pytest.raises(NarrativeCoreError) as exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snap_b.id,
                snapshot_chapter_id=chapter_b.id,
                snapshot_paragraph_id=para_b.id,
                paragraph_content_hash=para_b.content_hash,
                start_offset=0,
                end_offset=1,
                evidence_role=EvidenceRole.SUPPORT,
            )
        assert exc.value.code == NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH

        assets.attach_asset_evidence(
            created.version.id,
            book_snapshot_id=snap_a.id,
            snapshot_chapter_id=chapter_a.id,
            snapshot_paragraph_id=para_a.id,
            paragraph_content_hash=para_a.content_hash,
            start_offset=0,
            end_offset=1,
            evidence_role=EvidenceRole.SUPPORT,
        )
    engine.dispose()


def test_run_version_snapshot_mismatch_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "neg-run.db")
    with factory() as session:
        book = _seed_book(session, suffix="-run")
        snap_a = _completed_snapshot(session, book.id)
        live = session.scalar(select(Paragraph).where(Paragraph.book_id == book.id).limit(1))
        assert live is not None
        live.normalized_text = live.normalized_text + "x"
        live.raw_text = live.normalized_text
        session.commit()
        snap_b = _completed_snapshot(session, book.id)
        assert snap_b.id != snap_a.id

        run = RunStageService(session).create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
            book_id=book.id,
            book_snapshot_id=snap_a.id,
        )
        assets = NarrativeAssetService(session)
        with pytest.raises(NarrativeCoreError) as exc:
            assets.create_candidate_asset(
                book.id,
                asset_type=AssetType.REVEAL,
                title="run/snap mismatch",
                identity_fingerprint="reveal:rs",
                run_id=run.id,
                book_snapshot_id=snap_b.id,
            )
        assert exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH
    engine.dispose()


def test_cross_book_conflict_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "neg-conf.db")
    with factory() as session:
        book1 = _seed_book(session, suffix="-c1")
        book2 = _seed_book(session, suffix="-c2")
        entities = NarrativeEntityServiceImpl(session)
        e1 = entities.create_entity(book1.id, entity_type=EntityType.CHARACTER, canonical_name="A")
        e2 = entities.create_entity(book2.id, entity_type=EntityType.CHARACTER, canonical_name="B")
        session.commit()

        conflicts = AnalysisConflictServiceImpl(session)
        with pytest.raises(NarrativeCoreError) as exc:
            conflicts.create_analysis_conflict(
                book1.id,
                conflict_type=ConflictType.ENTITY_IDENTITY.value,
                left_ref_type=ConflictRefType.ENTITY.value,
                left_ref_id=str(e1.id),
                right_ref_type=ConflictRefType.ENTITY.value,
                right_ref_id=str(e2.id),
                description="cross-book entity conflict",
            )
        assert exc.value.code == NarrativeCoreErrorCode.CONFLICT_CROSS_BOOK
    engine.dispose()


def test_canonical_without_support_evidence_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "neg-can.db")
    with factory() as session:
        book = _seed_book(session, suffix="-can")
        snapshot = _completed_snapshot(session, book.id)
        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.FORESHADOWING,
            title="无证据",
            identity_fingerprint="fore:none",
            book_snapshot_id=snapshot.id,
        )
        created.version.review_status = ReviewStatus.CONFIRMED.value
        session.flush()
        with pytest.raises(NarrativeCoreError) as exc:
            assets.confirm_asset_version(created.version.id, make_canonical=True)
        assert exc.value.code == NarrativeCoreErrorCode.CANONICAL_EVIDENCE_REQUIRED
    engine.dispose()


def test_context_only_evidence_cannot_canonical(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "neg-ctx.db")
    with factory() as session:
        book = _seed_book(session, suffix="-ctx")
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.CLUE,
            title="仅上下文",
            identity_fingerprint="clue:ctx",
            book_snapshot_id=snapshot.id,
        )
        assets.attach_asset_evidence(
            created.version.id,
            book_snapshot_id=snapshot.id,
            snapshot_chapter_id=chapter.id,
            snapshot_paragraph_id=paragraph.id,
            paragraph_content_hash=paragraph.content_hash,
            start_offset=0,
            end_offset=1,
            evidence_role=EvidenceRole.CONTEXT,
        )
        with pytest.raises(NarrativeCoreError) as exc:
            assets.confirm_asset_version(created.version.id)
        assert exc.value.code == NarrativeCoreErrorCode.CANONICAL_EVIDENCE_REQUIRED
    engine.dispose()
