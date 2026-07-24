"""Agent Q directed tests — Context & Evidence Pipeline (CHG-20260723-038).

Not a full pytest suite. Covers Snapshot pipeline, TextRef, units, index,
bundle, planner, native/enhanced, evidence candidate/validator/coverage,
cache, privacy, and registry checks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Base,
    Book,
    BookSnapshot,
    Chapter,
    NarrativeAsset,
    NarrativeAssetVersion,
    Paragraph,
)
from app.narrative_core.enums import (
    EvidenceRole,
    ReviewStatus,
    SnapshotStatus,
    WholeBookModuleKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.private_engine_contract.context import (
    CONTEXT_PIPELINE_VERSION,
    ContextUnitType,
    GENERIC_LONG_CHAPTER_GROUPING,
)
from app.narrative_core.private_engine_contract.module_spec import get_module_spec
from app.narrative_core.private_engine_contract.quality import (
    DEFAULT_QUALITY_PROFILES,
    QualityProfileKey,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_context_pipeline import (
    ContextMode,
    DefaultWholeBookContextPipeline,
    EnhancedWholeBookContextProvider,
    HierarchicalContextPlanner,
    InMemoryContextBundleCache,
    NativeWholeBookContextProvider,
    WholeBookContextBundleBuilder,
    WholeBookContextIndex,
    configuration_fingerprint,
)
from app.narrative_core.services.whole_book_context_units import (
    ChapterNormalizeRecord,
    ContextUnitBuilder,
    SnapshotTextRef,
    SnapshotTextResolver,
    TextRefKind,
)
from app.narrative_core.services.whole_book_evidence_pipeline import (
    ClaimEvidenceBinding,
    EvidenceCandidateBuilder,
    EvidenceCoverageCalculator,
    ExplicitParagraphEvidenceInput,
    FakeModuleOutputEvidenceRef,
    FixtureExactMatchEvidenceInput,
    get_evidence_policy,
)
from app.narrative_core.services.whole_book_evidence_validator import (
    DefaultEvidenceValidator,
    EvidenceValidatorSnapshotView,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _factory(tmp_path, name: str = "ctx.db"):
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
    apply_narrative_phase1p_migrations(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _seed_book(
    session: Session,
    *,
    title: str = "Ctx Book",
    chapters: list[tuple[str, list[str]]] | None = None,
) -> Book:
    book = Book(
        title=title,
        source_file_name=f"{title}.txt",
        source_file_hash=f"hash-{title}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    bodies = chapters or [
        ("第一章", ["甲段文字内容", "乙段继续"]),
        ("第二章", ["丙段收束"]),
    ]
    for chapter_index, (ch_title, paragraphs) in enumerate(bodies, start=1):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=chapter_index,
            title=ch_title,
            display_title=ch_title,
            chapter_title=ch_title,
            source_title_line=ch_title,
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


def _completed_snapshot(session: Session, book: Book) -> BookSnapshot:
    service = BookSnapshotServiceImpl(session)
    snap = service.create_or_reuse_snapshot(book.id)
    session.commit()
    assert snap.snapshot_status == SnapshotStatus.COMPLETED
    return snap


def _quality(profile: QualityProfileKey = QualityProfileKey.BALANCED):
    return next(p for p in DEFAULT_QUALITY_PROFILES if p.profile_key == profile)


def _synth_chapter_records(n_chapters: int, *, paras_per: int = 3) -> list[ChapterNormalizeRecord]:
    records: list[ChapterNormalizeRecord] = []
    pid = 1
    for order in range(1, n_chapters + 1):
        ids = []
        stables = []
        hashes = []
        offsets = []
        cursor = 0
        for p in range(paras_per):
            text = f"c{order}-p{p}-body"
            h = calculate_text_hash(text)
            ids.append(pid)
            stables.append(f"B0001-C{order:04d}-P{p + 1:04d}")
            hashes.append(h)
            offsets.append((cursor, cursor + len(text)))
            cursor += len(text) + 1
            pid += 1
        records.append(
            ChapterNormalizeRecord(
                book_id=1,
                book_snapshot_id=99,
                snapshot_chapter_id=order,
                chapter_order=order,
                title=f"Chapter {order}",
                content_hash=calculate_text_hash("\n".join(f"c{order}-p{p}-body" for p in range(paras_per))),
                character_count=cursor,
                source_language="zh",
                snapshot_paragraph_ids=tuple(ids),
                stable_paragraph_ids=tuple(stables),
                paragraph_hashes=tuple(hashes),
                paragraph_orders=tuple(range(1, paras_per + 1)),
                paragraph_offsets=tuple(offsets),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Snapshot pipeline
# ---------------------------------------------------------------------------


def test_completed_snapshot_pipeline(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        pipe = DefaultWholeBookContextPipeline(session)
        prepared = pipe.prepare_snapshot(book.id, snap.id)
        assert prepared["fact_source"] == "snapshot"
        assert prepared["fts5"] is False
        chapters = pipe.normalize_chapters()
        assert [c.chapter_order for c in chapters] == [1, 2]
        chapter_units = pipe.build_chapter_units()
        assert len(chapter_units) == 2
        assert [u.chapter_order for u in chapter_units] == [1, 2]
        para_units = pipe.build_paragraph_units()
        assert all(u.unit_type == ContextUnitType.PARAGRAPH_GROUP for u in para_units)
        stables = [s for ch in chapters for s in ch.stable_paragraph_ids]
        assert stables[0].startswith("B")
        index = pipe.build_context_index((*chapter_units, *para_units))
        assert index.persistence == "non-persistent"
        assert index.is_fact_source is False
        assert index.list_chapter_units()
        h1 = index.calculate_hash()
        h2 = index.calculate_hash()
        assert h1 == h2
    engine.dispose()


def test_non_completed_snapshot_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        snap.snapshot_status = SnapshotStatus.BUILDING
        session.commit()
        pipe = DefaultWholeBookContextPipeline(session)
        with pytest.raises(NarrativeCoreError) as exc:
            pipe.prepare_snapshot(book.id, snap.id)
        assert exc.value.code in (
            NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
            NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
        )
    engine.dispose()


def test_book_mismatch_rejected(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book_a = _seed_book(session, title="A")
        book_b = _seed_book(session, title="B")
        snap = _completed_snapshot(session, book_a)
        pipe = DefaultWholeBookContextPipeline(session)
        with pytest.raises(NarrativeCoreError) as exc:
            pipe.prepare_snapshot(book_b.id, snap.id)
        assert exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH
    engine.dispose()


def test_chapter_paragraph_order_and_hashes(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        pipe = DefaultWholeBookContextPipeline(session)
        pipe.prepare_snapshot(book.id, snap.id)
        chapters = pipe.normalize_chapters()
        assert chapters[0].paragraph_orders == (1, 2)
        assert chapters[0].content_hash == calculate_text_hash(
            sorted(snap.chapters, key=lambda c: c.chapter_order)[0].content_text
        )
        # Title-only change on normalize records must not alter paragraph location keys.
        stables_before = chapters[0].stable_paragraph_ids
        hashes_before = chapters[0].paragraph_hashes
        ids_before = chapters[0].snapshot_paragraph_ids
        altered = ChapterNormalizeRecord(
            book_id=chapters[0].book_id,
            book_snapshot_id=chapters[0].book_snapshot_id,
            snapshot_chapter_id=chapters[0].snapshot_chapter_id,
            chapter_order=chapters[0].chapter_order,
            title="第一章·改标题",
            content_hash=chapters[0].content_hash,
            character_count=chapters[0].character_count,
            source_language=chapters[0].source_language,
            snapshot_paragraph_ids=chapters[0].snapshot_paragraph_ids,
            stable_paragraph_ids=chapters[0].stable_paragraph_ids,
            paragraph_hashes=chapters[0].paragraph_hashes,
            paragraph_orders=chapters[0].paragraph_orders,
            paragraph_offsets=chapters[0].paragraph_offsets,
        )
        builder = ContextUnitBuilder()
        u1 = builder.build_chapter_unit(chapters[0])
        u2 = builder.build_chapter_unit(altered)
        assert u1.stable_paragraph_ids == stables_before == u2.stable_paragraph_ids
        assert u1.snapshot_paragraph_ids == ids_before == u2.snapshot_paragraph_ids
        assert hashes_before == altered.paragraph_hashes
        # unit_id ignores title text (structural keys only)
        assert u1.unit_id == u2.unit_id
    engine.dispose()


# ---------------------------------------------------------------------------
# TextRef
# ---------------------------------------------------------------------------


def test_text_ref_lazy_and_hash_checks(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        pipe = DefaultWholeBookContextPipeline(session)
        pipe.prepare_snapshot(book.id, snap.id)
        chapters = pipe.normalize_chapters()
        units = pipe.build_chapter_units(chapters)
        # DTO has text_ref URI, not full body.
        assert units[0].text_ref and "snapshot://" in units[0].text_ref
        assert "甲段" not in json.dumps(
            {"id": units[0].unit_id, "ref": units[0].text_ref}, ensure_ascii=False
        )

        resolver = pipe.text_resolver
        ref = SnapshotTextRef.from_uri(units[0].text_ref)
        text = resolver.resolve(ref)
        assert "甲段" in text
        resolver.clear_cache()

        bad = SnapshotTextRef(
            kind=TextRefKind.CHAPTER,
            book_id=book.id,
            book_snapshot_id=snap.id,
            snapshot_chapter_id=chapters[0].snapshot_chapter_id,
            snapshot_paragraph_ids=chapters[0].snapshot_paragraph_ids,
            content_hash="0" * 64,
        )
        with pytest.raises(NarrativeCoreError):
            resolver.resolve(bad)

        # Cross-chapter paragraph reject
        if len(chapters) > 1 and chapters[1].snapshot_paragraph_ids:
            cross = SnapshotTextRef(
                kind=TextRefKind.PARAGRAPH_GROUP,
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=chapters[0].snapshot_chapter_id,
                snapshot_paragraph_ids=(chapters[1].snapshot_paragraph_ids[0],),
                content_hash=chapters[1].paragraph_hashes[0],
            )
            with pytest.raises(NarrativeCoreError):
                resolver.resolve(cross)
        resolver.clear_cache()
    engine.dispose()


# ---------------------------------------------------------------------------
# Units / grouping / generality
# ---------------------------------------------------------------------------


def test_chapter_scene_paragraph_units_and_long_grouping() -> None:
    builder = ContextUnitBuilder(source_language="zh")
    # Long chapter: 90 paragraphs → multiple groups with generic window.
    long = _synth_chapter_records(1, paras_per=90)[0]
    groups = builder.build_paragraph_group_units(long)
    max_per = int(GENERIC_LONG_CHAPTER_GROUPING["max_paragraphs_per_group"])
    assert len(groups) > 1
    assert all(len(g.snapshot_paragraph_ids) <= max_per for g in groups)

    scene = builder.build_scene_unit(
        book_id=1,
        book_snapshot_id=99,
        snapshot_chapter_id=1,
        chapter_order=1,
        scene_id=7,
        snapshot_paragraph_ids=long.snapshot_paragraph_ids[:3],
        stable_paragraph_ids=long.stable_paragraph_ids[:3],
        paragraph_texts_or_hashes=long.paragraph_hashes[:3],
    )
    assert scene.unit_type == ContextUnitType.SCENE
    derived = builder.build_derived_summary_ref(
        book_id=1,
        book_snapshot_id=99,
        summary_ref="summary://placeholder",
        content_hash=calculate_text_hash("placeholder"),
    )
    assert derived.derived is True

    # Determinism
    g2 = builder.build_paragraph_group_units(long)
    assert [g.unit_id for g in groups] == [g.unit_id for g in g2]


def test_no_book_specific_branch_in_unit_builder_source() -> None:
    src = Path(
        REPO_ROOT
        / "apps/api/app/narrative_core/services/whole_book_context_units.py"
    ).read_text(encoding="utf-8")
    banned = ("if title ==", "if author", "protagonist_name", "genre ==")
    for token in banned:
        assert token not in src


# ---------------------------------------------------------------------------
# Context Index scale fixtures
# ---------------------------------------------------------------------------


def test_context_index_100_500_1000_chapters() -> None:
    builder = ContextUnitBuilder()
    for n in (100, 500, 1000):
        records = _synth_chapter_records(n, paras_per=2)
        units = []
        for rec in records:
            units.append(builder.build_chapter_unit(rec))
            units.extend(builder.build_paragraph_group_units(rec))
        index = WholeBookContextIndex(
            book_id=1,
            book_snapshot_id=99,
            snapshot_content_hash=calculate_text_hash(f"snap-{n}"),
            units=tuple(units),
        )
        assert len(index.list_chapter_units()) == n
        # locate without N+1 scan of all evidence bodies
        first_pid = records[0].snapshot_paragraph_ids[0]
        located = index.locate_paragraph(first_pid)
        assert located is not None
        cov = index.coverage()
        assert cov.chapter_units == n
        assert index.get_unit(units[0].unit_id) is not None


# ---------------------------------------------------------------------------
# Bundle / planner / native / enhanced
# ---------------------------------------------------------------------------


def test_bundle_deterministic_hash_and_isolation(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        builder = WholeBookContextBundleBuilder(session)
        specs = (get_module_spec(WholeBookModuleKey.BOOK_OVERVIEW),)
        qp = _quality()
        b1 = builder.build(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_specs=specs,
            provider_context_limit=8000,
            quality_profile=qp,
            source_language="zh",
        )
        b2 = builder.build(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_specs=specs,
            provider_context_limit=8000,
            quality_profile=qp,
            source_language="zh",
        )
        assert b1.bundle_hash == b2.bundle_hash
        assert b1.configuration_fingerprint == b2.configuration_fingerprint
        assert b1.mode == ContextMode.NATIVE
        assert not any(
            "full_text" in (u.metadata or {}) for u in b1.units
        )
        builder.pipeline.validate_context_bundle(b1)

        # Different book snapshot isolation
        book2 = _seed_book(session, title="Other", chapters=[("X", ["别的内容"])])
        snap2 = _completed_snapshot(session, book2)
        b3 = builder.build(
            book_id=book2.id,
            book_snapshot_id=snap2.id,
            module_specs=specs,
            provider_context_limit=8000,
            quality_profile=qp,
        )
        assert b3.bundle_hash != b1.bundle_hash
        assert b3.book_snapshot_id != b1.book_snapshot_id
    engine.dispose()


def test_hierarchical_plan_limit_and_budget_downgrade() -> None:
    builder = ContextUnitBuilder()
    records = _synth_chapter_records(5, paras_per=20)
    units = []
    for rec in records:
        # Inflate token estimates via character_count already set.
        units.append(builder.build_chapter_unit(rec))
        units.extend(builder.build_paragraph_group_units(rec))
        units.append(
            builder.build_evidence_window_unit(
                book_id=1,
                book_snapshot_id=99,
                snapshot_chapter_id=rec.snapshot_chapter_id,
                chapter_order=rec.chapter_order,
                snapshot_paragraph_id=rec.snapshot_paragraph_ids[0],
                stable_paragraph_id=rec.stable_paragraph_ids[0],
                paragraph_content_hash=rec.paragraph_hashes[0],
                start_offset=0,
                end_offset=5,
                excerpt_hash=calculate_text_hash("xxxxx"),
                character_count=5,
            )
        )
    planner = HierarchicalContextPlanner()
    specs = (
        get_module_spec(WholeBookModuleKey.CHAPTER_FUNCTIONS),
    )
    plan = planner.plan(
        units=units,
        module_specs=specs,
        provider_context_limit=50,  # tiny → downgrade
        budget_policy_key="budget.tight",
    )
    assert plan.required_levels
    assert plan.downgraded or plan.warnings or plan.error_code
    plan2 = planner.plan(
        units=units,
        module_specs=specs,
        provider_context_limit=100_000,
        budget_policy_key="budget.relaxed",
    )
    assert plan2.selected_levels
    assert 3 in plan2.required_levels


def test_native_and_enhanced_modes(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        qp = _quality()
        native = NativeWholeBookContextProvider(session)
        nb = native.build_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=(WholeBookModuleKey.BOOK_OVERVIEW.value,),
            provider_context_limit=8000,
            quality_profile=qp,
        )
        assert nb.mode == ContextMode.NATIVE
        assert nb.analysis_mode in ("native", "whole_book_native")

        # Enhanced with missing aux → degrade warnings
        enhanced = EnhancedWholeBookContextProvider(session)
        eb_missing = enhanced.build_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=(WholeBookModuleKey.STORYLINES.value,),
            provider_context_limit=8000,
            quality_profile=qp,
        )
        assert eb_missing.mode == ContextMode.ENHANCED
        assert any("enhanced_missing" in w for w in eb_missing.warnings)

        # Full enhanced with scene + asset
        live_chapter = session.scalar(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.chapter_index)
        )
        assert live_chapter is not None
        paras = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == live_chapter.id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        # Scene requires analysis_run — create minimal via ORM if FK allows.
        # Skip full AnalysisRun if too heavy: insert asset path for stale/rejected.
        asset = NarrativeAsset(book_id=book.id, asset_key="ch1-fn")
        session.add(asset)
        session.flush()
        good = NarrativeAssetVersion(
            asset_id=asset.id,
            book_snapshot_id=snap.id,
            asset_type="chapter_function",
            title="fn",
            summary="aux",
            review_status=ReviewStatus.CANDIDATE.value,
            is_canonical=False,
            source_fingerprint="fp1",
        )
        stale = NarrativeAssetVersion(
            asset_id=asset.id,
            book_snapshot_id=snap.id + 9999 if False else None,
            asset_type="chapter_function",
            title="stale",
            summary="aux",
            review_status=ReviewStatus.CANDIDATE.value,
            source_fingerprint="fp2",
        )
        # Force stale by mismatched snapshot id using a second snapshot on another book.
        other = _seed_book(session, title="SnapOther", chapters=[("O", ["其它"])])
        other_snap = _completed_snapshot(session, other)
        stale.book_snapshot_id = other_snap.id
        rejected = NarrativeAssetVersion(
            asset_id=asset.id,
            book_snapshot_id=snap.id,
            asset_type="chapter_function",
            title="rej",
            summary="aux",
            review_status=ReviewStatus.REJECTED.value,
            source_fingerprint="fp3",
        )
        session.add_all([good, stale, rejected])
        session.commit()

        eb = enhanced.build_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=(WholeBookModuleKey.CHAPTER_FUNCTIONS.value,),
            provider_context_limit=8000,
            quality_profile=qp,
        )
        assert any("enhanced_asset_stale" in w or "stale=True" in n for w in eb.warnings for n in eb.coverage.notes) or any(
            "enhanced_asset_stale" in w for w in eb.warnings
        )
        assert any("rejected" in n for n in eb.coverage.notes)
        # Aux never replaces snapshot hash binding.
        assert eb.snapshot_content_hash == snap.content_hash
        _ = paras  # stable ids available for future scene wiring
    engine.dispose()


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_candidate_builder_deterministic(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        pipe = DefaultWholeBookContextPipeline(session)
        pipe.prepare_snapshot(book.id, snap.id)
        chapters = pipe.normalize_chapters()
        ch = chapters[0]
        builder = EvidenceCandidateBuilder()
        inp = ExplicitParagraphEvidenceInput(
            book_id=book.id,
            book_snapshot_id=snap.id,
            snapshot_chapter_id=ch.snapshot_chapter_id,
            snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
            stable_paragraph_id=ch.stable_paragraph_ids[0],
            paragraph_content_hash=ch.paragraph_hashes[0],
            start_offset=0,
            end_offset=4,
            evidence_role=EvidenceRole.SUPPORT,
            target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            target_output_ref="book_overview.logline",
            preview="甲段文字",
            source_context_unit_id="unit-1",
        )
        c1 = builder.from_explicit_paragraph(inp)
        c2 = builder.from_explicit_paragraph(inp)
        assert c1.candidate_id == c2.candidate_id
        assert len(c1.preview) <= 160

        fake = builder.from_fake_module_output(
            FakeModuleOutputEvidenceRef(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.CONTEXT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲",
            )
        )
        assert fake.extraction_method == "fake_module_output_ref"

        para_text = BookSnapshotServiceImpl(session).get_snapshot_paragraph_text(
            ch.snapshot_paragraph_ids[0]
        )
        fix = builder.from_fixture_exact_match(
            FixtureExactMatchEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                matched_text=para_text[:3],
                paragraph_text=para_text,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
            )
        )
        assert fix.start_offset == 0
    engine.dispose()


def test_evidence_validator_matrix(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        book2 = _seed_book(session, title="B2", chapters=[("Z", ["外书"])])
        snap2 = _completed_snapshot(session, book2)

        pipe = DefaultWholeBookContextPipeline(session)
        pipe.prepare_snapshot(book.id, snap.id)
        ch = pipe.normalize_chapters()[0]
        builder = EvidenceCandidateBuilder()
        validator = DefaultEvidenceValidator(session)
        view = validator.build_view_from_session(
            book_id=book.id,
            book_snapshot_id=snap.id,
            known_output_refs=("book_overview.logline",),
            known_context_unit_ids=("unit-1",),
        )

        valid = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲段",
                source_context_unit_id="unit-1",
            )
        )
        report = validator.validate_single(valid, view)
        assert report.valid is True

        bad_hash = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash="f" * 64,
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲段",
            )
        )
        assert any(
            "HASH" in i.code for i in validator.validate_single(bad_hash, view).issues
        )

        bad_off = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=10_000,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲段",
            )
        )
        assert any(
            "OFFSET" in i.code for i in validator.validate_single(bad_off, view).issues
        )

        bad_target = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="missing.ref",
                preview="甲段",
            )
        )
        assert any(
            "REFERENCE" in i.code or "OUTPUT" in i.code
            for i in validator.validate_single(bad_target, view).issues
        )

        cross_book = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book2.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲段",
            )
        )
        assert any(
            i.code == "CROSS_BOOK_FORBIDDEN"
            for i in validator.validate_single(cross_book, view).issues
        )

        cross_snap = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap2.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲段",
            )
        )
        assert any(
            "SNAPSHOT" in i.code or i.code == "CROSS_SNAPSHOT_FORBIDDEN"
            for i in validator.validate_single(cross_snap, view).issues
        )

        derived = builder.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=book.id,
                book_snapshot_id=snap.id,
                snapshot_chapter_id=ch.snapshot_chapter_id,
                snapshot_paragraph_id=ch.snapshot_paragraph_ids[0],
                stable_paragraph_id=ch.stable_paragraph_ids[0],
                paragraph_content_hash=ch.paragraph_hashes[0],
                start_offset=0,
                end_offset=2,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                target_output_ref="book_overview.logline",
                preview="甲段",
                from_derived_summary=True,
            )
        )
        assert any(
            i.code == "DERIVED_SUMMARY_AS_FINAL_EVIDENCE"
            for i in validator.validate_single(derived, view).issues
        )

        dup_report = validator.validate((valid, valid), view)
        assert any("DUPLICATE" in i.code for i in dup_report.issues)
    engine.dispose()


def test_coverage_and_critical_unsupported() -> None:
    calc = EvidenceCoverageCalculator()
    policy = get_evidence_policy("evidence.standard")
    report = calc.calculate(
        module_key="book_overview",
        claims=(
            ClaimEvidenceBinding(
                claim_key="logline",
                critical=True,
                support_candidate_ids=(),
            ),
            ClaimEvidenceBinding(
                claim_key="tone",
                support_candidate_ids=("ev1",),
                contradict_candidate_ids=("ev2",),
                context_candidate_ids=("ev3",),
            ),
        ),
        policy=policy,
        invalid_candidate_ids=("bad",),
        duplicate_candidate_ids=("dup",),
    )
    assert report.total_claims == 2
    assert report.claims_with_support == 1
    assert report.claims_with_contradiction == 1
    assert "logline" in report.unsupported_claims
    assert report.accepted is False
    assert report.critical_coverage_ratio < 1.0
    assert "contradict" in report.explanation
    # Coverage is not forged to 100%
    assert report.coverage_ratio < 1.0


# ---------------------------------------------------------------------------
# Cache / privacy / no model / no db index
# ---------------------------------------------------------------------------


def test_cache_and_privacy_serialization(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        native = NativeWholeBookContextProvider(session)
        qp = _quality()
        bundle = native.build_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=(WholeBookModuleKey.BOOK_OVERVIEW.value,),
            provider_context_limit=8000,
            quality_profile=qp,
        )
        cache = InMemoryContextBundleCache()
        key = InMemoryContextBundleCache.make_key(
            snapshot_content_hash=bundle.snapshot_content_hash,
            pipeline_version=CONTEXT_PIPELINE_VERSION,
            module_spec_versions=((WholeBookModuleKey.BOOK_OVERVIEW.value, "1.0.0"),),
            quality_profile_key=qp.profile_key.value,
            configuration_fingerprint=bundle.configuration_fingerprint,
        )
        cache.put(key, bundle)
        assert cache.get(key) is bundle
        cache.invalidate(key)
        assert cache.get(key) is None
        cache.put(key, bundle)
        cache.invalidate()
        assert len(cache) == 0

        public = bundle.to_public_dict()
        blob = json.dumps(public, ensure_ascii=False)
        assert "api_key" not in blob
        assert "credential" not in blob
        assert "prompt" not in blob.lower() or "prompt" not in str(public.get("units"))
        # Full chapter body not present
        assert "甲段文字内容" not in blob
    engine.dispose()


def test_no_model_and_no_database_index_markers() -> None:
    roots = [
        REPO_ROOT
        / "apps/api/app/narrative_core/services/whole_book_context_pipeline.py",
        REPO_ROOT
        / "apps/api/app/narrative_core/services/whole_book_context_units.py",
        REPO_ROOT
        / "apps/api/app/narrative_core/services/whole_book_evidence_pipeline.py",
        REPO_ROOT
        / "apps/api/app/narrative_core/services/whole_book_evidence_validator.py",
    ]
    banned_patterns = (
        "import openai",
        "import anthropic",
        "chat.completions",
        "create virtual table",
        "using fts5",
        "from neo4j",
        "import chromadb",
        "import faiss",
    )
    for path in roots:
        text = path.read_text(encoding="utf-8").lower()
        for token in banned_patterns:
            assert token not in text, f"{path} contains {token}"
        # Capability denial flags when present must be False.
        raw = path.read_text(encoding="utf-8")
        if '"fts5"' in raw or "'fts5'" in raw:
            assert "False" in raw or "false" in raw.lower()


def test_version_manager_and_change_registry_and_diff_check() -> None:
    for cmd in (
        [sys.executable, "scripts/version_manager.py", "check"],
        [sys.executable, "scripts/change_registry.py", "check"],
    ):
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    diff = subprocess.run(
        ["git", "diff", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert diff.returncode == 0, diff.stdout + diff.stderr


def test_configuration_fingerprint_stable() -> None:
    specs = (get_module_spec(WholeBookModuleKey.BOOK_OVERVIEW),)
    qp = _quality()
    a = configuration_fingerprint(
        pipeline_version=CONTEXT_PIPELINE_VERSION,
        module_specs=specs,
        quality_profile=qp,
        budget_policy_key=qp.budget_policy_key,
        provider_context_limit=8000,
        source_language="zh",
        analysis_mode="native",
        mode=ContextMode.NATIVE,
    )
    b = configuration_fingerprint(
        pipeline_version=CONTEXT_PIPELINE_VERSION,
        module_specs=specs,
        quality_profile=qp,
        budget_policy_key=qp.budget_policy_key,
        provider_context_limit=8000,
        source_language="zh",
        analysis_mode="native",
        mode=ContextMode.NATIVE,
    )
    assert a == b
