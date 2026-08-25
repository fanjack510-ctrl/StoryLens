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
    MaterialLabLegacyMaterial,
    MaterialLabMaterial,
    MaterialLabPattern,
    MaterialLabRun,
)
from app.db.models import Book, Chapter, Paragraph, WholeBookRun
from app.narrative_core.material_kind import FICTION, book_material_kind

from .bridge import (
    chapter_text_from_paragraphs,
    curate_book_materials,
    extract_book_materials,
    guess_genre,
)
from .dedup import signature, similarity
from .genre_templates import GENRE_ORDER, TEMPLATES, label_index
from .quality import WEIGHTS, _clip, _freq_weight, confidence_of, score_material

#: 与源项目 config.DEFAULTS 一致。
DEDUP_SIMILARITY_THRESHOLD = 0.62
FULL_BREAKDOWN_SUFFIX = "+story_breakdown"
FORMAL_RESULT_ORIGINS = {"formal", "real_provider"}


class MaterialLabError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def eligible_knowledge_source_runs(db: Session) -> dict[int, WholeBookRun]:
    """Return the newest completed full-book breakdown for each fiction book.

    Knowledge is a library-level derivative of an already completed breakdown. A
    diagnostic run, an opening-only run, a reference book, or a fixture/non-formal
    run is never a source. This predicate also quarantines old persisted rows.
    """
    newest: dict[int, WholeBookRun] = {}
    runs = db.scalars(
        select(WholeBookRun)
        .where(
            WholeBookRun.status == "completed",
            WholeBookRun.chapter_limit.is_(None),
            WholeBookRun.engine_version.like(f"%{FULL_BREAKDOWN_SUFFIX}"),
            WholeBookRun.result_origin.in_(FORMAL_RESULT_ORIGINS),
        )
        .order_by(WholeBookRun.id.desc())
    )
    for run in runs:
        book_id = int(run.book_id)
        if book_id in newest:
            continue
        if book_material_kind(db, book_id)[0] != FICTION:
            continue
        newest[book_id] = run
    return newest


def _require_eligible_knowledge_source(db: Session, book_id: int) -> WholeBookRun:
    book = db.get(Book, book_id)
    if book is None:
        raise MaterialLabError("MATERIAL_LAB_BOOK_NOT_FOUND", f"book {book_id} 不存在")
    if book_material_kind(db, book_id)[0] != FICTION:
        raise MaterialLabError(
            "MATERIAL_LAB_SOURCE_NOT_FICTION",
            "知识库只从小说提取素材，工具书不会进入这里",
        )
    run = eligible_knowledge_source_runs(db).get(book_id)
    if run is None:
        raise MaterialLabError(
            "MATERIAL_LAB_SOURCE_NOT_FULLY_DISSECTED",
            "这本小说尚未完成全文拆文；评测、进行中任务和只拆开篇都不能作为知识库来源",
        )
    return run


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
    """从一部已完成全文拆文的小说提取知识；只能由全局知识库触发。"""
    _require_eligible_knowledge_source(db, book_id)
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

    curated = curate_book_materials(result)

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
        item.draft.concise_example for item in curated
    )
    eligible_book_ids = set(eligible_knowledge_source_runs(db))
    other_books_freq: dict[str, int] = {
        ex: n for ex, n in db.execute(
            select(MaterialLabMaterial.concise_example, func.count())
            .where(
                MaterialLabMaterial.book_id != book_id,
                MaterialLabMaterial.book_id.in_(eligible_book_ids),
            )
            .group_by(MaterialLabMaterial.concise_example)
        )
    }

    made = 0
    pattern_rows: dict[int, list[MaterialLabMaterial]] = {}
    curated_by_scene: dict[tuple[int, int, int, int], list] = {}
    for item in curated:
        scene_key = (
            item.scene.chapter_seq,
            item.scene.scene_seq,
            item.scene.char_start,
            item.scene.char_end,
        )
        curated_by_scene.setdefault(scene_key, []).append(item.draft)

    for sc in result.scenes:
        scene_key = (sc.chapter_seq, sc.scene_seq, sc.char_start, sc.char_end)
        selected_drafts = curated_by_scene.get(scene_key)
        if not selected_drafts:
            continue
        chapter_id = chapter_id_by_seq[sc.chapter_seq]
        for a in sc.atoms:
            db.add(MaterialLabAtom(
                book_id=book_id, chapter_id=chapter_id, run_id=run.id,
                scene_seq=sc.scene_seq, atom_type=a.atom_type,
                value=a.value[:200], norm_value=a.norm_value[:120],
                salience=a.salience, char_pos=sc.char_start + a.char_pos,
                meta_json=json.dumps(a.meta, ensure_ascii=False),
            ))
        for d in selected_drafts:
            evidence = MaterialLabEvidence(
                book_id=book_id, chapter_id=chapter_id, run_id=run.id,
                scene_seq=sc.scene_seq, char_start=sc.char_start, char_end=sc.char_end,
                snippet=d.concise_example[:180], note="matched evidence sentence",
            )
            db.add(evidence)
            db.flush()
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
        "candidates_scanned": len(result.drafts),
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
    _require_eligible_knowledge_source(db, book_id)
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
    _require_eligible_knowledge_source(db, book_id)
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
    material_kind, material_kind_confirmed = book_material_kind(db, book_id)
    return {
        "book_id": book_id,
        "source_material_kind": material_kind,
        "source_material_kind_confirmed": material_kind_confirmed,
        "knowledge_role": "genre_example" if material_kind == FICTION else "domain_reference",
        "material_count": total,
        "by_type": by_type,
        "by_category": by_category,
        "last_run": _run_dict(last_run) if last_run else None,
    }


