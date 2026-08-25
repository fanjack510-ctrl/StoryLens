"""Import the structured ancient-farming DOCX guides as cited knowledge cards."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import delete, select  # noqa: E402

from app.db.material_lab_models import (  # noqa: E402
    MaterialLabLegacyImport,
    MaterialLabLegacyMaterial,
)
from app.db.session import SessionLocal, create_db  # noqa: E402
from app.narrative_core.material_lab.dedup import signature  # noqa: E402
from app.narrative_core.material_lab.genre_templates import TEMPLATES  # noqa: E402
from app.narrative_core.material_lab.structured_farming_corpus import (  # noqa: E402
    PIPELINE_VERSION,
    corpus_fingerprint,
    parse_structured_farming_directory,
)


SOURCE_PREFIX = "structured-farming-docx:"


def _labels(category_key: str, subcategory_key: str) -> tuple[str, str]:
    for category in TEMPLATES["zhongtian"]["categories"]:
        if category["key"] != category_key:
            continue
        for subcategory in category["subcategories"]:
            if subcategory["key"] == subcategory_key:
                return category["label"], subcategory["label"]
    raise ValueError(f"unknown farming category {category_key}/{subcategory_key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"source directory does not exist: {source}")

    corpus = parse_structured_farming_directory(source)
    fingerprint = corpus_fingerprint(corpus)
    paths = sorted(source.glob("*.docx"))
    now = datetime.now(timezone.utc)
    create_db()

    with SessionLocal() as db:
        existing = db.scalar(
            select(MaterialLabLegacyImport).where(
                MaterialLabLegacyImport.source_fingerprint == fingerprint
            )
        )
        if existing is not None and existing.status == "done":
            print(json.dumps({
                "already_imported": True,
                "batch_id": existing.id,
                "materials": existing.imported_count,
                "excluded": existing.skipped_count,
            }, ensure_ascii=False))
            return 0

        previous_ids = list(db.scalars(
            select(MaterialLabLegacyImport.id).where(
                MaterialLabLegacyImport.source_name.like(f"{SOURCE_PREFIX}%")
            )
        ))
        if previous_ids:
            db.execute(
                delete(MaterialLabLegacyMaterial).where(
                    MaterialLabLegacyMaterial.import_id.in_(previous_ids)
                )
            )
            db.execute(
                delete(MaterialLabLegacyImport).where(
                    MaterialLabLegacyImport.id.in_(previous_ids)
                )
            )

        batch = MaterialLabLegacyImport(
            source_fingerprint=fingerprint,
            source_name=f"{SOURCE_PREFIX}古代种田文写作素材库",
            source_size=sum(path.stat().st_size for path in paths),
            status="running",
            source_material_count=len(corpus.entries) + corpus.excluded_count,
            imported_count=0,
            skipped_count=corpus.excluded_count,
            created_at=now,
        )
        db.add(batch)
        db.flush()

        category_counts: Counter[str] = Counter()
        for entry in corpus.entries:
            category_label, subcategory_label = _labels(
                entry.category_key, entry.subcategory_key
            )
            material_id = hashlib.sha256(
                f"{entry.source_fingerprint}|{entry.section_number}|"
                f"{entry.item_number}|{entry.life_basis}".encode("utf-8")
            ).hexdigest()[:32]
            evidence = [
                {
                    "evidence_id": f"{entry.evidence_prefix}-BASIS",
                    "source_title": entry.source_title,
                    "chapter_index": entry.section_number,
                    "chapter_title": entry.section_label,
                    "paragraph_index": entry.basis_paragraph,
                    "position": "reference",
                    "suggested_category": entry.category_key,
                    "text": f"生活依据：{entry.life_basis}",
                },
                {
                    "evidence_id": f"{entry.evidence_prefix}-EXAMPLE",
                    "source_title": entry.source_title,
                    "chapter_index": entry.section_number,
                    "chapter_title": entry.section_label,
                    "paragraph_index": entry.example_paragraph,
                    "position": "reference",
                    "suggested_category": entry.category_key,
                    "text": f"可直接写：{entry.writing_example}",
                },
                {
                    "evidence_id": f"{entry.evidence_prefix}-PITFALL",
                    "source_title": entry.source_title,
                    "chapter_index": entry.section_number,
                    "chapter_title": entry.section_label,
                    "paragraph_index": entry.pitfall_paragraph,
                    "position": "reference",
                    "suggested_category": entry.category_key,
                    "text": f"避坑：{entry.pitfall}",
                },
            ]
            scores = {
                "concreteness": 5,
                "reusability": 5,
                "information_gap": 4,
                "evidence_fidelity": 5,
                "expression_quality": 5,
            }
            db.add(MaterialLabLegacyMaterial(
                import_id=batch.id,
                source_fingerprint=fingerprint,
                source_material_id=material_id,
                source_pattern_id=(
                    f"corpus:structured-farming:S{entry.section_number:02d}:"
                    f"{signature(entry.life_basis)[:12]}"
                ),
                source_book_id=entry.source_fingerprint,
                source_book_title=entry.source_title,
                source_scene_id=entry.evidence_prefix,
                source_evidence_ids_json=json.dumps({
                    "pipeline_version": PIPELINE_VERSION,
                    "provider": "deterministic-docx-parser",
                    "model": "none",
                    "evidence": evidence,
                    "applicable": entry.applicable,
                    "reference_direction": entry.reference_direction,
                }, ensure_ascii=False),
                genre_slug="zhongtian",
                genre_label="种田",
                material_type="knowledge",
                category_key=entry.category_key,
                category_label=category_label,
                subcategory_key=entry.subcategory_key,
                subcategory_label=subcategory_label,
                title=entry.title,
                concise_example=entry.life_basis,
                core_pattern=entry.writing_example,
                mechanism=entry.pitfall,
                suspense_question="",
                applicable_stage="全书",
                applicable_scene=entry.section_label,
                emotion="种田",
                tags_json=json.dumps([
                    entry.section_label,
                    entry.applicable,
                    entry.reference_direction,
                ], ensure_ascii=False),
                quality_score=96,
                score_json=json.dumps(scores, ensure_ascii=False),
                confidence=0.96,
                is_primary_variant=1,
                created_at=now,
            ))
            category_counts[entry.section_label] += 1

        batch.status = "done"
        batch.imported_count = len(corpus.entries)
        batch.finished_at = now
        db.commit()
        batch_id = batch.id

    print(json.dumps({
        "already_imported": False,
        "batch_id": batch_id,
        "sources": corpus.source_count,
        "materials": len(corpus.entries),
        "excluded": corpus.excluded_count,
        "by_section": dict(sorted(category_counts.items())),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
