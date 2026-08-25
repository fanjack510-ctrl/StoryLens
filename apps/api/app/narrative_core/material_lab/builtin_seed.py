"""Install the public, sanitized StoryLens material seed.

The release never ships a user's SQLite database.  Instead it ships a small
Pydantic-validated JSON asset containing only derived knowledge-card fields.
The installer is idempotent, replaces only earlier StoryLens-owned seed
batches, and never overwrites rows created or imported by the user.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.material_lab_models import (
    MaterialLabLegacyImport,
    MaterialLabLegacyMaterial,
    MaterialLabMaterial,
)


logger = logging.getLogger(__name__)

SEED_FILE_NAME = "storylens_material_seed_v1.json"
SEED_SOURCE_PREFIX = "storylens-builtin-material-seed:"
SEED_PATH_ENV = "STORYLENS_MATERIAL_SEED_PATH"


class BuiltinSeedMaterial(BaseModel):
    """One source-independent knowledge card safe to distribute publicly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_material_id: str = Field(min_length=16, max_length=64)
    source_group_id: str = Field(min_length=16, max_length=64)
    knowledge_role: Literal["genre_example", "domain_reference"]
    genre_slug: str = Field(min_length=1, max_length=32)
    genre_label: str = Field(min_length=1, max_length=32)
    material_type: str = Field(min_length=1, max_length=16)
    category_key: str = Field(min_length=1, max_length=64)
    category_label: str = Field(min_length=1, max_length=64)
    subcategory_key: str = Field(default="", max_length=64)
    subcategory_label: str = Field(default="", max_length=64)
    title: str = Field(min_length=1, max_length=200)
    concise_example: str = Field(min_length=1, max_length=4000)
    core_pattern: str = Field(min_length=1, max_length=500)
    mechanism: str = Field(default="", max_length=200)
    suspense_question: str = Field(default="", max_length=500)
    applicable_stage: str = Field(default="", max_length=32)
    applicable_scene: str = Field(default="", max_length=64)
    emotion: str = Field(default="", max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=40)
    quality_score: int = Field(ge=0, le=100)
    score: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    is_primary_variant: bool = True

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if any(len(item) > 80 for item in cleaned):
            raise ValueError("seed tag exceeds 80 characters")
        return list(dict.fromkeys(cleaned))


class BuiltinSeedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal[1]
    seed_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{5,63}$")
    material_count: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    materials: list[BuiltinSeedMaterial] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "BuiltinSeedPayload":
        if self.material_count != len(self.materials):
            raise ValueError("seed material_count does not match materials")
        if len({row.source_material_id for row in self.materials}) != len(self.materials):
            raise ValueError("seed source_material_id values must be unique")
        actual = content_sha256(self.materials)
        if actual != self.content_sha256:
            raise ValueError("seed content_sha256 mismatch")
        return self


class BuiltinSeedInstallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: bool
    seed_id: str = ""
    source_count: int = Field(default=0, ge=0)
    inserted_count: int = Field(default=0, ge=0)
    skipped_existing_count: int = Field(default=0, ge=0)
    already_installed: bool = False


def _canonical_materials(materials: list[BuiltinSeedMaterial]) -> bytes:
    rows = [row.model_dump(mode="json") for row in materials]
    return json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(materials: list[BuiltinSeedMaterial]) -> str:
    return hashlib.sha256(_canonical_materials(materials)).hexdigest()