def knowledge_library_summary(db: Session) -> dict:
    """全局知识库统计；旧的、不合资格的单书抽取结果会被硬隔离。"""
    eligible_book_ids = set(eligible_knowledge_source_runs(db))
    counts_by_book = {
        book_id: count
        for book_id, count in db.execute(
            select(MaterialLabMaterial.book_id, func.count())
            .where(MaterialLabMaterial.book_id.in_(eligible_book_ids))
            .group_by(MaterialLabMaterial.book_id)
        )
    }
    extracted_count = sum(counts_by_book.values())
    imported_count = int(
        db.scalar(select(func.count()).select_from(MaterialLabLegacyMaterial)) or 0
    )
    legacy_source_book_count = int(
        db.scalar(
            select(func.count(func.distinct(MaterialLabLegacyMaterial.source_book_id)))
        ) or 0
    )
    by_role = {"genre_example": imported_count, "domain_reference": 0}
    sources: list[dict] = []
    if counts_by_book:
        books = {
            book.id: book
            for book in db.scalars(select(Book).where(Book.id.in_(counts_by_book)))
        }
        for book_id, count in counts_by_book.items():
            kind, confirmed = book_material_kind(db, book_id)
            role = "genre_example"
            by_role[role] += count
            book = books.get(book_id)
            sources.append({
                "book_id": book_id,
                "book_title": book.title if book else f"书籍 {book_id}",
                "source_material_kind": kind,
                "source_material_kind_confirmed": confirmed,
                "knowledge_role": role,
                "knowledge_count": count,
            })
    cats, _subs = label_index()
    category_counts: Counter[str] = Counter()
    category_labels: dict[str, str] = {}
    for key, count in db.execute(
        select(MaterialLabMaterial.category_key, func.count())
        .where(MaterialLabMaterial.book_id.in_(eligible_book_ids))
        .group_by(MaterialLabMaterial.category_key)
    ):
        category_counts[key] += count
        category_labels[key] = cats.get(key, key)
    for key, label, count in db.execute(
        select(
            MaterialLabLegacyMaterial.category_key,
            func.max(MaterialLabLegacyMaterial.category_label),
            func.count(),
        ).group_by(MaterialLabLegacyMaterial.category_key)
    ):
        category_counts[key] += count
        category_labels.setdefault(key, label or cats.get(key, key))
    by_category = [
        {"key": key, "label": category_labels.get(key, key), "count": count}
        for key, count in category_counts.most_common(30)
    ]

    genre_counts: Counter[str] = Counter()
    genre_labels: dict[str, str] = {}
    taxonomy_counts: Counter[tuple[str, str]] = Counter()
    taxonomy_labels: dict[tuple[str, str], str] = {}
    # 分类是产品底座，不依赖当前是否已有素材。空库也要完整显示 10 个题材及
    # 各题材自己的分类，避免错误数据被删除后连分类导航一起消失。
    for template_slug in GENRE_ORDER:
        template = TEMPLATES[template_slug]
        genre_counts[template_slug] = 0
        genre_labels[template_slug] = template["label"]
        for template_category in template["categories"]:
            taxonomy_counts[(template_slug, template_category["key"])] = 0
            taxonomy_labels[(template_slug, template_category["key"])] = (
                template_category["label"]
            )
    for slug, count in db.execute(
        select(MaterialLabMaterial.genre_slug, func.count())
        .where(MaterialLabMaterial.book_id.in_(eligible_book_ids))
        .group_by(MaterialLabMaterial.genre_slug)
    ):
        genre_counts[slug] += count
        genre_labels[slug] = TEMPLATES.get(slug, {}).get("label", slug)
    for slug, key, count in db.execute(
        select(
            MaterialLabMaterial.genre_slug,
            MaterialLabMaterial.category_key,
            func.count(),
        )
        .where(MaterialLabMaterial.book_id.in_(eligible_book_ids))
        .group_by(MaterialLabMaterial.genre_slug, MaterialLabMaterial.category_key)
    ):
        taxonomy_counts[(slug, key)] += count
        taxonomy_labels[(slug, key)] = cats.get(key, key)
    for slug, label, count in db.execute(
        select(
            MaterialLabLegacyMaterial.genre_slug,
            func.max(MaterialLabLegacyMaterial.genre_label),
            func.count(),
        ).group_by(MaterialLabLegacyMaterial.genre_slug)
    ):
        genre_counts[slug] += count
        genre_labels.setdefault(slug, label or TEMPLATES.get(slug, {}).get("label", slug))
    for slug, key, label, count in db.execute(
        select(
            MaterialLabLegacyMaterial.genre_slug,
            MaterialLabLegacyMaterial.category_key,
            func.max(MaterialLabLegacyMaterial.category_label),
            func.count(),
        ).group_by(
            MaterialLabLegacyMaterial.genre_slug,
            MaterialLabLegacyMaterial.category_key,
        )
    ):
        taxonomy_counts[(slug, key)] += count
        taxonomy_labels.setdefault((slug, key), label or cats.get(key, key))
    extra_genres = sorted(set(genre_counts) - set(GENRE_ORDER))
    by_genre = [
        {"slug": slug, "label": genre_labels.get(slug, slug), "count": count}
        for slug in [*GENRE_ORDER, *extra_genres]
        for count in [genre_counts[slug]]
    ]
    taxonomy = [
        {
            "slug": item["slug"],
            "label": item["label"],
            "count": item["count"],
            "categories": (
                [
                    {
                        "key": category["key"],
                        "label": category["label"],
                        "count": taxonomy_counts[(item["slug"], category["key"])],
                    }
                    for category in TEMPLATES[item["slug"]]["categories"]
                ]
                if item["slug"] in TEMPLATES
                else [
                    {
                        "key": key,
                        "label": taxonomy_labels.get((item["slug"], key), key),
                        "count": count,
                    }
                    for (slug, key), count in sorted(
                        taxonomy_counts.items(), key=lambda pair: (-pair[1], pair[0][1])
                    )
                    if slug == item["slug"]
                ]
            ),
        }
        for item in by_genre
    ]
    return {
        "knowledge_count": extracted_count + imported_count,
        "extracted_knowledge_count": extracted_count,
        "imported_knowledge_count": imported_count,
        "source_book_count": len(counts_by_book),
        "legacy_source_book_count": legacy_source_book_count,
        "by_role": by_role,
        "by_genre": by_genre,
        "by_category": by_category,
        "taxonomy": taxonomy,
        "sources": sorted(sources, key=lambda row: (-row["knowledge_count"], row["book_id"])),
    }


