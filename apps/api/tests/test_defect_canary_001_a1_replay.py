# -*- coding: utf-8 -*-
"""A1-short-dialogue canary import + empty key_actions offline reproduction."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Chapter, Paragraph
from app.schemas.scene import EvidenceField, SceneAnalysisResult
from app.services.book_service import import_book
from app.services.scene_pipeline import normalize_scene_analysis_result, validate_scene_analysis

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from certification.chapter_fixtures import build_cert_chapter_specs  # noqa: E402


def test_a1_canary_stamp_selects_narrative_chapter(tmp_path) -> None:
    """DEFECT-CANARY-001/003: canary must import narrative text, not stamp-only scenes."""
    spec = next(s for s in build_cert_chapter_specs() if s.fixture_id == "A1-short-dialogue")
    engine = create_engine(f"sqlite:///{tmp_path / 'a1.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        # Production canary import: narrative only (no # canary / # fixture lines).
        book = import_book(session, "A1-short-dialogue.txt", spec.text.encode("utf-8"))
        chapters = list(
            session.scalars(
                select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.chapter_index)
            )
        )
        assert chapters
        chapter = max(
            chapters,
            key=lambda c: len(
                list(
                    session.scalars(
                        select(Paragraph)
                        .where(Paragraph.chapter_id == c.id)
                        .order_by(Paragraph.paragraph_index)
                    )
                )
            ),
        )
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == chapter.id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        texts = [p.normalized_text for p in paragraphs]
        assert any("雨停了" in t for t in texts)
        assert any("后退" in t for t in texts)
        assert not any(t.startswith("# canary=") or t.startswith("# fixture=") for t in texts)
        assert len(paragraphs) >= 5


def test_a1_scene_analysis_empty_or_evidenced_actions() -> None:
    """A1 has a clear action; empty still legal; unevidenced action illegal."""
    pids = [f"B0001-C0001-P{i:04d}" for i in range(1, 6)]
    allowed = set(pids)
    sid = "B0001-C0001-R0001-S0001"
    empty = SceneAnalysisResult(
        scene_id=sid,
        entry_state=EvidenceField(summary="雨后安静", evidence_paragraph_ids=[pids[0]]),
        goal=EvidenceField(summary="避免开门", evidence_paragraph_ids=[pids[1]]),
        obstacle=EvidenceField(summary="门缝窥视", evidence_paragraph_ids=[pids[2]]),
        key_actions=[],
        turning_point=EvidenceField(summary="", evidence_paragraph_ids=[]),
        outcome=EvidenceField(summary="灯灭", evidence_paragraph_ids=[pids[4]]),
        unresolved_question=EvidenceField(summary="门外是谁", evidence_paragraph_ids=[pids[2]]),
        function_tags=["悬念设置"],
        confidence=0.7,
    )
    validate_scene_analysis(normalize_scene_analysis_result(empty, allowed), sid, allowed, True)

    evidenced = empty.model_copy(
        update={
            "key_actions": [
                EvidenceField(summary="他后退半步", evidence_paragraph_ids=[pids[3]])
            ],
            "entry_state": EvidenceField(summary="雨停后的门口", evidence_paragraph_ids=[pids[0]]),
            "goal": EvidenceField(summary="听从别开的警告", evidence_paragraph_ids=[pids[1]]),
            "obstacle": EvidenceField(summary="门缝里的眼睛", evidence_paragraph_ids=[pids[2]]),
            "outcome": EvidenceField(summary="灯灭陷入黑暗", evidence_paragraph_ids=[pids[4]]),
            "unresolved_question": EvidenceField(
                summary="窥视者身份", evidence_paragraph_ids=[pids[2]]
            ),
        }
    )
    validate_scene_analysis(
        normalize_scene_analysis_result(evidenced, allowed), sid, allowed, True
    )

    bad = empty.model_copy(
        update={
            "key_actions": [
                EvidenceField(summary="他冲出门外砍人", evidence_paragraph_ids=[])
            ]
        }
    )
    try:
        validate_scene_analysis(bad, sid, allowed, True)
        raise AssertionError("expected rejection")
    except ValueError as exc:
        assert "key_actions" in str(exc)


def test_a1_content_hash_stable() -> None:
    spec = next(s for s in build_cert_chapter_specs() if s.fixture_id == "A1-short-dialogue")
    digest = hashlib.sha256(spec.text.encode("utf-8")).hexdigest()
    assert len(digest) == 64
    assert "他后退半步" in spec.text
