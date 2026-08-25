"""旧 novel-material-lab 派生知识的只读检查与幂等迁移。

迁移边界很窄：只读取旧库的 ``materials`` 派生层和分类/来源标识，绝不复制
``source_evidence.snippet``、章节正文或原始文件路径。目标表与当前全书提取表分开，
因此不会伪造 StoryLens 的 book/chapter/paragraph 外键。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.material_lab_models import (
    MaterialLabLegacyImport,
    MaterialLabLegacyMaterial,
)

from .service import MaterialLabError


REQUIRED_TABLES = {
    "books", "genres", "categories", "subcategories", "materials",
}
REQUIRED_MATERIAL_COLUMNS = {
    "material_id", "book_id", "scene_id", "genre_id", "material_type",
    "category_key", "subcategory_key", "title", "concise_example",
    "core_pattern", "mechanism", "suspense_question", "applicable_stage",
    "applicable_scene", "emotion", "tags_json", "quality_score", "score_json",
    "confidence", "source_evidence_json", "pattern_id", "is_primary_variant",
    "created_at",
}


class LegacyBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str
    count: int = Field(ge=0)


class LegacyLibraryInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    compatible: bool
    source_name: str
    source_size: int = Field(ge=0)
    fingerprint: str
    book_count: int = Field(ge=0)
    material_count: int = Field(ge=0)
    primary_material_count: int = Field(ge=0)
    pattern_count: int = Field(ge=0)
    genre_count: int = Field(ge=0)
    category_count: int = Field(ge=0)
    subcategory_count: int = Field(ge=0)
    by_genre: list[LegacyBreakdown]
    by_type: list[LegacyBreakdown]
    contains_source_text: Literal[False] = False


class LegacyImportStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imported: bool
    batch_id: int | None = None
    status: str = "not_imported"
    source_name: str = ""
    fingerprint: str = ""
    source_material_count: int = Field(default=0, ge=0)
    imported_count: int = Field(default=0, ge=0)
    primary_material_count: int = Field(default=0, ge=0)
    imported_at: str | None = None
    contains_source_text: Literal[False] = False
    already_imported: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _source_path(raw_path: str) -> Path:
    value = raw_path.strip().strip('"')
    path = Path(value)
    if not value or not path.is_absolute():
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_PATH_INVALID", "请选择旧资料库 library.db 的绝对路径"
        )
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_PATH_INVALID", "旧资料库必须是 SQLite 数据库文件"
        )
    if not path.is_file():
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_NOT_FOUND", f"找不到旧资料库：{path}"
        )
    return path.resolve()


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    # immutable=1 可确保旧库不会因为 journal/WAL 或意外语句被修改。
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def _validate_schema(con: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_SCHEMA_UNSUPPORTED",
            f"这不是受支持的旧资料库，缺少表：{', '.join(missing)}",
        )
    columns = {str(row[1]) for row in con.execute("PRAGMA table_info(materials)")}
    missing_columns = sorted(REQUIRED_MATERIAL_COLUMNS - columns)
    if missing_columns:
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_SCHEMA_UNSUPPORTED",
            f"旧资料库版本不兼容，materials 缺少字段：{', '.join(missing_columns)}",
        )


def _scalar(con: sqlite3.Connection, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0] or 0)


def inspect_legacy_library(raw_path: str) -> LegacyLibraryInspection:
    path = _source_path(raw_path)
    with _connect_read_only(path) as con:
        _validate_schema(con)
        by_genre = [
            LegacyBreakdown(key=row[0], label=row[1], count=row[2])
            for row in con.execute(
                """SELECT g.slug, g.name, COUNT(m.material_id)
                   FROM materials m JOIN genres g ON g.genre_id=m.genre_id
                   GROUP BY g.genre_id ORDER BY g.sort_order, g.slug"""
            )
        ]
        by_type = [
            LegacyBreakdown(key=row[0], label=row[0], count=row[1])
            for row in con.execute(
                "SELECT material_type, COUNT(*) FROM materials "
                "GROUP BY material_type ORDER BY COUNT(*) DESC, material_type"
            )
        ]
        return LegacyLibraryInspection(
            compatible=True,
            source_name=path.name,
            source_size=path.stat().st_size,
            fingerprint=_fingerprint(path),
            book_count=_scalar(con, "SELECT COUNT(*) FROM books"),
            material_count=_scalar(con, "SELECT COUNT(*) FROM materials"),
            primary_material_count=_scalar(
                con, "SELECT COUNT(*) FROM materials WHERE is_primary_variant=1"
            ),
            pattern_count=(
                _scalar(con, "SELECT COUNT(*) FROM material_patterns")
                if "material_patterns" in {
                    str(row[0]) for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                else _scalar(con, "SELECT COUNT(DISTINCT pattern_id) FROM materials")
            ),
            genre_count=_scalar(con, "SELECT COUNT(*) FROM genres"),
            category_count=_scalar(con, "SELECT COUNT(*) FROM categories"),
            subcategory_count=_scalar(con, "SELECT COUNT(*) FROM subcategories"),
            by_genre=by_genre,
            by_type=by_type,
        )


def _json_text(value: str | None, *, array: bool) -> str:
    fallback: list | dict = [] if array else {}
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        parsed = fallback
    if array and not isinstance(parsed, list):
        parsed = []
    if not array and not isinstance(parsed, dict):
        parsed = {}
    return json.dumps(parsed, ensure_ascii=False)


def _parse_datetime(value: str | None) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return _utc_now()


MATERIAL_SELECT = """
SELECT
    m.material_id, m.book_id, m.scene_id, m.material_type,
    m.category_key, m.subcategory_key, m.title, m.concise_example,
    m.core_pattern, m.mechanism, m.suspense_question,
    m.applicable_stage, m.applicable_scene, m.emotion, m.tags_json,
    m.quality_score, m.score_json, m.confidence, m.source_evidence_json,
    COALESCE(m.pattern_id, '') AS pattern_id,
    m.is_primary_variant, m.created_at,
    COALESCE(b.display_title, b.internal_title, '') AS book_title,
    COALESCE(g.slug, '') AS genre_slug, COALESCE(g.name, '') AS genre_label,
    COALESCE(c.label, m.category_key) AS category_label,
    COALESCE(s.label, m.subcategory_key) AS subcategory_label
