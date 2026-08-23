"""三级去重的纯函数半边（自 novel-material-lab dedup.py 原样截取）。

源文件的另一半（assign_pattern / refresh_pattern_stats / mark_primary_variants /
find_near_duplicate_examples）绑在源项目自己的 sqlite 连接上，按交接说明不搬，
由 service.py 用 SQLAlchemy 对 material_lab_patterns 重写。
本文件里的函数与源文件逐行一致——同义折叠表 SYNONYMS 是聚类行为的一部分，
改动它会让两边对同一本书聚出不同的模式簇。
"""
from __future__ import annotations

import hashlib
import re

_PUNCT = re.compile(r"[\s，。！？、；：“”‘’（）()\[\]{}·—…,.!?;:\"'|/\\-]+")

# Paraphrase folding: surface variants that mean the same thing in this domain
# collapse to one canonical token before shingling, so
# "死者身上出现陌生钥匙" and "尸体口袋里找到不属于他的钥匙" cluster together.
SYNONYMS: list[tuple[str, str]] = [
    ("尸体", "死者"), ("遗体", "死者"), ("被害人", "死者"), ("死人", "死者"),
    ("找到", "出现"), ("发现", "出现"), ("翻出", "出现"), ("搜出", "出现"),
    ("摸到", "出现"), ("看到", "出现"), ("捡到", "出现"),
    ("不属于他", "陌生"), ("不属于她", "陌生"), ("不属于自己", "陌生"),
    ("不是他的", "陌生"), ("不是她的", "陌生"), ("别人的", "陌生"),
    ("来路不明", "陌生"), ("没见过", "陌生"),
    ("口袋里", "身上"), ("兜里", "身上"), ("随身", "身上"), ("怀里", "身上"),
    ("门禁卡", "私人物件"), ("钥匙", "私人物件"), ("学生证", "私人物件"),
    ("工作证", "私人物件"), ("病历卡", "私人物件"), ("戒指", "私人物件"),
    ("持有", "拥有"), ("带着", "拥有"), ("拿着", "拥有"),
]


def fold_synonyms(s: str) -> str:
    for a, b in SYNONYMS:
        if a in s:
            s = s.replace(a, b)
    return s


def normalize(s: str) -> str:
    return _PUNCT.sub("", fold_synonyms(s or ""))


def signature(core_pattern: str) -> str:
    return hashlib.sha1(normalize(core_pattern).encode("utf-8")).hexdigest()[:16]


def shingles(s: str, k: int = 3) -> set[str]:
    n = normalize(s)
    if len(n) <= k:
        return {n} if n else set()
    return {n[i:i + k] for i in range(len(n) - k + 1)}


def jaccard(a: str, b: str, k: int = 3) -> float:
    sa, sb = shingles(a, k), shingles(b, k)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def cosine_like(a: str, b: str) -> float:
    """Containment-aware score: catches paraphrases of unequal length."""
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / min(len(sa), len(sb))


def similarity(a: str, b: str) -> float:
    return round(max(jaccard(a, b), 0.85 * cosine_like(a, b)), 4)
