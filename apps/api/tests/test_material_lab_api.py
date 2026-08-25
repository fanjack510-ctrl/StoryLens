# -*- coding: utf-8 -*-
"""素材库落库层与路由的测试：跑一本合成书，验证五张表的行为与接口形状。"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.material_lab_models import (
    MaterialLabAtom,
    MaterialLabEvidence,
    MaterialLabLegacyImport,
    MaterialLabLegacyMaterial,
    MaterialLabMaterial,
    MaterialLabPattern,
    MaterialLabRun,
)
from app.db.models import Base, Book, Chapter, Paragraph, WholeBookCheckpoint, WholeBookRun, utc_now
from app.db.session import get_db
from app.main import create_app
from app.routers import material_lab_router
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
        source_file_hash=f"{book_id:064d}", material_kind="fiction",
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
    session.add(WholeBookRun(
        book_id=book_id,
        status="completed",
        idempotency_key=f"material-source-{book_id}",
        engine_version="hierarchical-v2-1.0+story_breakdown",
        result_origin="formal",
        chapter_limit=None,
        completed_at=utc_now(),
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
def client(db_session, monkeypatch: pytest.MonkeyPatch):
    # 本文件验证素材提取/Skill 的业务结果；权限拒绝由独立 Pro gate 测试覆盖。
    monkeypatch.setattr(material_lab_router, "_require_pro_feature", lambda *_args: None)
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


def test_extraction_is_taxonomy_bound_and_book_bounded(db_session):
    from collections import Counter

    from app.narrative_core.material_lab.genre_templates import (
        BOOK_MATERIAL_LIMIT,
        template_for,
    )

    _seed_book(db_session)
    result = run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()

    template = template_for("xuanyi")
    assert template is not None
    allowed = {item["key"]: item for item in template["categories"]}
    rows = list(db_session.scalars(select(MaterialLabMaterial)))
    assert 0 < len(rows) <= BOOK_MATERIAL_LIMIT
    assert result["candidates_scanned"] >= result["materials"]
    assert {row.category_key for row in rows} <= set(allowed)

    counts = Counter(row.category_key for row in rows)
    assert all(counts[key] <= allowed[key]["max_items"] for key in counts)
    identities = {
        (row.category_key, row.subcategory_key, row.core_pattern) for row in rows
    }
    assert len(identities) == len(rows), "同一本书不重复沉淀同一种核心模式"


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
    run = client.post(
        "/api/v1/material-lab/library/sources/1/extract",
        json={"genre_slug": "xuanyi"},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["materials"] > 0

    summary = client.get("/api/v1/material-lab/books/1/summary").json()
    assert summary["material_count"] == body["materials"]
    assert summary["source_material_kind"] == "fiction"
    assert summary["knowledge_role"] == "genre_example"
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
                "suspense_question", "category_label", "quality_score", "tags",
                "source_excerpt", "source_paragraph_ids", "source_material_kind",
                "knowledge_role", "knowledge_role_label", "verification_label"):
        assert key in item
    assert item["source_excerpt"]
    assert item["source_paragraph_ids"]
    assert all(pid.startswith("p") for pid in item["source_paragraph_ids"])
    assert item["knowledge_role_label"] == "题材案例"
    assert "不能作为事实依据" in item["verification_label"]
    # 摘要来自命中分类的证据句；不再回退到固定套话。
    assert item["source_excerpt"] == item["concise_example"]
    assert "被明确下来，并限制了后续" not in item["concise_example"]
    assert "处境随之改变" not in item["concise_example"]

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


def test_farming_template_contains_domain_knowledge_categories(client):
    from app.narrative_core.material_lab.genre_templates import template_for

    categories = {c["key"]: c for c in template_for("zhongtian")["categories"]}
    assert {"weather_season", "crop_cultivation", "soil_water", "livestock_processing"} <= set(categories)
    assert any(sub["label"] == "天气变化" for sub in categories["weather_season"]["subcategories"])
    assert any(sub["label"] == "田间管理" for sub in categories["crop_cultivation"]["subcategories"])


def test_reference_book_and_legacy_rows_are_excluded(db_session):
    _seed_book(db_session)
    run_material_lab(db_session, 1, genre_slug="xuanyi")
    db_session.commit()
    book = db_session.get(Book, 1)
    book.material_kind = "reference"
    db_session.commit()

    from app.narrative_core.material_lab.service import knowledge_library_summary, list_materials

    with pytest.raises(MaterialLabError) as exc:
        run_material_lab(db_session, 1, genre_slug="xuanyi")
    assert exc.value.code == "MATERIAL_LAB_SOURCE_NOT_FICTION"
    assert knowledge_library_summary(db_session)["knowledge_count"] == 0
    assert list_materials(db_session, book_id=1, limit=1)["total"] == 0


def test_partial_or_non_breakdown_run_cannot_feed_knowledge(db_session):
    _seed_book(db_session)
    run = db_session.scalars(select(WholeBookRun).where(WholeBookRun.book_id == 1)).one()
    run.chapter_limit = 5
    db_session.commit()

    with pytest.raises(MaterialLabError) as exc:
        run_material_lab(db_session, 1, genre_slug="xuanyi")
    assert exc.value.code == "MATERIAL_LAB_SOURCE_NOT_FULLY_DISSECTED"

    run.chapter_limit = None
    run.result_origin = "fixture"
    db_session.commit()
    with pytest.raises(MaterialLabError) as fixture_exc:
        run_material_lab(db_session, 1, genre_slug="xuanyi")
    assert fixture_exc.value.code == "MATERIAL_LAB_SOURCE_NOT_FULLY_DISSECTED"


def test_api_patterns_listing(client):
    client.post(
        "/api/v1/material-lab/library/sources/1/extract",
        json={"genre_slug": "xuanyi"},
    )
    patterns = client.get(
        "/api/v1/material-lab/patterns", params={"genre_slug": "xuanyi"}
    ).json()
    assert patterns["total"] > 0
    assert all(p["variant_count"] > 0 for p in patterns["items"])


def test_cross_book_knowledge_summary_and_role_filter(client):
    client.post(
        "/api/v1/material-lab/library/sources/1/extract",
        json={"genre_slug": "xuanyi"},
    )

    summary = client.get("/api/v1/material-lab/library/summary").json()
    assert summary["knowledge_count"] > 0
    assert summary["source_book_count"] == 1
    assert summary["by_role"]["genre_example"] == summary["knowledge_count"]
    assert summary["by_role"]["domain_reference"] == 0
    assert summary["by_genre"][0]["label"] == "悬疑"
    assert summary["sources"][0]["book_title"] == "测试书1"

    examples = client.get(
        "/api/v1/material-lab/materials",
        params={"knowledge_role": "genre_example", "genre_slug": "xuanyi", "limit": 1},
    ).json()
    assert examples["total"] > 0
    assert examples["items"][0]["source_book_title"] == "测试书1"
    references = client.get(
        "/api/v1/material-lab/materials",
        params={"knowledge_role": "domain_reference"},
    ).json()
    assert references["total"] == 0

    sources = client.get("/api/v1/material-lab/library/sources").json()
    assert sources["total"] == 1
    assert sources["items"][0]["book_title"] == "测试书1"
    assert sources["items"][0]["extracted"] is True


def test_taxonomy_exists_even_when_knowledge_library_is_empty(client):
    summary = client.get("/api/v1/material-lab/library/summary").json()
    assert summary["knowledge_count"] == 0
    assert len(summary["taxonomy"]) == 10
    mystery = next(item for item in summary["taxonomy"] if item["slug"] == "xuanyi")
    assert mystery["label"] == "悬疑"
    assert mystery["count"] == 0
    assert len(mystery["categories"]) == 18
    assert {item["label"] for item in mystery["categories"]} >= {
        "开篇异常", "实物线索", "人物疑点", "伏笔", "真相揭示"
    }
    assert all(item["count"] == 0 for item in mystery["categories"])


def test_api_error_shapes(client, db_session):
    missing = client.get("/api/v1/material-lab/books/404/summary")
    assert missing.status_code == 404
    bad = client.post(
        "/api/v1/material-lab/library/sources/1/extract",
        json={"genre_slug": "nope"},
    )
    assert bad.status_code == 400

    run = db_session.scalars(select(WholeBookRun).where(WholeBookRun.book_id == 1)).one()
    run.chapter_limit = 5
    db_session.commit()
    blocked = client.post(
        "/api/v1/material-lab/library/sources/1/extract",
        json={"genre_slug": "xuanyi"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error_code"] == "MATERIAL_LAB_SOURCE_NOT_FULLY_DISSECTED"


def test_book_skill_requires_a_readable_full_report(client):
    response = client.post("/api/v1/material-lab/library/skills/1")
    assert response.status_code == 409
    assert response.json()["error_code"] == "MATERIAL_LAB_SKILL_RESULT_NOT_FOUND"


def test_book_skill_is_generated_from_validated_report_without_source_quotes(client, db_session):
    from app.narrative_core.whole_book_v2.engine import (
        DeterministicPrimitiveExtractor,
        SourceChapter,
        WholeBookV2Engine,
    )

    run = db_session.scalars(select(WholeBookRun).where(WholeBookRun.book_id == 1)).one()
    source = [
        SourceChapter(
            chapter_id=1000 + index,
            chapter_index=index,
            title=f"第{index}章",
            text=f"@林 第{index}章 谜团 线索 误导 真相，人物作出选择并承担代价。",
            snapshot_id=77,
            revision_hash="skill-test-revision",
        )
        for index in range(1, 5)
    ]
    result = WholeBookV2Engine(
        DeterministicPrimitiveExtractor(), window_size=2, overlap=1,
    ).run(run_id=int(run.id), book_id=1, title="雾港疑案", chapters=source)
    db_session.add(WholeBookCheckpoint(
        run_id=int(run.id),
        stage_code="v2_result",
        checkpoint_key="latest",
        sequence_no=1,
        completed_unit_count=1,
        payload_hash="",
        checkpoint_payload_json=result.model_dump_json(),
    ))
    db_session.commit()

    response = client.post("/api/v1/material-lab/library/skills/1")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "storylens-book-skill/1.0"
    assert body["filename"] == "storylens-book-1-SKILL.md"
    assert "name: storylens-book-1" in body["content"]
    assert "## 结构迁移模板" in body["content"]
    assert "## 悬念与信息释放" in body["content"]
    assert "禁止复制原文" in body["content"]
    assert "@林" not in body["content"]


def _make_legacy_library(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE books (
          book_id TEXT PRIMARY KEY, internal_title TEXT NOT NULL, display_title TEXT
        );
        CREATE TABLE genres (
          genre_id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 100
        );
        CREATE TABLE categories (
          category_id TEXT PRIMARY KEY, genre_id TEXT NOT NULL,
          key TEXT NOT NULL, label TEXT NOT NULL
        );
        CREATE TABLE subcategories (
          subcategory_id TEXT PRIMARY KEY, category_id TEXT NOT NULL,
          key TEXT NOT NULL, label TEXT NOT NULL
        );
        CREATE TABLE materials (
          material_id TEXT PRIMARY KEY, book_id TEXT NOT NULL, scene_id TEXT NOT NULL,
          genre_id TEXT NOT NULL, material_type TEXT NOT NULL,
          category_key TEXT NOT NULL, subcategory_key TEXT NOT NULL,
          title TEXT NOT NULL, concise_example TEXT NOT NULL,
          core_pattern TEXT NOT NULL, mechanism TEXT NOT NULL,
          suspense_question TEXT NOT NULL, applicable_stage TEXT NOT NULL,
          applicable_scene TEXT NOT NULL, emotion TEXT NOT NULL,
          tags_json TEXT NOT NULL, quality_score INTEGER NOT NULL,
          score_json TEXT NOT NULL, confidence REAL NOT NULL,
          source_evidence_json TEXT NOT NULL, pattern_id TEXT,
          is_primary_variant INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO books VALUES ('bk-1', '旧库测试小说', NULL);
        INSERT INTO genres VALUES ('g-1', '悬疑', 'xuanyi', 10);
        INSERT INTO categories VALUES ('c-1', 'g-1', 'clue_object', '实物线索');
        INSERT INTO subcategories VALUES ('s-1', 'c-1', 'key', '钥匙');
        INSERT INTO materials VALUES
          ('m-1','bk-1','sc-1','g-1','线索','clue_object','key',
           '不属于死者的钥匙','遗物中有一把不属于死者住处的钥匙。',
           '不匹配现有空间的钥匙指向未知地点','物件归属冲突 + 延迟解释',
           '钥匙能打开哪里？','开篇','勘查现场','疑惑','["钥匙","实物证据"]',
           88,'{"composite":88}',0.9,'["ev-1"]','PATTERN-1',1,
           '2026-08-16T00:00:00+00:00'),
          ('m-2','bk-1','sc-2','g-1','线索','clue_object','key',
           '门锁上的陌生钥匙','门锁中留有一把住户从未见过的钥匙。',
           '不匹配现有空间的钥匙指向未知地点','物件归属冲突 + 延迟解释',
           '谁留下了钥匙？','发展','门口','不安','["钥匙"]',
           76,'{"composite":76}',0.8,'["ev-2"]','PATTERN-1',0,
           '2026-08-16T00:01:00+00:00');
        """
    )
    con.commit()
    con.close()


