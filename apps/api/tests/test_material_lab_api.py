# -*- coding: utf-8 -*-
"""素材库落库层与路由的测试：跑一本合成书，验证五张表的行为与接口形状。"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.material_lab_models import (
    MaterialLabAtom,
    MaterialLabEvidence,
    MaterialLabMaterial,
    MaterialLabPattern,
    MaterialLabRun,
)
from app.db.models import Base, Book, Chapter, Paragraph
from app.db.session import get_db
from app.main import create_app
from app.narrative_core.material_lab.service import (
    MaterialLabError,
    run_material_lab,
)
from app.narrative_core.migrations.runner import apply_narrative_migrations

# 与 test_material_lab_bridge 同款的悬疑合成文本：信号词密度足够触发抽取。
_SCENE = (
    "陈默推开档案室的门，昨天的卷宗还摊在桌上。\n"
    "他发现一枚戒指压在案件记录下面，来历不明，档案里没有登记。\n"
    "死者的邻居说三天前听到过争吵，可笔录上写的是当晚无人在家。\n"
    "刑警队里没人能解释这枚戒指为什么会出现在这里，线索对不上。\n"
    "陈默决定调查下去，嫌疑人交代的时间和监控完全不符，真相还埋着。\n"
) * 6


def _seed_book(session, *, book_id: int = 1, chapters: int = 3) -> None:
    session.add(Book(
        id=book_id, title=f"测试书{book_id}", source_file_name=f"b{book_id}.txt",
        source_file_hash=f"{book_id:064d}",
    ))
    session.flush()
    pid = 0
    for order in range(1, chapters + 1):
        ch = Chapter(
            book_id=book_id, chapter_index=order, title=f"第{order}章",
        )
        session.add(ch)
        session.flush()
        # 每章两段，段落文本各带一次场景块
        for j, txt in enumerate((_SCENE, _SCENE.replace("戒指", "怀表"))):
            pid += 1
            session.add(Paragraph(
                id=f"p{book_id:02d}{pid:04d}", book_id=book_id, chapter_id=ch.id,
                paragraph_index=j, raw_text=txt, normalized_text=txt,
                char_start=0, char_end=len(txt),
            ))
    session.commit()


@pytest.fixture()
def db_session():
    path = os.path.join(tempfile.mkdtemp(), "material_lab.db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    apply_narrative_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture()
def client(db_session):
    _seed_book(db_session)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


# ------------------------------------------------------------- service 层
def test_run_persists_all_five_tables(db_session):
    _seed_book(db_session)
    result = run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()

    assert result["materials"] > 0
    assert result["genre_source"] == "user"
    for model in (MaterialLabRun, MaterialLabPattern, MaterialLabAtom,
                  MaterialLabEvidence, MaterialLabMaterial):
        assert db_session.scalar(select(func.count()).select_from(model)) > 0
    # 落库数与返回数一致
    assert db_session.scalar(
        select(func.count()).select_from(MaterialLabMaterial)
    ) == result["materials"]


def test_rerun_replaces_instead_of_duplicating(db_session):
    _seed_book(db_session)
    first = run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()
    second = run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()

    assert second["materials"] == first["materials"]
    assert db_session.scalar(
        select(func.count()).select_from(MaterialLabMaterial)
    ) == first["materials"]
    # run 历史保留两条
    assert db_session.scalar(select(func.count()).select_from(MaterialLabRun)) == 2


def test_pattern_stats_and_primary_variants(db_session):
    _seed_book(db_session)
    run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()

    patterns = list(db_session.scalars(select(MaterialLabPattern)))
    active = [p for p in patterns if p.variant_count > 0]
    assert active, "至少归出一个模式簇"
    for p in active:
        n = db_session.scalar(
            select(func.count()).select_from(MaterialLabMaterial)
            .where(MaterialLabMaterial.pattern_id == p.id)
        )
        assert n == p.variant_count
        primaries = db_session.scalar(
            select(func.count()).select_from(MaterialLabMaterial)
            .where(MaterialLabMaterial.pattern_id == p.id,
                   MaterialLabMaterial.is_primary_variant == 1)
        )
        assert primaries == 1, "每个簇恰好一条展示代表"


def test_quality_scores_are_populated(db_session):
    _seed_book(db_session)
    run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()
    scores = list(db_session.scalars(select(MaterialLabMaterial.quality_score)))
    assert all(0 <= s <= 100 for s in scores)
    assert any(s > 0 for s in scores)


def test_auto_genre_detection_records_source(db_session):
    _seed_book(db_session)
    result = run_material_lab(db_session, 1)  # 不指定类型
    assert result["genre_slug"] == "xuanyi"
    assert result["genre_source"] == "auto"
    assert result["genre_confidence"] > 0


def test_unknown_book_and_unknown_genre_fail_cleanly(db_session):
    _seed_book(db_session)
    with pytest.raises(MaterialLabError) as e1:
        run_material_lab(db_session, 999)
    assert e1.value.code == "MATERIAL_LAB_BOOK_NOT_FOUND"
    with pytest.raises(MaterialLabError) as e2:
        run_material_lab(db_session, 1, genre_slug="不存在的类型")
    assert e2.value.code == "MATERIAL_LAB_UNKNOWN_GENRE"


# --------------------------------------------------------------- 路由层
def test_api_run_then_summary_and_listing(client):
    run = client.post("/api/v1/material-lab/books/1/run", json={"genre_slug": "xuanyi"})
    assert run.status_code == 200
    body = run.json()
    assert body["materials"] > 0

    summary = client.get("/api/v1/material-lab/books/1/summary").json()
    assert summary["material_count"] == body["materials"]
    assert summary["last_run"]["status"] == "done"
    assert summary["by_category"], "类目分布带中文标签"
    assert all("label" in c for c in summary["by_category"])

    materials = client.get(
        "/api/v1/material-lab/materials", params={"book_id": 1, "limit": 5}
    ).json()
    assert materials["total"] == body["materials"]
    assert len(materials["items"]) == 5
    item = materials["items"][0]
    for key in ("title", "concise_example", "core_pattern", "mechanism",
                "suspense_question", "category_label", "quality_score", "tags"):
        assert key in item
    # 派生层不携带源文本人名
    assert "陈默" not in item["concise_example"]

    # 过滤器：min_score 过滤后不多于全量
    filtered = client.get(
        "/api/v1/material-lab/materials",
        params={"book_id": 1, "min_score": 60},
    ).json()
    assert filtered["total"] <= materials["total"]


def test_api_genres_and_suggestion(client):
    genres = client.get("/api/v1/material-lab/genres").json()["items"]
    assert len(genres) == 10
    assert {"slug", "label", "category_count"} <= set(genres[0])

    suggestion = client.get("/api/v1/material-lab/books/1/genre-suggestion").json()
    assert suggestion["genre_slug"] == "xuanyi"
    assert suggestion["label"] == "悬疑"


def test_api_patterns_listing(client):
    client.post("/api/v1/material-lab/books/1/run", json={"genre_slug": "xuanyi"})
    patterns = client.get(
        "/api/v1/material-lab/patterns", params={"genre_slug": "xuanyi"}
    ).json()
    assert patterns["total"] > 0
    assert all(p["variant_count"] > 0 for p in patterns["items"])


def test_api_error_shapes(client):
    missing = client.get("/api/v1/material-lab/books/404/summary")
    assert missing.status_code == 404
    bad = client.post("/api/v1/material-lab/books/1/run", json={"genre_slug": "nope"})
    assert bad.status_code == 400
