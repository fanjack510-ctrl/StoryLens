"""Quality scoring: ten sub-scores -> 0-100 composite."""
from __future__ import annotations

import json
import math

from .dedup import normalize
from .lexicon import OBJECT_WORDS

WEIGHTS = {
    "novelty": 0.14,
    "specificity": 0.16,
    "reusability": 0.14,
    "genre_fit": 0.10,
    "platform_fit": 0.06,
    "visuality": 0.10,
    "suspense": 0.10,
    "independence": 0.08,
    "source_confidence": 0.08,
    "similarity_penalty": -0.14,   # applied as penalty
}

GENERIC_WORDS = ["某种", "一些", "很多", "各种", "东西", "情况", "事情", "问题", "构型"]
CONCRETE_HINT = ["一件", "一张", "一把", "一份", "一处", "第", "两", "三", "四", "五",
                 "七", "十", "分钟", "小时", "天", "年", "米", "把", "枚", "条"]


def score_material(*, concise_example: str, core_pattern: str, mechanism: str,
                   suspense_question: str, tags: list[str], signals: dict,
                   cluster_size: int, book_count_for_pattern: int,
                   evidence_count: int, example_freq: int = 1,
                   book_example_freq: int = 1) -> tuple[int, dict]:
    ex = concise_example or ""
    cp = core_pattern or ""
    n_ex = len(normalize(ex))

    # specificity: concrete nouns/quantifiers, penalised for vague words
    concrete = sum(1 for w in CONCRETE_HINT if w in ex)
    objs = sum(1 for w in OBJECT_WORDS[:400] if w in ex)
    generic = sum(1 for w in GENERIC_WORDS if w in ex or w in cp)
    specificity = _clip(0.25 + 0.11 * concrete + 0.14 * objs - 0.18 * generic)

    # novelty: how rare this concrete entry is across the whole library.
    #
    # It deliberately does NOT use the pattern cluster. corePattern abstraction
    # is designed to collapse 钥匙/戒指/门禁卡 into one pattern, so essentially
    # every material sits in a large cluster - scoring novelty off cluster size
    # put 99% of the library on the floor and measured the abstraction working,
    # not the entry being weak. Entry text is the unit that actually varies.
    novelty = _clip(1.0 - _freq_weight(example_freq, 60.0))

    # reusability: abstraction that still names a mechanism
    reusability = _clip(
        0.35
        + (0.25 if mechanism else 0)
        + (0.2 if "+" in mechanism else 0)
        + (0.2 if 8 <= len(normalize(cp)) <= 40 else 0)
        - (0.25 if generic else 0)
    )

    genre_fit = _clip(0.4 + 0.15 * min(signals.get("cue_hits", 0), 4))
    platform_fit = _clip(0.5 + 0.1 * min(book_count_for_pattern, 5))

    visuality = _clip(
        0.2 + 0.16 * objs + (0.2 if signals.get("strategy") in
                             ("object_anomaly", "env_anomaly") else 0)
        + (0.15 if any(p in ex for p in "见看发现摆放留下") else 0)
    )
    suspense = _clip(
        0.25
        + (0.3 if suspense_question else 0)
        + (0.2 if signals.get("owner_conflict") else 0)
        + 0.08 * min(signals.get("cue_hits", 0), 3)
    )
    independence = _clip(
        0.35
        + (0.3 if 18 <= n_ex <= 70 else 0)
        + (0.2 if not any(k in ex for k in ("上文", "前面", "如前", "该书")) else 0)
    )
    source_confidence = _clip(0.3 + 0.2 * min(evidence_count, 3)
                              + (0.1 if signals.get("scene_len", 0) > 500 else 0))
    # redundancy that actually costs the operator something: the same sentence
    # repeating inside one book. The first occurrence is free.
    similarity_penalty = _clip(_freq_weight(book_example_freq, 20.0))

    parts = {
        "novelty": novelty, "specificity": specificity, "reusability": reusability,
        "genre_fit": genre_fit, "platform_fit": platform_fit,
        "visuality": visuality, "suspense": suspense,
        "independence": independence, "source_confidence": source_confidence,
        "similarity_penalty": similarity_penalty,
    }
    raw = sum(WEIGHTS[k] * v for k, v in parts.items())
    score = int(round(_clip(raw / 0.96) * 100))
    parts_out = {k: round(v, 3) for k, v in parts.items()}
    parts_out["composite"] = score
    return score, parts_out


def rescore_with_final_counts(conn) -> dict:
    """Level the two frequency-dependent sub-scores once analysis is over.

    During a run the counts are only "so far", so the first copy of a sentence
    looks novel and the hundredth looks worthless - the same text scores
    differently depending on when its book happened to be processed. Every other
    sub-score is order-independent and is reused verbatim from `score_json`, so
    one pass at the end makes the library self-consistent.
    """
    from . import db as D

    glob = {r["e"]: r["c"] for r in D.q(
        conn, "SELECT concise_example e, COUNT(*) c FROM materials GROUP BY e")}
    per_book = {(r["b"], r["e"]): r["c"] for r in D.q(
        conn, """SELECT book_id b, concise_example e, COUNT(*) c
                 FROM materials GROUP BY b, e""")}
    updated = 0
    for r in D.q(conn, """SELECT material_id, book_id, concise_example, score_json
                          FROM materials"""):
        try:
            parts = json.loads(r["score_json"] or "{}")
        except Exception:
            continue
        if not parts:
            continue
        ex = r["concise_example"]
        parts["novelty"] = round(
            _clip(1.0 - _freq_weight(glob.get(ex, 1), 60.0)), 3)
        parts["similarity_penalty"] = round(
            _clip(_freq_weight(per_book.get((r["book_id"], ex), 1), 20.0)), 3)
        raw = sum(WEIGHTS[k] * float(parts.get(k, 0.0)) for k in WEIGHTS)
        score = int(round(_clip(raw / 0.96) * 100))
        parts["composite"] = score
        D.ex(conn, "UPDATE materials SET quality_score=?, score_json=? WHERE material_id=?",
             (score, json.dumps(parts, ensure_ascii=False), r["material_id"]))
        updated += 1
    conn.commit()
    return {"rescored": updated, "distinct_examples": len(glob)}


def confidence_of(evidence_count: int, cluster_books: int, cue_hits: int) -> float:
    base = 0.25 + 0.15 * min(evidence_count, 3) + 0.1 * min(cluster_books, 4)
    base += 0.05 * min(cue_hits, 3)
    return round(min(base, 0.97), 3)


def _freq_weight(freq: int, cap: float) -> float:
    """0.0 for the first occurrence, rising to 1.0 at `cap` repeats."""
    n = max(1, min(int(freq or 1), int(cap)))
    return math.log(n) / math.log(cap)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def bucket(score: int, official: int, review: int) -> str:
    if score >= official:
        return "official"
    if score >= review:
        return "review"
    return "low"
