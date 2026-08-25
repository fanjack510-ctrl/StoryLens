from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.material_lab_models import MaterialLabLegacyImport, MaterialLabLegacyMaterial
from app.db.models import Base
from app.narrative_core.material_lab.builtin_seed import (
    BuiltinSeedMaterial,
    BuiltinSeedPayload,
    content_sha256,
    install_builtin_material_seed,
    load_builtin_seed,
)


@pytest.fixture()
def session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def _release_seed_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "material_seed"
        / "storylens_material_seed_v1.json"
    )


def _row(*, suffix: str = "a") -> BuiltinSeedMaterial:
    return BuiltinSeedMaterial(
        source_material_id=(suffix * 32)[:32],
        source_group_id=(suffix * 16)[:16],
        knowledge_role="genre_example",
        genre_slug="xuanyi",
        genre_label="悬疑",
        material_type="knowledge",
        category_key="clue_object",
        category_label="实物线索",
        subcategory_key="leftover",
        subcategory_label="遗留物",
        title=f"测试素材{suffix}",
        concise_example=f"一个可以直接复用的知识示例{suffix}",
        core_pattern=f"稳定知识模式{suffix}",
        quality_score=88,
        confidence=0.88,
    )


def _write_payload(path: Path, rows: list[BuiltinSeedMaterial], seed_id: str) -> None:
    payload = BuiltinSeedPayload(
        schema_version=1,
        seed_id=seed_id,
        material_count=len(rows),
        content_sha256=content_sha256(rows),
        materials=rows,
    )
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )


def test_release_seed_is_valid_and_contains_approved_798_cards():
    payload = load_builtin_seed(_release_seed_path())
    assert payload is not None
    assert payload.material_count == 798
    assert {row.knowledge_role for row in payload.materials} == {
        "genre_example",
        "domain_reference",
    }


def test_fresh_database_installs_release_seed_once(session):
    first = install_builtin_material_seed(session, path=_release_seed_path())
    session.commit()
    assert first.source_count == 798
    assert first.inserted_count == 798
    assert session.scalar(
        select(func.count()).select_from(MaterialLabLegacyMaterial)
    ) == 798

    second = install_builtin_material_seed(session, path=_release_seed_path())
    session.commit()
    assert second.already_installed is True
    assert session.scalar(
        select(func.count()).select_from(MaterialLabLegacyMaterial)
    ) == 798


def test_seed_merge_preserves_user_rows_and_skips_matching_card(session, tmp_path: Path):
    matching = _row(suffix="a")
    user_batch = MaterialLabLegacyImport(
        source_fingerprint="1" * 64,
        source_name="user-import.db",
        source_size=10,
        status="completed",
        source_material_count=1,
        imported_count=1,
    )
    session.add(user_batch)
    session.flush()
    session.add(
        MaterialLabLegacyMaterial(
            import_id=user_batch.id,
            source_fingerprint=user_batch.source_fingerprint,
            source_material_id="user-card",
            source_pattern_id="corpus:user",
            source_book_id="user-book",
            source_book_title="",
            source_scene_id="",
            source_evidence_ids_json="[]",
            genre_slug=matching.genre_slug,
            genre_label=matching.genre_label,
            material_type=matching.material_type,
            category_key=matching.category_key,
            category_label=matching.category_label,
            subcategory_key=matching.subcategory_key,
            subcategory_label=matching.subcategory_label,
            title=matching.title,
            concise_example=matching.concise_example,
            core_pattern=matching.core_pattern,
            mechanism="",
            suspense_question="",
            applicable_stage="",
            applicable_scene="",
            emotion="",
            tags_json="[]",
            quality_score=matching.quality_score,
            score_json="{}",
            confidence=matching.confidence,
            is_primary_variant=1,
        )
    )
    session.commit()

    seed_path = tmp_path / "mini-seed.json"
    _write_payload(seed_path, [matching, _row(suffix="b")], "test-seed-v1")
    result = install_builtin_material_seed(session, path=seed_path)
    session.commit()

    assert result.inserted_count == 1
    assert result.skipped_existing_count == 1
    assert session.scalar(
        select(func.count()).select_from(MaterialLabLegacyMaterial)
    ) == 2
    assert session.scalar(
        select(MaterialLabLegacyImport).where(
            MaterialLabLegacyImport.source_name == "user-import.db"
        )
    ) is not None