def list_knowledge_sources(db: Session) -> dict:
    """List every novel currently eligible to feed the standalone knowledge page."""
    eligible = eligible_knowledge_source_runs(db)
    if not eligible:
        return {"total": 0, "items": []}
    counts = {
        book_id: count
        for book_id, count in db.execute(
            select(MaterialLabMaterial.book_id, func.count())
            .where(MaterialLabMaterial.book_id.in_(eligible))
            .group_by(MaterialLabMaterial.book_id)
        )
    }
    books = {
        int(book.id): book
        for book in db.scalars(select(Book).where(Book.id.in_(eligible)))
    }
    last_runs = {
        int(run.book_id): run
        for run in db.scalars(
            select(MaterialLabRun)
            .where(MaterialLabRun.book_id.in_(eligible), MaterialLabRun.status == "done")
            .order_by(MaterialLabRun.id.asc())
        )
    }
    items = []
    for book_id, breakdown_run in eligible.items():
        book = books.get(book_id)
        extraction = last_runs.get(book_id)
        material_count = int(counts.get(book_id, 0) or 0)
        items.append(
            {
                "book_id": book_id,
                "book_title": book.title if book else f"书籍 {book_id}",
                "breakdown_run_id": int(breakdown_run.id),
                "breakdown_completed_at": (
                    breakdown_run.completed_at.isoformat()
                    if breakdown_run.completed_at
                    else None
                ),
                "material_count": material_count,
                "genre_slug": extraction.genre_slug if extraction else "",
                "extracted": material_count > 0,
            }
        )
    items.sort(key=lambda item: (not item["extracted"], -item["book_id"]))
    return {"total": len(items), "items": items}


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
    genre_slug: str | None = None,
    knowledge_role: str | None = None,
    material_type: str | None = None,
    category_key: str | None = None,
    min_score: int | None = None,
    primary_only: bool = False,
    q: str | None = None,
    source_kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    if source_kind not in {None, "whole_book", "legacy_import"}:
        raise MaterialLabError(
            "MATERIAL_LAB_UNKNOWN_SOURCE_KIND", f"未知素材来源 {source_kind}"
        )
    eligible_book_ids = set(eligible_knowledge_source_runs(db))
    stmt = select(MaterialLabMaterial).where(
        MaterialLabMaterial.book_id.in_(eligible_book_ids)
    )
    if book_id is not None:
        stmt = stmt.where(MaterialLabMaterial.book_id == book_id)
    if genre_slug:
        stmt = stmt.where(MaterialLabMaterial.genre_slug == genre_slug)
    if knowledge_role:
        if knowledge_role not in {"genre_example", "domain_reference"}:
            raise MaterialLabError(
                "MATERIAL_LAB_UNKNOWN_KNOWLEDGE_ROLE",
                f"未知知识来源类型 {knowledge_role}",
            )
        matching_book_ids = list(eligible_book_ids) if knowledge_role == "genre_example" else []
        stmt = stmt.where(MaterialLabMaterial.book_id.in_(matching_book_ids))
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
    legacy_stmt = select(MaterialLabLegacyMaterial)
    if book_id is not None:
        legacy_stmt = legacy_stmt.where(False)
    if genre_slug:
        legacy_stmt = legacy_stmt.where(MaterialLabLegacyMaterial.genre_slug == genre_slug)
    if knowledge_role == "domain_reference":
        legacy_stmt = legacy_stmt.where(False)
    if material_type:
        legacy_stmt = legacy_stmt.where(
            MaterialLabLegacyMaterial.material_type == material_type
        )
    if category_key:
        legacy_stmt = legacy_stmt.where(
            MaterialLabLegacyMaterial.category_key == category_key
        )
    if min_score is not None:
        legacy_stmt = legacy_stmt.where(
            MaterialLabLegacyMaterial.quality_score >= min_score
        )
    if primary_only:
        legacy_stmt = legacy_stmt.where(
            MaterialLabLegacyMaterial.is_primary_variant == 1
        )
    if q:
        like = f"%{q}%"
        legacy_stmt = legacy_stmt.where(
            MaterialLabLegacyMaterial.title.like(like)
            | MaterialLabLegacyMaterial.concise_example.like(like)
            | MaterialLabLegacyMaterial.core_pattern.like(like)
            | MaterialLabLegacyMaterial.tags_json.like(like)
        )

    use_current = source_kind != "legacy_import"
    use_legacy = source_kind != "whole_book"
    current_total = (
        int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        if use_current else 0
    )
    legacy_total = (
        int(db.scalar(select(func.count()).select_from(legacy_stmt.subquery())) or 0)
        if use_legacy else 0
    )
    top = min(offset + min(limit, 200), current_total + legacy_total)
    current_candidates = list(db.scalars(
        stmt.order_by(MaterialLabMaterial.quality_score.desc(), MaterialLabMaterial.id)
        .limit(top)
    )) if use_current and top else []
    legacy_candidates = list(db.scalars(
        legacy_stmt.order_by(
            MaterialLabLegacyMaterial.quality_score.desc(),
            MaterialLabLegacyMaterial.id,
        ).limit(top)
    )) if use_legacy and top else []
    combined: list[tuple[str, MaterialLabMaterial | MaterialLabLegacyMaterial]] = [
        ("whole_book", row) for row in current_candidates
    ] + [("legacy_import", row) for row in legacy_candidates]
    combined.sort(key=lambda pair: (-pair[1].quality_score, pair[0], pair[1].id))
    selected = combined[offset:offset + min(limit, 200)]
    rows = [row for origin, row in selected if origin == "whole_book"]
    cats, subs = label_index()
    source_book_kinds: dict[int, tuple[str, bool]] = {
        source_book_id: book_material_kind(db, source_book_id)
        for source_book_id in {m.book_id for m in rows}
    }
    source_book_titles = {
        book.id: book.title
        for book in db.scalars(
            select(Book).where(Book.id.in_({m.book_id for m in rows}))
        )
    } if rows else {}
    evidence_ids = {m.evidence_id for m in rows if m.evidence_id is not None}
    evidence_by_id = {
        e.id: e for e in db.scalars(
            select(MaterialLabEvidence).where(MaterialLabEvidence.id.in_(evidence_ids))
        )
    } if evidence_ids else {}
    paragraph_ids = _source_paragraph_ids(db, rows)
    return {
        "total": current_total + legacy_total,
        "items": [
            (
                _material_dict(
                    m, cats, subs,
                    evidence=evidence_by_id.get(m.evidence_id),
                    source_paragraph_ids=paragraph_ids.get(m.id, []),
                    source_material_kind=source_book_kinds[m.book_id][0],
                    source_material_kind_confirmed=source_book_kinds[m.book_id][1],
                    source_book_title=source_book_titles.get(
                        m.book_id, f"书籍 {m.book_id}"
                    ),
                )
                if origin == "whole_book"
                else _legacy_material_dict(m)
            )
            for origin, m in selected
        ],
    }


