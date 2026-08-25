"""Export the approved local material catalog as a sanitized release asset.

Only derived knowledge-card fields are exported.  Book/chapter/paragraph ids,
source titles, excerpts, file paths, timestamps, API configuration and license
data are intentionally absent from the output schema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.narrative_core.material_lab.builtin_seed import (  # noqa: E402
    BuiltinSeedMaterial,
    BuiltinSeedPayload,
    content_sha256,
)
from app.narrative_core.material_lab.genre_templates import (  # noqa: E402
    TEMPLATES,
    label_index,
)


FORBIDDEN_RELEASE_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|ak)-[a-z0-9_-]{12,}"),
    re.compile(r"(?i)\bBearer\s+[a-z0-9._-]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:^|[\s\"'])(?:[a-z]:\\|/Users/|/home/|file://)"),
    re.compile(r"https?://", re.IGNORECASE),
)


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _opaque(prefix: str, *parts: object) -> str:
    source = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(f"{prefix}\x1f{source}".encode("utf-8")).hexdigest()[:32]


def _assert_public_text(row: BuiltinSeedMaterial) -> None:
    text = json.dumps(row.model_dump(mode="json"), ensure_ascii=False)
    for pattern in FORBIDDEN_RELEASE_PATTERNS:
        if pattern.search(text):
            raise ValueError(
                f"material {row.source_material_id} contains forbidden release text"
            )


def _role_from_legacy(row: sqlite3.Row) -> str:
    evidence = _json(row["source_evidence_ids_json"], {})
    pipeline_version = str(evidence.get("pipeline_version") or "")
    if pipeline_version.startswith("structured-farming-docx-"):
        return "domain_reference"
    return "genre_example"


def export_seed(source_db: Path, output: Path, *, seed_id: str) -> BuiltinSeedPayload:
    cats, subs = label_index()
    # Do not use immutable=1 here: the active development database may have
    # committed WAL pages that are part of the approved catalog.  mode=ro plus
    # query_only observes that consistent state without modifying it.
    con = sqlite3.connect(
        f"file:{source_db.resolve().as_posix()}?mode=ro", uri=True
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    materials: list[BuiltinSeedMaterial] = []
    try:
        legacy_rows = con.execute(
            "SELECT * FROM material_lab_legacy_materials ORDER BY id"
        )
        for row in legacy_rows:
            genre_slug = str(row["genre_slug"] or "")
            role = _role_from_legacy(row)
            card = BuiltinSeedMaterial(
                source_material_id=_opaque(
                    "material", "legacy", row["source_fingerprint"], row["source_material_id"]
                ),
                source_group_id=_opaque(
                    "group", "legacy", row["source_fingerprint"], row["source_book_id"]
                ),
                knowledge_role=role,
                genre_slug=genre_slug,
                genre_label=str(
                    row["genre_label"]
                    or (TEMPLATES.get(genre_slug) or {}).get("label")
                    or genre_slug
                ),
                material_type=str(row["material_type"] or "knowledge"),
                category_key=str(row["category_key"] or ""),
                category_label=str(
                    row["category_label"]
                    or cats.get(str(row["category_key"] or ""))
                    or row["category_key"]
                ),
                subcategory_key=str(row["subcategory_key"] or ""),
                subcategory_label=str(
                    row["subcategory_label"]
                    or subs.get(str(row["subcategory_key"] or ""))
                    or row["subcategory_key"]
                    or ""
                ),
                title=str(row["title"] or ""),
                concise_example=str(row["concise_example"] or ""),
                core_pattern=str(row["core_pattern"] or ""),
                mechanism=str(row["mechanism"] or ""),
                suspense_question=str(row["suspense_question"] or ""),
                applicable_stage=str(row["applicable_stage"] or ""),
                applicable_scene=str(row["applicable_scene"] or ""),
                emotion=str(row["emotion"] or ""),
                tags=_json(row["tags_json"], []),
                quality_score=int(row["quality_score"] or 0),
                score=_json(row["score_json"], {}),
                confidence=float(row["confidence"] or 0.0),
                is_primary_variant=bool(row["is_primary_variant"]),
            )
            _assert_public_text(card)
            materials.append(card)

        native_rows = con.execute(
            "SELECT * FROM material_lab_materials ORDER BY id"
        )
        for row in native_rows:
            genre_slug = str(row["genre_slug"] or "")
            card = BuiltinSeedMaterial(
                source_material_id=_opaque("material", "native", row["id"]),
                source_group_id=_opaque("group", "native", row["book_id"]),
                knowledge_role="genre_example",
                genre_slug=genre_slug,
                genre_label=str(
                    (TEMPLATES.get(genre_slug) or {}).get("label") or genre_slug
                ),
                material_type=str(row["material_type"] or "knowledge"),
                category_key=str(row["category_key"] or ""),
                category_label=str(
                    cats.get(str(row["category_key"] or "")) or row["category_key"]
                ),
                subcategory_key=str(row["subcategory_key"] or ""),
                subcategory_label=str(
                    subs.get(str(row["subcategory_key"] or ""))
                    or row["subcategory_key"]
                    or ""
                ),
                title=str(row["title"] or ""),
                concise_example=str(row["concise_example"] or ""),
                core_pattern=str(row["core_pattern"] or ""),
                mechanism=str(row["mechanism"] or ""),
                suspense_question=str(row["suspense_question"] or ""),
                applicable_stage=str(row["applicable_stage"] or ""),
                applicable_scene=str(row["applicable_scene"] or ""),
                emotion=str(row["emotion"] or ""),
                tags=_json(row["tags_json"], []),
                quality_score=int(row["quality_score"] or 0),
                score=_json(row["score_json"], {}),
                confidence=float(row["confidence"] or 0.0),
                is_primary_variant=bool(row["is_primary_variant"]),
            )
            _assert_public_text(card)
            materials.append(card)
    finally:
        con.close()

    checksum = content_sha256(materials)
    payload = BuiltinSeedPayload(
        schema_version=1,
        seed_id=seed_id,
        material_count=len(materials),
        content_sha256=checksum,
        materials=materials,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, default=ROOT / "data" / "storylens.db")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "packages" / "material_seed" / "storylens_material_seed_v1.json",
    )
    parser.add_argument("--seed-id", default="storylens-materials-2026.08.25")
    args = parser.parse_args()
    payload = export_seed(args.source_db, args.output, seed_id=args.seed_id)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "material_count": payload.material_count,
                "content_sha256": payload.content_sha256,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