def test_legacy_library_import_is_read_only_complete_and_idempotent(client, db_session, tmp_path):
    source = tmp_path / "library.db"
    _make_legacy_library(source)
    before = source.read_bytes()

    inspected = client.post(
        "/api/v1/material-lab/library/legacy/inspect", json={"path": str(source)}
    )
    assert inspected.status_code == 200
    inspection = inspected.json()
    assert inspection["material_count"] == 2
    assert inspection["primary_material_count"] == 1
    assert inspection["contains_source_text"] is False

    imported = client.post(
        "/api/v1/material-lab/library/legacy/import",
        json={
            "path": str(source),
            "expected_fingerprint": inspection["fingerprint"],
            "confirm": True,
        },
    )
    assert imported.status_code == 200
    assert imported.json()["imported_count"] == 2
    assert source.read_bytes() == before
    assert db_session.scalar(
        select(func.count()).select_from(MaterialLabLegacyImport)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(MaterialLabLegacyMaterial)
    ) == 2

    repeated = client.post(
        "/api/v1/material-lab/library/legacy/import",
        json={
            "path": str(source),
            "expected_fingerprint": inspection["fingerprint"],
            "confirm": True,
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["already_imported"] is True
    assert db_session.scalar(
        select(func.count()).select_from(MaterialLabLegacyMaterial)
    ) == 2


def test_legacy_materials_join_global_catalog_without_fake_storylens_evidence(
    client, tmp_path
):
    source = tmp_path / "legacy.sqlite"
    _make_legacy_library(source)
    inspection = client.post(
        "/api/v1/material-lab/library/legacy/inspect", json={"path": str(source)}
    ).json()
    client.post(
        "/api/v1/material-lab/library/legacy/import",
        json={
            "path": str(source),
            "expected_fingerprint": inspection["fingerprint"],
            "confirm": True,
        },
    )

    summary = client.get("/api/v1/material-lab/library/summary").json()
    assert summary["imported_knowledge_count"] == 2
    assert summary["legacy_source_book_count"] == 1
    assert summary["knowledge_count"] == 2
    assert summary["by_genre"][0]["label"] == "悬疑"

    listing = client.get(
        "/api/v1/material-lab/materials",
        params={"source_kind": "legacy_import", "primary_only": True},
    ).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["origin"] == "legacy_import"
    assert item["title"] == "不属于死者的钥匙"
    assert item["book_id"] is None
    assert item["chapter_id"] is None
    assert item["source_excerpt"] == ""
    assert item["source_paragraph_ids"] == []
    assert "未复制小说正文" in item["verification_label"]