def _legacy_material_dict(m: MaterialLabLegacyMaterial) -> dict:
    is_reference_corpus = (m.source_pattern_id or "").startswith("corpus:")
    evidence: dict = {}
    evidence_rows: list[dict] = []
    if is_reference_corpus:
        try:
            parsed_evidence = json.loads(m.source_evidence_ids_json or "{}")
            evidence = parsed_evidence if isinstance(parsed_evidence, dict) else {}
            nested = evidence.get("evidence")
            if isinstance(nested, list):
                evidence_rows = [row for row in nested if isinstance(row, dict)]
        except ValueError:
            evidence = {}
    primary_evidence = evidence_rows[0] if evidence_rows else evidence
    pipeline_version = str(evidence.get("pipeline_version") or "")
    is_structured_reference = pipeline_version.startswith("structured-farming-docx-")
    source_excerpt = "\n\n".join(
        str(row.get("text") or row.get("excerpt") or "").strip()
        for row in (evidence_rows or [evidence])[:3]
        if str(row.get("text") or row.get("excerpt") or "").strip()
    )
    source_paragraph_ids = [
        str(row.get("evidence_id"))
        for row in evidence_rows
        if row.get("evidence_id")
    ]
    if not source_paragraph_ids and primary_evidence.get("chapter_index"):
        source_paragraph_ids = [f"第{int(primary_evidence['chapter_index'])}章"]
    chapter_labels = list(dict.fromkeys(
        str(row.get("chapter_title") or f"第{row.get('chapter_index')}章")
        for row in evidence_rows
        if row.get("chapter_title") or row.get("chapter_index")
    ))
    return {
        "id": f"legacy:{m.source_material_id}",
        "origin": "reference_corpus" if is_reference_corpus else "legacy_import",
        "book_id": None,
        "source_book_title": m.source_book_title if is_reference_corpus else "旧项目资料库",
        "chapter_id": None,
        "scene_seq": int(primary_evidence.get("paragraph_index") or primary_evidence.get("scene_seq") or 0),
        "place": "",
        "time_cue": "",
        "genre_slug": m.genre_slug,
        "material_type": m.material_type,
        "category_key": m.category_key,
        "category_label": m.category_label or m.category_key,
        "subcategory_key": m.subcategory_key,
        "subcategory_label": m.subcategory_label or m.subcategory_key,
        "title": m.title,
        "source_excerpt": source_excerpt,
        "source_paragraph_ids": source_paragraph_ids,
        "source_material_kind": "reference" if is_structured_reference else "fiction",
        "source_material_kind_confirmed": True,
        "knowledge_role": "domain_reference" if is_structured_reference else "genre_example",
        "knowledge_role_label": (
            "种田资料知识"
            if is_structured_reference
            else ("参考小说知识" if is_reference_corpus else "旧库知识")
        ),
        "verification_label": (
            ("本地写作资料 · " if is_structured_reference else "本地参考小说 · ")
            + (" / ".join(chapter_labels) if chapter_labels else "章节待定位")
            + (" · 三段资料依据已核对" if is_structured_reference else " · 段落证据已核对")
            if is_reference_corpus
            else "旧项目派生层已迁入；未复制小说正文或原文摘录"
        ),
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
        "pattern_id": m.source_pattern_id or None,
        "is_primary_variant": bool(m.is_primary_variant),
    }


