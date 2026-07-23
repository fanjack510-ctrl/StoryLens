"""Agent E: Narrative Asset Evidence + Snapshot gateway directed tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, BookSnapshot, Chapter, Paragraph
from app.narrative_core.enums import AssetType, EvidenceRole, ReviewStatus, SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.migrations.runner import apply_narrative_phase1bp_migrations
from app.narrative_core.services.asset_evidence_service import NarrativeAssetEvidenceService
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.snapshot_repository import BookSnapshotRepositoryImpl
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _factory(tmp_path, name: str = "evidence.db"):
    engine = _fk_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory, engine


def _seed_book(session: Session, *, suffix: str = "") -> Book:
    book = Book(
        title=f"Evidence Book{suffix}",
        source_file_name=f"evidence{suffix}.txt",
        source_file_hash=f"evidence-hash{suffix}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    for chapter_index, body in enumerate(
        [("第一章", ["证据段落甲", "证据段落乙"]), ("第二章", ["证据段落丙"])],
        start=1,
    ):
        title, paragraphs = body
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
        for p_index, text_body in enumerate(paragraphs, start=1):
            session.add(
                Paragraph(
                    id=f"B{book.id:04d}-C{chapter_index:04d}-P{p_index:04d}",
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=p_index,
                    raw_text=text_body,
                    normalized_text=text_body,
                    char_start=offset,
                    char_end=offset + len(text_body),
                )
            )
            offset += len(text_body) + 1
    session.commit()
    return book


def _completed_snapshot(session: Session, book_id: int) -> BookSnapshot:
    service = BookSnapshotServiceImpl(session)
    snapshot = service.create_or_reuse_snapshot(book_id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED
    return snapshot


def _first_paragraph(snapshot: BookSnapshot):
    chapter = sorted(snapshot.chapters, key=lambda c: c.chapter_order)[0]
    paragraph = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)[0]
    return chapter, paragraph


def test_completed_snapshot_evidence_success(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        para_text = BookSnapshotServiceImpl(session).get_snapshot_paragraph_text(
            paragraph.id
        )

        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.CLUE,
            title="有证据的线索",
            identity_fingerprint="clue:ev1",
            book_snapshot_id=snapshot.id,
        )
        evidence = assets.attach_asset_evidence(
            created.version.id,
            book_snapshot_id=snapshot.id,
            snapshot_chapter_id=chapter.id,
            snapshot_paragraph_id=paragraph.id,
            paragraph_content_hash=paragraph.content_hash,
            start_offset=0,
            end_offset=len(para_text),
            evidence_role=EvidenceRole.SUPPORT,
            evidence_label="全文支持",
        )
        session.commit()
        assert evidence.id is not None
        assert assets.validate_asset_evidence(evidence.id) is True
        listed = assets.list_asset_version_evidence(created.version.id)
        assert len(listed) == 1
        excerpt = NarrativeAssetEvidenceService(session).restore_evidence_excerpt(
            evidence.id
        )
        assert excerpt == para_text
    engine.dispose()


def test_building_failed_invalid_snapshot_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        hashes_book = book.id
        completed = _completed_snapshot(session, hashes_book)
        chapter, paragraph = _first_paragraph(completed)

        repo = BookSnapshotRepositoryImpl(session)
        building = repo.create_snapshot_record(
            book.id,
            completed.content_hash + "-building",
            snapshot_status=SnapshotStatus.BUILDING,
        )
        failed = repo.create_snapshot_record(
            book.id,
            completed.content_hash + "-failed",
            snapshot_status=SnapshotStatus.FAILED,
        )
        invalid = repo.create_snapshot_record(
            book.id,
            completed.content_hash + "-invalid",
            snapshot_status=SnapshotStatus.INVALID,
        )
        session.commit()

        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.HOOK,
            title="坏快照",
            identity_fingerprint="hook:bad-snap",
        )

        for bad_id in (building.id, failed.id, invalid.id):
            with pytest.raises(NarrativeCoreError) as exc:
                assets.attach_asset_evidence(
                    created.version.id,
                    book_snapshot_id=bad_id,
                    snapshot_chapter_id=chapter.id,
                    snapshot_paragraph_id=paragraph.id,
                    paragraph_content_hash=paragraph.content_hash,
                    start_offset=0,
                    end_offset=1,
                    evidence_role=EvidenceRole.SUPPORT,
                )
            assert exc.value.code in {
                NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
            }
    engine.dispose()


def test_snapshot_book_mismatch(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book1 = _seed_book(session, suffix="-a")
        book2 = _seed_book(session, suffix="-b")
        snap2 = _completed_snapshot(session, book2.id)
        chapter, paragraph = _first_paragraph(snap2)

        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book1.id,
            asset_type=AssetType.EVENT,
            title="书不匹配",
            identity_fingerprint="event:mismatch",
        )
        with pytest.raises(NarrativeCoreError) as exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snap2.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash=paragraph.content_hash,
                start_offset=0,
                end_offset=1,
                evidence_role=EvidenceRole.CONTEXT,
            )
        assert exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH
    engine.dispose()


def test_paragraph_hash_mismatch_and_offset_oob(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        para_text = BookSnapshotServiceImpl(session).get_snapshot_paragraph_text(
            paragraph.id
        )

        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.CLUE,
            title="hash/offset",
            identity_fingerprint="clue:hash",
        )

        with pytest.raises(NarrativeCoreError) as hash_exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snapshot.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash="0" * 64,
                start_offset=0,
                end_offset=1,
                evidence_role=EvidenceRole.SUPPORT,
            )
        assert hash_exc.value.code == NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH

        with pytest.raises(NarrativeCoreError) as oob_exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snapshot.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash=paragraph.content_hash,
                start_offset=0,
                end_offset=len(para_text) + 5,
                evidence_role=EvidenceRole.SUPPORT,
            )
        assert oob_exc.value.code == NarrativeCoreErrorCode.EVIDENCE_OFFSET_OUT_OF_RANGE

        with pytest.raises(NarrativeCoreError) as neg_exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snapshot.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash=paragraph.content_hash,
                start_offset=5,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
            )
        assert neg_exc.value.code == NarrativeCoreErrorCode.EVIDENCE_OFFSET_OUT_OF_RANGE
    engine.dispose()


def test_evidence_role_validation(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.HOOK,
            title="role",
            identity_fingerprint="hook:role",
        )
        with pytest.raises(NarrativeCoreError) as exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snapshot.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash=paragraph.content_hash,
                start_offset=0,
                end_offset=1,
                evidence_role="narrator",
            )
        assert "invalid evidence_role" in str(exc.value)

        for role in (EvidenceRole.SUPPORT, EvidenceRole.CONTRADICT, EvidenceRole.CONTEXT):
            ev = assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snapshot.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash=paragraph.content_hash,
                start_offset=0,
                end_offset=1,
                evidence_role=role,
            )
            assert ev.evidence_role == role
    engine.dispose()


def test_old_snapshot_evidence_reproducible_after_live_edit(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        old_snap = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(old_snap)
        old_text = BookSnapshotServiceImpl(session).get_snapshot_paragraph_text(
            paragraph.id
        )

        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.FORESHADOWING,
            title="旧快照证据",
            identity_fingerprint="fore:old",
            book_snapshot_id=old_snap.id,
        )
        evidence = assets.attach_asset_evidence(
            created.version.id,
            book_snapshot_id=old_snap.id,
            snapshot_chapter_id=chapter.id,
            snapshot_paragraph_id=paragraph.id,
            paragraph_content_hash=paragraph.content_hash,
            start_offset=0,
            end_offset=len(old_text),
            evidence_role=EvidenceRole.SUPPORT,
        )
        session.commit()

        # Mutate live book text — old snapshot evidence must still restore.
        from sqlalchemy import select

        live = session.scalar(
            select(Paragraph).where(Paragraph.book_id == book.id).limit(1)
        )
        assert live is not None
        live.normalized_text = "正文已彻底改写"
        live.raw_text = "正文已彻底改写"
        session.commit()

        new_snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
        session.commit()
        assert new_snap.id != old_snap.id

        restored = NarrativeAssetEvidenceService(session).restore_evidence_excerpt(
            evidence.id
        )
        assert restored == old_text
        assert assets.validate_asset_evidence(evidence.id) is True
        assert calculate_text_hash(restored) == paragraph.content_hash
    engine.dispose()


def test_model_cannot_remove_confirmed_canonical_evidence(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.REVEAL,
            title="正式证据",
            identity_fingerprint="reveal:formal",
            book_snapshot_id=snapshot.id,
        )
        evidence = assets.attach_asset_evidence(
            created.version.id,
            book_snapshot_id=snapshot.id,
            snapshot_chapter_id=chapter.id,
            snapshot_paragraph_id=paragraph.id,
            paragraph_content_hash=paragraph.content_hash,
            start_offset=0,
            end_offset=1,
            evidence_role=EvidenceRole.SUPPORT,
            actor="user",
        )
        assets.confirm_asset_version(created.version.id, actor="user")
        session.commit()

        with pytest.raises(NarrativeCoreError) as exc:
            assets.remove_candidate_evidence(evidence.id, actor="model")
        assert exc.value.code == NarrativeCoreErrorCode.ASSET_LOCKED

        # Candidate evidence remains removable by model.
        cand = assets.add_asset_version(
            created.asset.id, asset_type=AssetType.REVEAL, title="候选"
        )
        cand_ev = assets.attach_asset_evidence(
            cand.id,
            book_snapshot_id=snapshot.id,
            snapshot_chapter_id=chapter.id,
            snapshot_paragraph_id=paragraph.id,
            paragraph_content_hash=paragraph.content_hash,
            start_offset=0,
            end_offset=1,
            evidence_role=EvidenceRole.CONTEXT,
            actor="model",
        )
        assets.remove_candidate_evidence(cand_ev.id, actor="model")
        assert assets.list_asset_version_evidence(cand.id) == []
    engine.dispose()


def test_locked_formal_evidence_not_model_modifiable(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        assets = NarrativeAssetService(session)
        created = assets.create_candidate_asset(
            book.id,
            asset_type=AssetType.EVENT,
            title="锁定正式",
            identity_fingerprint="event:lock-ev",
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
            evidence_role=EvidenceRole.SUPPORT,
            actor="user",
        )
        assets.confirm_asset_version(created.version.id, actor="user")
        assets.lock_asset(created.asset.id)

        with pytest.raises(NarrativeCoreError) as exc:
            assets.attach_asset_evidence(
                created.version.id,
                book_snapshot_id=snapshot.id,
                snapshot_chapter_id=chapter.id,
                snapshot_paragraph_id=paragraph.id,
                paragraph_content_hash=paragraph.content_hash,
                start_offset=0,
                end_offset=1,
                evidence_role=EvidenceRole.CONTRADICT,
                actor="model",
            )
        assert exc.value.code == NarrativeCoreErrorCode.ASSET_LOCKED
    engine.dispose()


def test_sqlite_fk_evidence_requires_version(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "fk_ev.db")
    with factory() as session:
        book = _seed_book(session)
        snapshot = _completed_snapshot(session, book.id)
        chapter, paragraph = _first_paragraph(snapshot)
        snap_id = snapshot.id
        chapter_id = chapter.id
        paragraph_id = paragraph.id
        paragraph_hash = paragraph.content_hash
        session.commit()

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        try:
            connection.execute(
                text(
                    "INSERT INTO narrative_asset_evidence ("
                    "asset_version_id,book_snapshot_id,snapshot_chapter_id,"
                    "snapshot_paragraph_id,paragraph_content_hash,start_offset,"
                    "end_offset,evidence_role,evidence_label,created_at) VALUES "
                    "(99999,:sid,:cid,:pid,:hash,0,1,'support','', '2026-01-01')"
                ),
                {
                    "sid": snap_id,
                    "cid": chapter_id,
                    "pid": paragraph_id,
                    "hash": paragraph_hash,
                },
            )
            raised = False
        except Exception:
            raised = True
    assert raised
    engine.dispose()
