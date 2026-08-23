"""素材库的落库层：bridge 的纯输出 -> 五张表。本包唯一允许碰数据库的模块。

对应源项目 pipeline.py + dedup.py 绑 db 的那半边，按 StoryLens 的
SQLAlchemy 结构重写。三处与源项目的刻意差异：

1. **评分一次到位**：源项目边插边算 novelty/similarity_penalty（频次是"到目前
   为止"的），再用 rescore_with_final_counts 在结束后拉平。这里先抽完整本书、
   再用最终频次统一评分——终态与源项目拉平后的意图一致，且顺序无关。
2. **模式簇归并在内存缓存上做**：同 (genre, category) 的簇一次载入，
   精确签名命中走字典，其余走 dedup.similarity 线性扫——阈值 0.62 与源项目
   DEFAULTS 一致。
3. **重跑即重来**：对一本书重跑会先删掉它名下的原子/证据/资料（模式簇保留，
   由 refresh_pattern_stats 收缩计数）。源项目的 checkpoint/resume 机制不搬——
   本地引擎整本书秒级跑完，断点续跑保护的成本不存在了。
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.material_lab_models import (
    MaterialLabAtom,
    MaterialLabEvidence,
    MaterialLabMaterial,
    MaterialLabPattern,
    MaterialLabRun,
)
from app.db.models import Book, Chapter, Paragraph

from .bridge import chapter_text_from_paragraphs, extract_book_materials, guess_genre
from .dedup import signature, similarity
from .genre_templates import GENRE_ORDER, TEMPLATES, label_index
from .quality import WEIGHTS, _clip, _freq_weight, confidence_of, score_material

#: 与源项目 config.DEFAULTS 一致。
DEDUP_SIMILARITY_THRESHOLD = 0.62


class MaterialLabError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------- 模式簇归并
class _PatternCache:
    """一个 genre 的模式簇，整套载入内存做归并（簇的数量级是几十，不是几万）。"""

    def __init__(self, db: Session, genre_slug: str):
        self.db = db
        self.genre_slug = genre_slug
        self.by_signature: dict[str, MaterialLabPattern] = {}
        self.by_category: dict[str, list[MaterialLabPattern]] = {}
        for p in db.scalars(
            select(MaterialLabPattern).where(MaterialLabPattern.genre_slug == genre_slug)
        ):
            self.by_signature.setdefault(p.signature, p)
            self.by_category.setdefault(p.category_key, []).append(p)

    def assign(self, category_key: str, core_pattern: str,
               mechanism: str) -> tuple[MaterialLabPattern, float]:
        """与源项目 dedup.assign_pattern 同序：先精确签名，再类目内相似度，最后新建。"""
        sig = signature(core_pattern)
        exact = self.by_signature.get(sig)
        if exact is not None:
            return exact, 1.0
        best, best_sim = None, 0.0
        for p in self.by_category.get(category_key, []):
            s = similarity(core_pattern, p.core_pattern)
            if s > best_sim:
                best, best_sim = p, s
        if best is not None and best_sim >= DEDUP_SIMILARITY_THRESHOLD:
            return best, best_sim
        created = MaterialLabPattern(
            genre_slug=self.genre_slug, category_key=category_key,
            core_pattern=core_pattern, mechanism=mechanism, signature=sig,
        )
        self.db.add(created)
        self.db.flush()  # 需要 id
        self.by_signature[sig] = created
        self.by_category.setdefault(category_key, []).append(created)
        return created, 1.0


# ------------------------------------------------------------------- 跑批
def run_material_lab(db: Session, book_id: int, *, genre_slug: str | None = None) -> dict:
    """对一本书跑完整链路：抽取 -> 归簇 -> 评分 -> 落库。同步执行，秒级。"""
    book = db.get(Book, book_id)
    if book is None:
        raise MaterialLabError("MATERIAL_LAB_BOOK_NOT_FOUND", f"book {book_id} 不存在")
    if genre_slug and genre_slug not in TEMPLATES:
        raise MaterialLabError(
            "MATERIAL_LAB_UNKNOWN_GENRE",
            f"未知类型 {genre_slug}，可选：{'/'.join(GENRE_ORDER)}",
        )

    chapters_orm = list(db.scalars(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index)
    ))
    if not chapters_orm:
        raise MaterialLabError("MATERIAL_LAB_BOOK_EMPTY", "这本书没有章节可分析")
    chapter_texts: list[tuple[str, str]] = []
    for ch in chapters_orm:
        paras = db.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == ch.id)
            .order_by(Paragraph.paragraph_index)
        )
        chapter_texts.append((ch.title, chapter_text_from_paragraphs(paras)))

    result = extract_book_materials(chapter_texts, genre_slug or "")
    if not result.genre_slug:
        raise MaterialLabError(
            "MATERIAL_LAB_GENRE_UNDETECTED",
            "无法从文本判断类型，请显式指定 genre_slug",
        )

    # 重跑即重来：清掉这本书名下的派生行（run 历史保留，模式簇稍后收缩计数）。
    for model in (MaterialLabMaterial, MaterialLabAtom, MaterialLabEvidence):
        db.query(model).filter(model.book_id == book_id).delete(synchronize_session=False)

    run = MaterialLabRun(
        book_id=book_id, status="running",
        genre_slug=result.genre_slug,
        genre_source="user" if genre_slug else "auto",
        genre_confidence=result.genre_confidence,
        chapter_count=result.chapter_count,
        scene_count=len(result.scenes),
        duplicate_chapters=result.duplicate_chapters,
        skipped_short_scenes=result.skipped_short_scenes,
    )
    db.add(run)
    db.flush()

    chapter_id_by_seq = {i + 1: ch.id for i, ch in enumerate(chapters_orm)}
    cache = _PatternCache(db, result.genre_slug)

    # 最终频次先算好，评分一次到位（见模块 docstring 第 1 条）。
    run_example_freq: Counter[str] = Counter(
        d.concise_example for sc in result.scenes for d in sc.drafts
    )
    other_books_freq: dict[str, int] = {
        ex: n for ex, n in db.execute(
            select(MaterialLabMaterial.concise_example, func.count())
            .where(MaterialLabMaterial.book_id != book_id)
            .group_by(MaterialLabMaterial.concise_example)
        )
    }

    made = 0
    pattern_rows: dict[int, list[MaterialLabMaterial]] = {}
    for sc in result.scenes:
        chapter_id = chapter_id_by_seq[sc.chapter_seq]
        evidence = MaterialLabEvidence(
            book_id=book_id, chapter_id=chapter_id, run_id=run.id,
            scene_seq=sc.scene_seq, char_start=sc.char_start, char_end=sc.char_end,
            snippet=sc.summary[:180], note="scene head",
        )
        db.add(evidence)
        db.flush()
        for a in sc.atoms:
            db.add(MaterialLabAtom(
                book_id=book_id, chapter_id=chapter_id, run_id=run.id,
                scene_seq=sc.scene_seq, atom_type=a.atom_type,
                value=a.value[:200], norm_value=a.norm_value[:120],
                salience=a.salience, char_pos=sc.char_start + a.char_pos,
                meta_json=json.dumps(a.meta, ensure_ascii=False),
            ))
        for d in sc.drafts:
            pattern, sim = cache.assign(d.category_key, d.core_pattern, d.mechanism)
            row = MaterialLabMaterial(
                book_id=book_id, chapter_id=chapter_id, run_id=run.id,
                pattern_id=pattern.id, evidence_id=evidence.id,
                scene_seq=sc.scene_seq, char_start=sc.char_start, char_end=sc.char_end,
                place=sc.place, time_cue=sc.time_cue,
                genre_slug=result.genre_slug,
                material_type=d.material_type, category_key=d.category_key,
                subcategory_key=d.subcategory_key, title=d.title,
                concise_example=d.concise_example, core_pattern=d.core_pattern,
                mechanism=d.mechanism, suspense_question=d.suspense_question,
                applicable_stage=d.applicable_stage, applicable_scene=d.applicable_scene,
                emotion=d.emotion,
                tags_json=json.dumps(d.tags, ensure_ascii=False),
                signals_json=json.dumps(d.signals, ensure_ascii=False),
                pattern_similarity=sim,
            )
            db.add(row)
            pattern_rows.setdefault(pattern.id, []).append(row)
            made += 1

    # 评分：簇的规模与跨书计数在全部插入之后才是最终值。
    db.flush()
    pattern_book_counts = _pattern_book_counts(db, list(pattern_rows.keys()))
    for pid, rows in pattern_rows.items():
        cluster_size = _cluster_size(db, pid)
        book_count = pattern_book_counts.get(pid, 0)
        for row in rows:
            d_signals = json.loads(row.signals_json)
            ex_freq = run_example_freq[row.concise_example] + \
                other_books_freq.get(row.concise_example, 0)
            score, parts = score_material(
                concise_example=row.concise_example, core_pattern=row.core_pattern,
                mechanism=row.mechanism, suspense_question=row.suspense_question,
                tags=json.loads(row.tags_json), signals=d_signals,
                cluster_size=cluster_size, book_count_for_pattern=book_count,
                evidence_count=1, example_freq=ex_freq,
                book_example_freq=run_example_freq[row.concise_example],
            )
            row.quality_score = score
            row.score_json = json.dumps(parts, ensure_ascii=False)
            row.confidence = confidence_of(1, book_count, d_signals.get("cue_hits", 0))

    refresh_pattern_stats(db)
    mark_primary_variants(db)

    run.status = "done"
    run.material_count = made
    run.finished_at = _utc_now()
    return {
        "run_id": run.id,
        "book_id": book_id,
        "genre_slug": result.genre_slug,
        "genre_source": run.genre_source,
        "genre_confidence": result.genre_confidence,
        "chapters": result.chapter_count,
        "scenes": len(result.scenes),
        "duplicate_chapters": result.duplicate_chapters,
        "skipped_short_scenes": result.skipped_short_scenes,
        "materials": made,
    }


def _cluster_size(db: Session, pattern_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(MaterialLabMaterial)
        .where(MaterialLabMaterial.pattern_id == pattern_id)
    ) or 0


def _pattern_book_counts(db: Session, pattern_ids: list[int]) -> dict[int, int]:
    if not pattern_ids:
        return {}
    rows = db.execute(
        select(MaterialLabMaterial.pattern_id,
               func.count(func.distinct(MaterialLabMaterial.book_id)))
        .where(MaterialLabMaterial.pattern_id.in_(pattern_ids))
        .group_by(MaterialLabMaterial.pattern_id)
    )
    return {pid: n for pid, n in rows}


def refresh_pattern_stats(db: Session) -> None:
    """对应源项目 dedup.refresh_pattern_stats；顺带把空簇清成 0 而不是删行。"""
    counts = {
        pid: (variants, books)
        for pid, variants, books in db.execute(
            select(MaterialLabMaterial.pattern_id, func.count(),
                   func.count(func.distinct(MaterialLabMaterial.book_id)))
            .where(MaterialLabMaterial.pattern_id.is_not(None))
            .group_by(MaterialLabMaterial.pattern_id)
        )
    }
    for p in db.scalars(select(MaterialLabPattern)):
        variants, books = counts.get(p.id, (0, 0))
        if p.variant_count != variants or p.book_count != books:
            p.variant_count = variants
            p.book_count = books


def mark_primary_variants(db: Session) -> None:
    """每个簇里质量最高的一条是展示代表。对应源项目 dedup.mark_primary_variants。"""
    ranked = select(
        MaterialLabMaterial.id,
        func.row_number().over(
            partition_by=MaterialLabMaterial.pattern_id,
            order_by=(MaterialLabMaterial.quality_score.desc(), MaterialLabMaterial.id),
        ).label("rn"),
    ).where(MaterialLabMaterial.pattern_id.is_not(None)).subquery()
    primary_ids = {row_id for row_id, rn in db.execute(select(ranked.c.id, ranked.c.rn))
                   if rn == 1}
    for m in db.scalars(select(MaterialLabMaterial)
                        .where(MaterialLabMaterial.pattern_id.is_not(None))):
        want = 1 if m.id in primary_ids else 0
        if m.is_primary_variant != want:
            m.is_primary_variant = want


def rescore_library(db: Session) -> int:
    """跨书拉平频次型子分。对应源项目 quality.rescore_with_final_counts。

    单本书跑完不需要它（run_material_lab 已经用最终频次评分）；
    多本书陆续入库后，全局 example_freq 变了，才值得跑一次。
    """
    glob: Counter[str] = Counter()
    per_book: Counter[tuple[int, str]] = Counter()
    for book_id, ex, n in db.execute(
        select(MaterialLabMaterial.book_id, MaterialLabMaterial.concise_example,
               func.count())
        .group_by(MaterialLabMaterial.book_id, MaterialLabMaterial.concise_example)
    ):
        glob[ex] += n
        per_book[(book_id, ex)] = n
    updated = 0
    for m in db.scalars(select(MaterialLabMaterial)):
        try:
            parts = json.loads(m.score_json or "{}")
        except ValueError:
            continue
        if not parts:
            continue
        parts["novelty"] = round(_clip(1.0 - _freq_weight(glob[m.concise_example], 60.0)), 3)
        parts["similarity_penalty"] = round(
            _clip(_freq_weight(per_book[(m.book_id, m.concise_example)], 20.0)), 3)
        raw = sum(WEIGHTS[k] * float(parts.get(k, 0.0)) for k in WEIGHTS)
        score = int(round(_clip(raw / 0.96) * 100))
        parts["composite"] = score
        m.quality_score = score
        m.score_json = json.dumps(parts, ensure_ascii=False)
        updated += 1
    mark_primary_variants(db)
    return updated


# ------------------------------------------------------------------- 查询
def genre_options() -> list[dict]:
    return [
        {
            "slug": slug,
            "label": TEMPLATES[slug]["label"],
            "category_count": len(TEMPLATES[slug]["categories"]),
        }
        for slug in GENRE_ORDER
    ]


def suggest_genre(db: Session, book_id: int) -> dict:
    """导入时的类型建议：取全书文本样本跑 guess_genre。"""
    if db.get(Book, book_id) is None:
        raise MaterialLabError("MATERIAL_LAB_BOOK_NOT_FOUND", f"book {book_id} 不存在")
    texts: list[str] = []
    total = 0
    for ch_id in db.scalars(
        select(Chapter.id).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index)
    ):
        for t in db.scalars(
            select(Paragraph.normalized_text).where(Paragraph.chapter_id == ch_id)
            .order_by(Paragraph.paragraph_index)
        ):
            texts.append(t)
            total += len(t)
        if total > 200000:  # guess_genre 只取前 12 万 + 中段 6 万，样本够了
            break
    slug, conf = guess_genre("\n".join(texts))
    label = TEMPLATES[slug]["label"] if slug in TEMPLATES else ""
    return {"genre_slug": slug, "label": label, "confidence": conf}


def book_summary(db: Session, book_id: int) -> dict:
    if db.get(Book, book_id) is None:
        raise MaterialLabError("MATERIAL_LAB_BOOK_NOT_FOUND", f"book {book_id} 不存在")
    last_run = db.scalars(
        select(MaterialLabRun).where(MaterialLabRun.book_id == book_id)
        .order_by(MaterialLabRun.id.desc()).limit(1)
    ).first()
    by_type = {
        k: n for k, n in db.execute(
            select(MaterialLabMaterial.material_type, func.count())
            .where(MaterialLabMaterial.book_id == book_id)
            .group_by(MaterialLabMaterial.material_type)
        )
    }
    cats, _subs = label_index()
    by_category = [
        {"key": k, "label": cats.get(k, k), "count": n}
        for k, n in db.execute(
            select(MaterialLabMaterial.category_key, func.count())
            .where(MaterialLabMaterial.book_id == book_id)
            .group_by(MaterialLabMaterial.category_key)
            .order_by(func.count().desc())
        )
    ]
    total = db.scalar(
        select(func.count()).select_from(MaterialLabMaterial)
        .where(MaterialLabMaterial.book_id == book_id)
    ) or 0
    return {
        "book_id": book_id,
        "material_count": total,
        "by_type": by_type,
        "by_category": by_category,
        "last_run": _run_dict(last_run) if last_run else None,
    }


def _run_dict(run: MaterialLabRun) -> dict:
    return {
        "run_id": run.id,
        "status": run.status,
        "genre_slug": run.genre_slug,
        "genre_source": run.genre_source,
        "genre_confidence": run.genre_confidence,
        "chapters": run.chapter_count,
        "scenes": run.scene_count,
        "materials": run.material_count,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def list_materials(
    db: Session,
    *,
    book_id: int | None = None,
    material_type: str | None = None,
    category_key: str | None = None,
    min_score: int | None = None,
    primary_only: bool = False,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(MaterialLabMaterial)
    if book_id is not None:
        stmt = stmt.where(MaterialLabMaterial.book_id == book_id)
    if material_type:
        stmt = stmt.where(MaterialLabMaterial.material_type == material_type)
    if category_key:
        stmt = stmt.where(MaterialLabMaterial.category_key == category_key)
    if min_score is not None:
        stmt = stmt.where(MaterialLabMaterial.quality_score >= min_score)
    if primary_only:
        stmt = stmt.where(MaterialLabMaterial.is_primary_variant == 1)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            MaterialLabMaterial.title.like(like)
            | MaterialLabMaterial.concise_example.like(like)
            | MaterialLabMaterial.core_pattern.like(like)
            | MaterialLabMaterial.tags_json.like(like)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(MaterialLabMaterial.quality_score.desc(), MaterialLabMaterial.id)
        .limit(min(limit, 200)).offset(offset)
    )
    cats, subs = label_index()
    return {
        "total": total,
        "items": [_material_dict(m, cats, subs) for m in rows],
    }


def _material_dict(m: MaterialLabMaterial, cats: dict, subs: dict) -> dict:
    return {
        "id": m.id,
        "book_id": m.book_id,
        "chapter_id": m.chapter_id,
        "scene_seq": m.scene_seq,
        "place": m.place,
        "time_cue": m.time_cue,
        "genre_slug": m.genre_slug,
        "material_type": m.material_type,
        "category_key": m.category_key,
        "category_label": cats.get(m.category_key, m.category_key),
        "subcategory_key": m.subcategory_key,
        "subcategory_label": subs.get(m.subcategory_key, m.subcategory_key),
        "title": m.title,
        "concise_example": m.concise_example,
        "core_pattern": m.core_pattern,
        "mechanism": m.mechanism,
        "suspense_question": m.suspense_question,
        "applicable_stage": m.applicable_stage,
        "applicable_scene": m.applicable_scene,
        "emotion": m.emotion,
        "tags": json.loads(m.tags_json or "[]"),
        "quality_score": m.quality_score,
        "confidence": m.confidence,
        "pattern_id": m.pattern_id,
        "is_primary_variant": bool(m.is_primary_variant),
    }


def list_patterns(
    db: Session,
    *,
    genre_slug: str | None = None,
    category_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    stmt = select(MaterialLabPattern).where(MaterialLabPattern.variant_count > 0)
    if genre_slug:
        stmt = stmt.where(MaterialLabPattern.genre_slug == genre_slug)
    if category_key:
        stmt = stmt.where(MaterialLabPattern.category_key == category_key)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    cats, _subs = label_index()
    rows = db.scalars(
        stmt.order_by(MaterialLabPattern.variant_count.desc(), MaterialLabPattern.id)
        .limit(min(limit, 500)).offset(offset)
    )
    return {
        "total": total,
        "items": [
            {
                "id": p.id,
                "genre_slug": p.genre_slug,
                "category_key": p.category_key,
                "category_label": cats.get(p.category_key, p.category_key),
                "core_pattern": p.core_pattern,
                "mechanism": p.mechanism,
                "variant_count": p.variant_count,
                "book_count": p.book_count,
            }
            for p in rows
        ],
    }