def _default_seed_path() -> Path:
    override = os.environ.get(SEED_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "packages" / "material_seed" / SEED_FILE_NAME
    return Path(__file__).resolve().parents[5] / "packages" / "material_seed" / SEED_FILE_NAME


def load_builtin_seed(path: Path | None = None) -> BuiltinSeedPayload | None:
    seed_path = path or _default_seed_path()
    if not seed_path.is_file():
        return None
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    return BuiltinSeedPayload.model_validate(raw)


def _identity_values(
    *,
    genre_slug: str,
    material_type: str,
    category_key: str,
    subcategory_key: str,
    title: str,
    concise_example: str,
    core_pattern: str,
) -> str:
    parts = (
        genre_slug,
        material_type,
        category_key,
        subcategory_key,
        title,
        concise_example,
        core_pattern,
    )
    normalized = "\x1f".join(str(value or "").strip() for value in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _seed_identity(row: BuiltinSeedMaterial) -> str:
    return _identity_values(
        genre_slug=row.genre_slug,
        material_type=row.material_type,
        category_key=row.category_key,
        subcategory_key=row.subcategory_key,
        title=row.title,
        concise_example=row.concise_example,
        core_pattern=row.core_pattern,
    )


def install_builtin_material_seed(
    db: Session, *, path: Path | None = None
) -> BuiltinSeedInstallResult:
    """Merge the bundled seed without changing user-owned material rows."""

    payload = load_builtin_seed(path)
    if payload is None:
        return BuiltinSeedInstallResult(found=False)

    source_name = f"{SEED_SOURCE_PREFIX}{payload.seed_id}"
    completed = db.scalar(
        select(MaterialLabLegacyImport).where(
            MaterialLabLegacyImport.source_name == source_name,
            MaterialLabLegacyImport.status == "completed",
            MaterialLabLegacyImport.source_material_count == payload.material_count,
        )
    )
    if completed is not None:
        return BuiltinSeedInstallResult(
            found=True,
            seed_id=payload.seed_id,
            source_count=payload.material_count,
            inserted_count=int(completed.imported_count or 0),
            skipped_existing_count=max(
                payload.material_count - int(completed.imported_count or 0), 0
            ),
            already_installed=True,
        )

    old_batches = list(
        db.scalars(
            select(MaterialLabLegacyImport).where(
                MaterialLabLegacyImport.source_name.like(f"{SEED_SOURCE_PREFIX}%")
            )
        )
    )
    for batch in old_batches:
        db.query(MaterialLabLegacyMaterial).filter(
            MaterialLabLegacyMaterial.import_id == batch.id
        ).delete(synchronize_session=False)
        db.delete(batch)
    db.flush()

    existing: set[str] = set()
    for row in db.scalars(select(MaterialLabLegacyMaterial)):
        existing.add(
            _identity_values(
                genre_slug=row.genre_slug,
                material_type=row.material_type,
                category_key=row.category_key,
                subcategory_key=row.subcategory_key,
                title=row.title,
                concise_example=row.concise_example,
                core_pattern=row.core_pattern,
            )
        )
    for row in db.scalars(select(MaterialLabMaterial)):
        existing.add(
            _identity_values(
                genre_slug=row.genre_slug,
                material_type=row.material_type,
                category_key=row.category_key,
                subcategory_key=row.subcategory_key,
                title=row.title,
                concise_example=row.concise_example,
                core_pattern=row.core_pattern,
            )
        )

    seed_bytes = (path or _default_seed_path()).read_bytes()
    # Namespace the fingerprint so a user manually importing the exact JSON
    # bytes through a future importer can never collide with this owned batch.
    fingerprint = hashlib.sha256(b"storylens-builtin-seed\0" + seed_bytes).hexdigest()
    batch = MaterialLabLegacyImport(
        source_fingerprint=fingerprint,
        source_name=source_name,
        source_size=len(seed_bytes),
        status="running",
        source_material_count=payload.material_count,
    )
    db.add(batch)
    db.flush()

    inserted = 0
    for row in payload.materials:
        identity = _seed_identity(row)
        if identity in existing:
            continue
        existing.add(identity)
        db.add(
            MaterialLabLegacyMaterial(
                import_id=batch.id,
                source_fingerprint=fingerprint,
                source_material_id=row.source_material_id,
                source_pattern_id=f"builtin:{row.knowledge_role}",
                source_book_id=f"builtin:{row.source_group_id}",
                source_book_title="",
                source_scene_id="",
                source_evidence_ids_json="[]",
                genre_slug=row.genre_slug,
                genre_label=row.genre_label,
                material_type=row.material_type,
                category_key=row.category_key,
                category_label=row.category_label,
                subcategory_key=row.subcategory_key,
                subcategory_label=row.subcategory_label,
                title=row.title,
                concise_example=row.concise_example,
                core_pattern=row.core_pattern,
                mechanism=row.mechanism,
                suspense_question=row.suspense_question,
                applicable_stage=row.applicable_stage,
                applicable_scene=row.applicable_scene,
                emotion=row.emotion,
                tags_json=json.dumps(row.tags, ensure_ascii=False),
                quality_score=row.quality_score,
                score_json=json.dumps(row.score, ensure_ascii=False, sort_keys=True),
                confidence=row.confidence,
                is_primary_variant=1 if row.is_primary_variant else 0,
            )
        )
        inserted += 1

    batch.imported_count = inserted
    batch.skipped_count = payload.material_count - inserted
    batch.status = "completed"
    from app.db.models import utc_now

    batch.finished_at = utc_now()
    db.flush()
    logger.info(
        "builtin_material_seed_installed seed_id=%s source=%s inserted=%s skipped=%s",
        payload.seed_id,
        payload.material_count,
        inserted,
        payload.material_count - inserted,
    )
    return BuiltinSeedInstallResult(
        found=True,
        seed_id=payload.seed_id,
        source_count=payload.material_count,
        inserted_count=inserted,
        skipped_existing_count=payload.material_count - inserted,
    )


__all__ = [
    "BuiltinSeedInstallResult",
    "BuiltinSeedMaterial",
    "BuiltinSeedPayload",
    "SEED_FILE_NAME",
    "content_sha256",
    "install_builtin_material_seed",
    "load_builtin_seed",
]
