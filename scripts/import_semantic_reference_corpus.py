"""Create a small, evidence-backed reference corpus with the active model gateway.

This is intentionally not a bulk importer.  It deep-reads a few explicitly
selected novels, asks the model to synthesize reusable knowledge, performs a
second review pass, then appends a curated batch. Re-running the same source
selection replaces only that batch, leaving previously approved batches intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
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
from app.domain.ingestion import split_chapters  # noqa: E402
from app.model_gateway.base import ModelRequest  # noqa: E402
from app.narrative_core.material_lab.dedup import signature  # noqa: E402
from app.narrative_core.material_lab.genre_templates import TEMPLATES  # noqa: E402
from app.narrative_core.material_lab.semantic_reference_corpus import (  # noqa: E402
    PIPELINE_VERSION,
    SEMANTIC_CATEGORY_KEYS,
    EvidenceCandidate,
    EvidenceAuditBatch,
    SemanticExtractionBatch,
    SemanticReviewBatch,
    apply_evidence_audit,
    build_evidence_audit_prompt,
    build_extraction_prompt,
    build_review_prompt,
    filter_ancient_domain_knowledge,
    filter_disaster_domain_knowledge,
    filter_contemporary_domain_knowledge,
    filter_fantasy_domain_knowledge,
    filter_infinite_flow_domain_knowledge,
    filter_farming_domain_knowledge,
    filter_scifi_domain_knowledge,
    filter_urban_domain_knowledge,
    filter_xianxia_domain_knowledge,
    group_evidence_round_robin,
    parse_json_object,
    validate_drafts,
    validate_review,
)
from app.narrative_core.services.whole_book_active_provider_v1 import (  # noqa: E402
    active_provider_availability,
)
from app.narrative_core.services.whole_book_cost_estimate_service import (  # noqa: E402
    _resolve_model_name,
)
from app.narrative_core.services.whole_book_provider_gateway import _run_async  # noqa: E402
from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (  # noqa: E402
    _bind_formal_gateway,
)


DEFAULT_TITLES = ("盗墓笔记", "离魂镜", "见鬼事务所")
MAX_EVIDENCE_PER_BOOK = 18
MAX_FINAL_PER_BOOK = 12
WINDOW_MAX_CHARS = 520
_GENERAL_ANOMALY_CUES = (
    "不对", "奇怪", "异常", "诡异", "没想到", "竟然", "居然", "失踪",
    "尸体", "死者", "死亡", "钥匙", "照片", "纸条", "档案", "记录",
    "血迹", "脚印", "反锁", "谎", "不记得", "想不起", "同一时间",
)
_GENERAL_FARMING_CUES = (
    "田", "地", "种", "苗", "粮", "收", "晒", "仓", "水", "沟", "井",
    "雨", "旱", "霜", "土", "肥", "虫", "鸡", "鸭", "猪", "牛", "羊",
    "喂", "磨", "腌", "酿", "作坊", "银子",
)
_GENERAL_ANCIENT_CUES = (
    "嫡", "庶", "妾", "主母", "老夫人", "宗祠", "族老", "族规", "婚书",
    "聘", "嫁妆", "媒人", "议亲", "联姻", "官职", "升迁", "贬", "弹劾",
    "皇后", "贵妃", "嫔", "选秀", "宫规", "中馈", "账册", "月例", "钥匙",
)
_GENERAL_URBAN_CUES = (
    "公司", "部门", "岗位", "主管", "合同", "客户", "项目", "报价", "谈判",
    "股权", "股份", "董事会", "融资", "贷款", "现金流", "回款", "律师", "法院",
    "证据", "委托", "练习生", "经纪人", "录音", "专辑", "宣传", "电视台", "租房",
    "物业", "银行", "医院",
)
_GENERAL_SCIFI_CUES = (
    "假设", "理论", "实验", "观测", "信号", "装置", "系统", "芯片", "接口",
    "引擎", "算法", "能源", "机甲", "飞船", "护盾", "导航", "基因", "克隆",
    "意识", "联邦", "研究所", "配额", "等级", "许可", "代价", "副作用", "失控",
    "故障", "断联", "过载", "灾难", "连锁",
)
_GENERAL_DISASTER_CUES = (
    "感染", "病毒", "辐射", "污染", "丧尸", "变异", "食物", "饮水", "净水",
    "罐头", "药品", "包扎", "隔离", "卫生", "避难所", "基地", "围墙", "路障",
    "发电", "燃料", "仓库", "库存", "配给", "运输", "维修", "暴雨", "严寒",
    "值守", "巡逻", "分工", "处罚", "弱点", "聚集",
)
_GENERAL_FANTASY_CUES = (
    "大陆", "种族", "境界", "功法", "斗气", "魔力", "血脉", "体质", "丹药",
    "灵石", "材料", "炼器", "拍卖", "商会", "宗门", "家族", "考核", "资格",
    "秘境", "遗迹", "消耗", "反噬", "限制",
)
_GENERAL_XIANXIA_CUES = (
    "道心", "天劫", "炼气", "筑基", "金丹", "元婴", "功法", "师父", "外门",
    "内门", "炼丹", "丹炉", "炼器", "符箓", "阵法", "贡献", "坊市", "灵石",
    "秘境", "洞府", "灵脉", "灵兽", "神识", "法力", "反噬", "寿元",
)
_GENERAL_CONTEMPORARY_CUES = (
    "父母", "公婆", "分家", "家务", "工资", "存折", "结婚证", "领证", "户口",
    "随军", "粮票", "供销社", "单位", "知青", "招工", "家属院", "住房", "租金",
    "生活费", "摆摊", "调岗", "转正", "借钱", "入学", "住院", "介绍信", "街道",
)
_GENERAL_INFINITE_FLOW_CUES = (
    "副本", "关卡", "规则", "须知", "禁止", "隐藏规则", "任务", "死亡", "淘汰",
    "抹杀", "线索", "纸条", "提示", "验证", "破解", "漏洞", "分工", "积分", "道具",
    "兑换", "结算", "传送", "倒计时", "返回", "下一场",
)


def _decode(path: Path, preferred: str) -> str:
    raw = path.read_bytes()
    for encoding in (preferred.replace("-replace", ""), "utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("gb18030", errors="replace")


def _position(chapter_index: int, total: int) -> str:
    if chapter_index <= 3:
        return "opening"
    ratio = chapter_index / max(total, 1)
    if ratio <= 0.25:
        return "early"
    if ratio <= 0.75:
        return "middle"
    return "late"


def _category_cues(genre_slug: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = defaultdict(list)
    category_keys = SEMANTIC_CATEGORY_KEYS[genre_slug]
    for category in TEMPLATES[genre_slug]["categories"]:
        if category["key"] not in category_keys:
            continue
        result[category["key"]].extend(category.get("cues") or [])
        for sub in category["subcategories"]:
            result[category["key"]].extend(sub.get("cues") or [])
    return {key: tuple(dict.fromkeys(values)) for key, values in result.items()}


def _windowed(paragraphs: list[str]) -> list[tuple[int, str]]:
    windows: list[tuple[int, str]] = []
    index = 0
    while index < len(paragraphs):
        parts: list[str] = []
        start = index
        chars = 0
        while index < len(paragraphs) and chars < 220:
            text = re.sub(r"\s+", " ", paragraphs[index]).strip()
            index += 1
            if not text:
                continue
            if chars + len(text) > WINDOW_MAX_CHARS and parts:
                index -= 1
                break
            parts.append(text)
            chars += len(text)
        joined = " ".join(parts)[:WINDOW_MAX_CHARS]
        if len(joined) >= 35:
            windows.append((start + 1, joined))
    return windows


def discover_candidates(
    *,
    source_title: str,
    fingerprint: str,
    text: str,
    genre_slug: str = "xuanyi",
) -> list[EvidenceCandidate]:
    chapters = split_chapters(text)
    category_keys = SEMANTIC_CATEGORY_KEYS[genre_slug]
    cues_by_category = _category_cues(genre_slug)
    general_cues = {
        "zhongtian": _GENERAL_FARMING_CUES,
        "guyan": _GENERAL_ANCIENT_CUES,
        "dushi": _GENERAL_URBAN_CUES,
        "kehuan": _GENERAL_SCIFI_CUES,
        "moshi": _GENERAL_DISASTER_CUES,
        "xuanhuan": _GENERAL_FANTASY_CUES,
        "xianxia": _GENERAL_XIANXIA_CUES,
        "xianyan": _GENERAL_CONTEMPORARY_CUES,
        "wuxianliu": _GENERAL_INFINITE_FLOW_CUES,
    }.get(genre_slug, _GENERAL_ANOMALY_CUES)
    scored: list[tuple[float, EvidenceCandidate]] = []
    seen: set[str] = set()
    for chapter_index, chapter in enumerate(chapters, 1):
        position = _position(chapter_index, len(chapters))
        for paragraph_index, window in _windowed(chapter.paragraphs):
            normalized = re.sub(r"\W+", "", window)
            if normalized in seen:
                continue
            seen.add(normalized)
            general = sum(window.count(cue) for cue in general_cues)
            for category, cues in cues_by_category.items():
                cue_hits = sum(window.count(cue) for cue in cues)
                opening_bonus = 5 if category == "opening_anomaly" and position == "opening" else 0
                if category == "opening_anomaly" and position != "opening":
                    continue
                score = cue_hits * 3 + general + opening_bonus
                if score < (4 if category != "opening_anomaly" else 5):
                    continue
                evidence_id = (
                    f"R-{fingerprint[:10]}-C{chapter_index:04d}-P{paragraph_index:04d}"
                )
                scored.append((score, EvidenceCandidate(
                    evidence_id=evidence_id,
                    source_title=source_title,
                    chapter_index=chapter_index,
                    chapter_title=chapter.title,
                    paragraph_index=paragraph_index,
                    position=position,
                    suggested_category=category,
                    text=window,
                )))
    # Same evidence window may score in several categories. Keep the strongest
    # category assignment so the prompt remains compact and inexpensive.
    best_by_id: dict[str, tuple[float, EvidenceCandidate]] = {}
    for score, candidate in scored:
        current = best_by_id.get(candidate.evidence_id)
        if current is None or score > current[0]:
            best_by_id[candidate.evidence_id] = (score, candidate)
    ordered = [row[1] for row in sorted(best_by_id.values(), key=lambda row: -row[0])]
    return group_evidence_round_robin(
        ordered,
        limit=MAX_EVIDENCE_PER_BOOK,
        category_keys=category_keys,
    )


def _call_json(gateway, provider_name: str, model: str, prompt: str, schema) -> dict:
    response = _run_async(gateway.generate(
        provider_name,
        ModelRequest(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_output_tokens=4096,
            response_format_mode="json_object",
            enable_thinking=False,
        ),
    ))
    return parse_json_object(response.text)


def _category_labels(
    genre_slug: str, category_key: str, subcategory_key: str
) -> tuple[str, str]:
    for category in TEMPLATES[genre_slug]["categories"]:
        if category["key"] != category_key:
            continue
        for sub in category["subcategories"]:
            if sub["key"] == subcategory_key:
                return category["label"], sub["label"]
    raise ValueError(f"unknown category {category_key}/{subcategory_key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--titles", nargs="*", default=list(DEFAULT_TITLES))
    parser.add_argument(
        "--genre",
        choices=sorted(SEMANTIC_CATEGORY_KEYS),
        default="xuanyi",
        help="题材模板；当前语义管线支持悬疑和种田",
    )
    args = parser.parse_args()
    root = args.source.resolve()
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    wanted = set(args.titles)
    records = [
        row for row in scan["records"]
        if row["decision"] == "accepted"
        and row["genre_slug"] == args.genre
        and Path(row["relative_path"]).stem in wanted
    ]
    missing = wanted - {Path(row["relative_path"]).stem for row in records}
    if missing:
        raise SystemExit("missing accepted titles: " + "、".join(sorted(missing)))

    create_db()
    started = time.monotonic()
    outputs: list[tuple[dict, list, dict]] = []
    failures: list[dict[str, str]] = []
    with SessionLocal() as db:
        provider_row, provider_name, blockers = active_provider_availability(db)
        if provider_row is None or blockers:
            raise SystemExit(blockers[0] if blockers else "no active model provider")
        model = _resolve_model_name(provider_row)
        if not model:
            raise SystemExit("active provider has no model")
        gateway = _bind_formal_gateway(db, provider_name=provider_name)

        for record in sorted(records, key=lambda row: row["relative_path"]):
            title = Path(record["relative_path"]).stem
            stage = "candidate_discovery"
            try:
                text = _decode(root / Path(record["relative_path"]), record["encoding"])
                candidates = discover_candidates(
                    source_title=title,
                    fingerprint=record["fingerprint"],
                    text=text,
                    genre_slug=args.genre,
                )
                evidence_by_id = {item.evidence_id: item for item in candidates}
                stage = "semantic_extraction"
                raw_batch = _call_json(
                    gateway, provider_name, model,
                    build_extraction_prompt(
                        source_title=title,
                        candidates=candidates,
                        genre_slug=args.genre,
                    ),
                    SemanticExtractionBatch,
                )
                batch = SemanticExtractionBatch.model_validate(raw_batch)
                valid_drafts, draft_rejections = validate_drafts(
                    batch,
                    evidence_by_id=evidence_by_id,
                    genre_slug=args.genre,
                )
                if not valid_drafts:
                    raise ValueError(
                        "extraction produced no valid drafts: "
                        + json.dumps({
                            "draft_count": len(batch.materials),
                            "raw_keys": sorted(raw_batch.keys()),
                            "raw_preview": str(raw_batch)[:800],
                            "rejections": draft_rejections,
                            "returned": [
                                {
                                    "draft_id": item.draft_id,
                                    "category": item.category_key,
                                    "subcategory": item.subcategory_key,
                                    "evidence_ids": item.evidence_ids,
                                }
                                for item in batch.materials
                            ],
                        }, ensure_ascii=False)
                    )
                stage = "quality_review"
                raw_review = _call_json(
                    gateway, provider_name, model,
                    build_review_prompt(
                        drafts=valid_drafts,
                        evidence_by_id=evidence_by_id,
                        genre_slug=args.genre,
                    ),
                    SemanticReviewBatch,
                )
                review = SemanticReviewBatch.model_validate(raw_review)
                accepted, review_rejections = validate_review(
                    review,
                    source_drafts=valid_drafts,
                    evidence_by_id=evidence_by_id,
                )
                if not accepted:
                    raise ValueError("review accepted no materials")
                stage = "evidence_audit"
                raw_audit = _call_json(
                    gateway, provider_name, model,
                    build_evidence_audit_prompt(
                        items=accepted,
                        evidence_by_id=evidence_by_id,
                        genre_slug=args.genre,
                    ),
                    EvidenceAuditBatch,
                )
                audit = EvidenceAuditBatch.model_validate(raw_audit)
                accepted, audit_rejections = apply_evidence_audit(
                    audit,
                    reviewed=accepted,
                    evidence_by_id=evidence_by_id,
                )
                relevance_rejections: list[str] = []
                if args.genre == "zhongtian":
                    accepted, relevance_rejections = filter_farming_domain_knowledge(
                        accepted
                    )
                elif args.genre == "guyan":
                    accepted, relevance_rejections = filter_ancient_domain_knowledge(
                        accepted
                    )
                elif args.genre == "dushi":
                    accepted, relevance_rejections = filter_urban_domain_knowledge(
                        accepted
                    )
                elif args.genre == "kehuan":
                    accepted, relevance_rejections = filter_scifi_domain_knowledge(
                        accepted
                    )
                elif args.genre == "moshi":
                    accepted, relevance_rejections = filter_disaster_domain_knowledge(
                        accepted
                    )
                elif args.genre == "xuanhuan":
                    accepted, relevance_rejections = filter_fantasy_domain_knowledge(
                        accepted
                    )
                elif args.genre == "xianxia":
                    accepted, relevance_rejections = filter_xianxia_domain_knowledge(
                        accepted
                    )
                elif args.genre == "xianyan":
                    accepted, relevance_rejections = filter_contemporary_domain_knowledge(
                        accepted
                    )
                elif args.genre == "wuxianliu":
                    accepted, relevance_rejections = filter_infinite_flow_domain_knowledge(
                        accepted
                    )
                accepted = accepted[:MAX_FINAL_PER_BOOK]
                if not accepted:
                    raise ValueError("evidence audit accepted no materials")
                outputs.append((record, accepted, evidence_by_id))
                print(json.dumps({
                    "source": title,
                    "evidence_candidates": len(candidates),
                    "drafts": len(batch.materials),
                    "accepted": len(accepted),
                    "rejected": (
                        draft_rejections
                        + review_rejections
                        + audit_rejections
                        + relevance_rejections
                    ),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:
                safe = exc.as_safe_dict() if hasattr(exc, "as_safe_dict") else {}
                failures.append({
                    "source": title,
                    "stage": stage,
                    "error": str(exc)[:500],
                    "provider_error": {
                        key: safe.get(key)
                        for key in (
                            "error_code", "http_status", "provider_error_code",
                            "provider_message", "response_content_type",
                            "sanitized_response_excerpt",
                        )
                        if safe.get(key) is not None
                    },
                })
                print(json.dumps(failures[-1], ensure_ascii=False), flush=True)

        if not outputs:
            raise SystemExit("all semantic extraction batches failed")

        fingerprint = hashlib.sha256(
            (PIPELINE_VERSION + "|" + args.genre + "|" + "|".join(
                sorted(row["fingerprint"] for row in records)
            )).encode("utf-8")
        ).hexdigest()
        # Append independent curated batches. Re-running the exact same source
        # selection replaces only that batch; previously approved batches stay
        # untouched. This keeps retryability without turning every expansion
        # into an expensive re-analysis of the entire corpus.
        old_ids = list(db.scalars(select(MaterialLabLegacyImport.id).where(
            MaterialLabLegacyImport.source_fingerprint == fingerprint
        )))
        if old_ids:
            db.execute(delete(MaterialLabLegacyImport).where(
                MaterialLabLegacyImport.id.in_(old_ids)
            ))
            db.flush()

        now = datetime.now(timezone.utc)
        batch_row = MaterialLabLegacyImport(
            source_fingerprint=fingerprint,
            source_name=(
                f"semantic-reference-corpus:{args.genre}:{root.name}:{fingerprint[:12]}"
            ),
            source_size=sum(row["byte_size"] for row, _, _ in outputs),
            status="done" if not failures else "completed_with_errors",
            source_material_count=len(records),
            imported_count=sum(len(items) for _, items, _ in outputs),
            skipped_count=len(failures),
            error_message=json.dumps(failures, ensure_ascii=False) if failures else None,
            created_at=now,
            finished_at=now,
        )
        db.add(batch_row)
        db.flush()

        seen: set[str] = set()
        inserted = 0
        for record, items, evidence_by_id in outputs:
            title = Path(record["relative_path"]).stem
            for item in items:
                normalized = re.sub(r"\W+", "", item.creative_material)
                if normalized in seen:
                    continue
                seen.add(normalized)
                category_label, subcategory_label = _category_labels(
                    args.genre, item.category_key, item.subcategory_key
                )
                evidence = [
                    evidence_by_id[eid].model_dump() for eid in item.evidence_ids
                ]
                material_id = hashlib.sha256(
                    f"{record['fingerprint']}|{item.draft_id}|{normalized}".encode("utf-8")
                ).hexdigest()[:32]
                score_values = item.scores.model_dump()
                quality_score = round(sum(score_values.values()) / 25 * 100)
                db.add(MaterialLabLegacyMaterial(
                    import_id=batch_row.id,
                    source_fingerprint=fingerprint,
                    source_material_id=material_id,
                    source_pattern_id=f"corpus:semantic:{signature(item.reusable_pattern)}",
                    source_book_id=record["fingerprint"],
                    source_book_title=title,
                    source_scene_id=",".join(item.evidence_ids),
                    source_evidence_ids_json=json.dumps({
                        "pipeline_version": PIPELINE_VERSION,
                        "provider": provider_name,
                        "model": model,
                        "evidence": evidence,
                    }, ensure_ascii=False),
                    genre_slug=args.genre,
                    genre_label=TEMPLATES[args.genre]["label"],
                    material_type="knowledge",
                    category_key=item.category_key,
                    category_label=category_label,
                    subcategory_key=item.subcategory_key,
                    subcategory_label=subcategory_label,
                    title=item.title,
                    concise_example=item.creative_material,
                    core_pattern=item.reusable_pattern,
                    mechanism=item.mechanism,
                    suspense_question=item.suspense_question,
                    applicable_stage=item.applicable_stage,
                    applicable_scene="创作构思",
                    emotion=TEMPLATES[args.genre]["label"],
                    tags_json=json.dumps(item.tags, ensure_ascii=False),
                    quality_score=quality_score,
                    score_json=json.dumps(score_values, ensure_ascii=False),
                    confidence=min(score_values.values()) / 5,
                    is_primary_variant=1,
                    created_at=now,
                ))
                inserted += 1
        batch_row.imported_count = inserted
        db.commit()

    print(json.dumps({
        "provider": provider_name,
        "model": model,
        "selected_sources": len(records),
        "completed_sources": len(outputs),
        "materials": inserted,
        "failures": failures,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