FROM materials m
LEFT JOIN books b ON b.book_id=m.book_id
LEFT JOIN genres g ON g.genre_id=m.genre_id
LEFT JOIN categories c ON c.genre_id=m.genre_id AND c.key=m.category_key
LEFT JOIN subcategories s ON s.category_id=c.category_id AND s.key=m.subcategory_key
ORDER BY m.material_id
"""


def import_legacy_library(
    db: Session, raw_path: str, *, expected_fingerprint: str
) -> LegacyImportStatus:
    inspection = inspect_legacy_library(raw_path)
    if inspection.fingerprint != expected_fingerprint:
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_SOURCE_CHANGED",
            "旧资料库在检查后发生了变化，请重新检查再迁移",
        )

    existing = db.scalar(
        select(MaterialLabLegacyImport).where(
            MaterialLabLegacyImport.source_fingerprint == inspection.fingerprint
        )
    )
    if existing and existing.status == "completed":
        return _status_from_batch(db, existing, already_imported=True)
    if existing is None:
        batch = MaterialLabLegacyImport(
            source_fingerprint=inspection.fingerprint,
            source_name=inspection.source_name,
            source_size=inspection.source_size,
            status="running",
            source_material_count=inspection.material_count,
        )
        db.add(batch)
        db.flush()
    else:
        batch = existing
        db.query(MaterialLabLegacyMaterial).filter(
            MaterialLabLegacyMaterial.import_id == batch.id
        ).delete(synchronize_session=False)
        batch.status = "running"
        batch.imported_count = 0
        batch.skipped_count = 0
        batch.error_message = None
        batch.finished_at = None
        db.flush()

    path = _source_path(raw_path)
    inserted = 0
    with _connect_read_only(path) as con:
        _validate_schema(con)
        cursor = con.execute(MATERIAL_SELECT)
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            objects = [
                MaterialLabLegacyMaterial(
                    import_id=batch.id,
                    source_fingerprint=inspection.fingerprint,
                    source_material_id=str(row["material_id"]),
                    source_pattern_id=str(row["pattern_id"] or ""),
                    source_book_id=str(row["book_id"] or ""),
                    source_book_title=str(row["book_title"] or ""),
                    source_scene_id=str(row["scene_id"] or ""),
                    source_evidence_ids_json=_json_text(
                        row["source_evidence_json"], array=True
                    ),
                    genre_slug=str(row["genre_slug"] or ""),
                    genre_label=str(row["genre_label"] or ""),
                    material_type=str(row["material_type"] or ""),
                    category_key=str(row["category_key"] or ""),
                    category_label=str(row["category_label"] or ""),
                    subcategory_key=str(row["subcategory_key"] or ""),
                    subcategory_label=str(row["subcategory_label"] or ""),
                    title=str(row["title"] or ""),
                    concise_example=str(row["concise_example"] or ""),
                    core_pattern=str(row["core_pattern"] or ""),
                    mechanism=str(row["mechanism"] or ""),
                    suspense_question=str(row["suspense_question"] or ""),
                    applicable_stage=str(row["applicable_stage"] or ""),
                    applicable_scene=str(row["applicable_scene"] or ""),
                    emotion=str(row["emotion"] or ""),
                    tags_json=_json_text(row["tags_json"], array=True),
                    quality_score=int(row["quality_score"] or 0),
                    score_json=_json_text(row["score_json"], array=False),
                    confidence=float(row["confidence"] or 0.0),
                    is_primary_variant=int(row["is_primary_variant"] or 0),
                    created_at=_parse_datetime(row["created_at"]),
                )
                for row in rows
            ]
            db.bulk_save_objects(objects)
            inserted += len(objects)
            db.flush()

    if inserted != inspection.material_count:
        raise MaterialLabError(
            "MATERIAL_LAB_LEGACY_COUNT_MISMATCH",
            f"迁移计数不一致：检查到 {inspection.material_count}，写入 {inserted}",
        )
    batch.imported_count = inserted
    batch.status = "completed"
    batch.finished_at = _utc_now()
    db.flush()
    return _status_from_batch(db, batch)


def _status_from_batch(
    db: Session, batch: MaterialLabLegacyImport, *, already_imported: bool = False
) -> LegacyImportStatus:
    primary = db.scalar(
        select(func.count()).select_from(MaterialLabLegacyMaterial).where(
            MaterialLabLegacyMaterial.import_id == batch.id,
            MaterialLabLegacyMaterial.is_primary_variant == 1,
        )
    ) or 0
    return LegacyImportStatus(
        imported=batch.status == "completed",
        batch_id=batch.id,
        status=batch.status,
        source_name=batch.source_name,
        fingerprint=batch.source_fingerprint,
        source_material_count=batch.source_material_count,
        imported_count=batch.imported_count,
        primary_material_count=int(primary),
        imported_at=batch.finished_at.isoformat() if batch.finished_at else None,
        already_imported=already_imported,
    )


def legacy_import_status(db: Session) -> LegacyImportStatus:
    batch = db.scalar(
        select(MaterialLabLegacyImport)
        .where(MaterialLabLegacyImport.status == "completed")
        .order_by(MaterialLabLegacyImport.id.desc())
        .limit(1)
    )
    return _status_from_batch(db, batch) if batch else LegacyImportStatus(imported=False)