def _source_paragraph_ids(
    db: Session, materials: list[MaterialLabMaterial]
) -> dict[int, list[str]]:
    """把场景的章内偏移还原到真实 Paragraph ID，供知识条目溯源。"""
    chapter_ids = {m.chapter_id for m in materials}
    if not chapter_ids:
        return {}
    paragraphs_by_chapter: dict[int, list[Paragraph]] = {}
    for paragraph in db.scalars(
        select(Paragraph)
        .where(Paragraph.chapter_id.in_(chapter_ids))
        .order_by(Paragraph.chapter_id, Paragraph.paragraph_index)
    ):
        paragraphs_by_chapter.setdefault(paragraph.chapter_id, []).append(paragraph)

    spans_by_chapter: dict[int, list[tuple[str, int, int]]] = {}
    for chapter_id, paragraphs in paragraphs_by_chapter.items():
        cursor = 0
        spans: list[tuple[str, int, int]] = []
        for paragraph in paragraphs:
            text_value = paragraph.normalized_text or paragraph.raw_text or ""
            end = cursor + len(text_value)
            spans.append((paragraph.id, cursor, end))
            cursor = end + 1  # chapter_text_from_paragraphs 使用单个换行连接。
        spans_by_chapter[chapter_id] = spans

    return {
        material.id: [
            paragraph_id
            for paragraph_id, start, end in spans_by_chapter.get(material.chapter_id, [])
            if end > material.char_start and start < material.char_end
        ]
        for material in materials
    }


def _material_dict(
    m: MaterialLabMaterial,
    cats: dict,
    subs: dict,
    *,
    evidence: MaterialLabEvidence | None = None,
    source_paragraph_ids: list[str] | None = None,
    source_material_kind: str = FICTION,
    source_material_kind_confirmed: bool = False,
    source_book_title: str = "",
) -> dict:
    is_fiction = source_material_kind == FICTION
    return {
        "id": m.id,
        "origin": "whole_book",
        "book_id": m.book_id,
        "source_book_title": source_book_title,
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
        "source_excerpt": evidence.snippet if evidence else "",
        "source_paragraph_ids": source_paragraph_ids or [],
        "source_material_kind": source_material_kind,
        "source_material_kind_confirmed": source_material_kind_confirmed,
        "knowledge_role": "genre_example" if is_fiction else "domain_reference",
        "knowledge_role_label": "题材案例" if is_fiction else "领域资料",
        "verification_label": (
            "原文可核对，但不能作为事实依据"
            if is_fiction
            else "原文可核对，来源可信度待确认"
        ),
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
    eligible_book_ids = set(eligible_knowledge_source_runs(db))
    counts = (
        select(
            MaterialLabMaterial.pattern_id.label("pattern_id"),
            func.count().label("variant_count"),
            func.count(func.distinct(MaterialLabMaterial.book_id)).label("book_count"),
        )
        .where(
            MaterialLabMaterial.book_id.in_(eligible_book_ids),
            MaterialLabMaterial.pattern_id.is_not(None),
        )
        .group_by(MaterialLabMaterial.pattern_id)
        .subquery()
    )
    stmt = select(MaterialLabPattern, counts.c.variant_count, counts.c.book_count).join(
        counts, counts.c.pattern_id == MaterialLabPattern.id
    )
    if genre_slug:
        stmt = stmt.where(MaterialLabPattern.genre_slug == genre_slug)
    if category_key:
        stmt = stmt.where(MaterialLabPattern.category_key == category_key)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    cats, _subs = label_index()
    rows = db.execute(
        stmt.order_by(counts.c.variant_count.desc(), MaterialLabPattern.id)
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
                "variant_count": variant_count,
                "book_count": book_count,
            }
            for p, variant_count, book_count in rows
        ],
    }
