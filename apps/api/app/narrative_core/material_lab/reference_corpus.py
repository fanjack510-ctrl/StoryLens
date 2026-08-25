"""Fast, deterministic screening for a large local reference corpus.

The corpus is deliberately screened before it can feed the knowledge library:
only TXT files that look like complete fiction and have a confident mapping to
one of the product's fixed genre templates become extraction candidates.  The
scanner reads small byte windows instead of loading every multi-megabyte novel.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from .genre_templates import TEMPLATES
from .lexicon import GENRE_SIGNALS


SAMPLE_HEAD_BYTES = 192 * 1024
SAMPLE_MIDDLE_BYTES = 96 * 1024
SAMPLE_TAIL_BYTES = 96 * 1024
MIN_NOVEL_BYTES = 40 * 1024

_CHAPTER_RE = re.compile(
    r"(?m)^\s*(?:第\s*[0-9０-９零〇一二三四五六七八九十百千万两]+\s*[章回节]"
    r"|(?:chapter|CHAPTER)\s*\d{1,4})[^\r\n]{0,80}\r?$"
)
_FICTION_CUES = (
    "说道", "问道", "笑道", "心想", "抬头", "回头", "看着", "走进", "转身",
    "房间", "院子", "门口", "眼神", "脸色", "忽然", "突然", "没想到",
)
_NON_FICTION_TITLE_CUES = (
    "营销", "礼仪", "管理学", "经济学", "研究", "报告", "教程", "指南", "手册",
    "制度", "文档", "工作记录", "使用说明", "参考资料", "资料整理", "skill",
    "提示词", "README", "元数据", "目录清单", "史记", "文明起源",
)
_NON_FICTION_TEXT_CUES = (
    "本章学习目标", "课后练习", "参考文献", "关键词：", "编者按", "课程目标",
    "操作步骤", "用户指南", "版权所有", "本报告", "研究表明",
)
_TITLE_SIGNALS: dict[str, tuple[str, ...]] = {
    "xuanyi": ("悬疑", "推理", "侦探", "谜案", "凶案", "刑警", "法医", "杀人", "诡案", "盗墓"),
    "xuanhuan": ("玄幻", "异界", "斗神", "武神", "魔王", "神座", "神凰", "斗气", "召唤"),
    "xianxia": ("仙侠", "修真", "修仙", "成仙", "仙途", "仙尊", "问道", "剑仙", "大道"),
    "dushi": ("都市", "兵王", "校花", "大亨", "职场", "官场", "商战", "创业"),
    "xianyan": ("现言", "总裁", "追妻", "爱上", "婚", "恋", "老公", "老婆", "男友", "女友", "娇宠", "军官", "六零", "八零"),
    "guyan": ("古言", "王妃", "医妃", "嫡女", "庶女", "清穿", "宫斗", "宅斗", "冷宫"),
    "kehuan": ("科幻", "星际", "星舰", "机甲", "未来", "宇宙", "虫族", "银河", "基因"),
    "moshi": ("末世", "丧尸", "废土", "灾变", "幸存者"),
    "wuxianliu": ("无限流", "无限恐怖", "无限", "主神", "副本", "轮回空间"),
    "zhongtian": ("种田", "农家", "田园", "发家", "庄园", "村长", "小农"),
}
_UNSUPPORTED_SIGNALS: dict[str, dict[str, float]] = {
    "wuxia": {
        "江湖": 2.8, "武林": 3.2, "武功": 2.4, "大侠": 3.5, "侠客": 3.2,
        "镖局": 3.5, "掌法": 2.2, "剑法": 2.0, "内力": 1.8, "点穴": 3.0,
    },
    "history": {
        "朝廷": 2.3, "皇帝": 1.8, "大军": 1.5, "将军": 1.3, "兵马": 2.0,
        "起义": 2.8, "王朝": 2.4, "战役": 3.2, "疆土": 2.0, "史书": 2.5,
    },
    "game": {
        "玩家": 3.2, "游戏": 3.0, "网游": 4.5, "NPC": 4.0, "npc": 4.0,
        "服务器": 3.0, "登录": 1.8, "公会": 2.5, "掉落": 2.6, "职业技能": 2.5,
    },
    "fanfic": {
        "同人": 4.0, "原著": 2.0, "剧情人物": 2.0, "动漫": 2.2,
    },
}
_UNSUPPORTED_TITLE_SIGNALS: dict[str, tuple[str, ...]] = {
    "wuxia": ("武侠", "江湖", "大侠", "镖", "侠", "武林", "碧血", "飞刀"),
    "history": ("大明", "大唐", "大宋", "三国", "抗战", "帝国", "皇权", "慈禧"),
    "game": ("网游", "游戏", "玩家", "魔兽", "暗黑破坏神", "传奇之"),
    "fanfic": ("同人", "[综]", "（综", "[HP]", "[黑篮]", "[棋魂]"),
}


class ReferenceCorpusRecord(BaseModel):
    relative_path: str
    title: str
    byte_size: int = Field(ge=0)
    fingerprint: str
    encoding: str
    chapter_markers_sampled: int = Field(ge=0)
    fiction_score: float = Field(ge=0.0, le=1.0)
    genre_slug: str = ""
    genre_label: str = ""
    genre_confidence: float = Field(ge=0.0, le=1.0)
    genre_signal_score: float = Field(ge=0.0)
    decision: str
    reasons: list[str] = Field(default_factory=list)


class ReferenceCorpusScan(BaseModel):
    root: str
    total_txt: int = Field(ge=0)
    accepted: int = Field(ge=0)
    unsupported_or_uncertain: int = Field(ge=0)
    rejected: int = Field(ge=0)
    by_genre: dict[str, int]
    records: list[ReferenceCorpusRecord]


def _decode(data: bytes, preferred: str | None = None) -> tuple[str, str]:
    encodings = [preferred] if preferred else []
    encodings.extend(["utf-8-sig", "utf-8", "gb18030", "utf-16", "big5"])
    seen: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return data.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("gb18030", errors="replace"), "gb18030-replace"


def _sample_bytes(path: Path) -> tuple[bytes, bytes, bytes]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(SAMPLE_HEAD_BYTES)
        middle_start = max(0, size // 2 - SAMPLE_MIDDLE_BYTES // 2)
        handle.seek(middle_start)
        middle = handle.read(SAMPLE_MIDDLE_BYTES)
        handle.seek(max(0, size - SAMPLE_TAIL_BYTES))
        tail = handle.read(SAMPLE_TAIL_BYTES)
    return head, middle, tail


def _sample_text(path: Path) -> tuple[str, str, bytes]:
    head, middle, tail = _sample_bytes(path)
    head_text, encoding = _decode(head)
    mid_text, _ = _decode(middle, encoding.replace("-replace", ""))
    tail_text, _ = _decode(tail, encoding.replace("-replace", ""))
    return "\n".join((head_text, mid_text, tail_text)), encoding, head + middle + tail


def _genre_scores(title: str, sample: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for slug, signals in GENRE_SIGNALS.items():
        score = sum(sample.count(word) * weight for word, weight in signals.items())
        score += sum(18.0 for cue in _TITLE_SIGNALS.get(slug, ()) if cue in title)
        scores[slug] = round(score, 3)
    return scores


def has_explicit_genre_title(title: str, genre_slug: str) -> bool:
    return any(cue in title for cue in _TITLE_SIGNALS.get(genre_slug, ()))


def _unsupported_scores(title: str, sample: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for slug, signals in _UNSUPPORTED_SIGNALS.items():
        score = sum(sample.count(word) * weight for word, weight in signals.items())
        score += sum(
            26.0 for cue in _UNSUPPORTED_TITLE_SIGNALS.get(slug, ()) if cue in title
        )
        scores[slug] = round(score, 3)
    return scores


def classify_reference_file(path: Path, root: Path) -> ReferenceCorpusRecord:
    stat = path.stat()
    title = path.stem.strip()
    sample, encoding, sampled_bytes = _sample_text(path)
    relative = str(path.relative_to(root)).replace("\\", "/")
    chapter_markers = len(_CHAPTER_RE.findall(sample))
    reasons: list[str] = []

    fiction_points = 0.0
    if stat.st_size >= MIN_NOVEL_BYTES:
        fiction_points += 0.12
    else:
        reasons.append("文件短于40KB")
    fiction_points += min(0.42, chapter_markers * 0.035)
    cue_hits = sum(min(sample.count(cue), 30) for cue in _FICTION_CUES)
    fiction_points += min(0.28, cue_hits / 260)
    dialogue_count = sample.count("“") + sample.count("”") + sample.count("：\"")
    fiction_points += min(0.18, dialogue_count / 240)

    title_lower = title.lower()
    negative_title = [cue for cue in _NON_FICTION_TITLE_CUES if cue.lower() in title_lower]
    negative_text = [cue for cue in _NON_FICTION_TEXT_CUES if cue in sample]
    if negative_title:
        fiction_points -= min(0.55, 0.18 * len(negative_title))
        reasons.append("标题含非小说信号：" + "、".join(negative_title[:3]))
    if negative_text:
        fiction_points -= min(0.35, 0.12 * len(negative_text))
        reasons.append("正文含非小说信号：" + "、".join(negative_text[:3]))
    if any(part.lower() in {"skill", "scripts", "logs", "docs"} for part in path.parts):
        fiction_points -= 0.35
        reasons.append("位于开发资料目录")
    fiction_score = round(max(0.0, min(1.0, fiction_points)), 3)

    scores = _genre_scores(title, sample)
    title_matches = {
        slug: [cue for cue in cues if cue in title]
        for slug, cues in _TITLE_SIGNALS.items()
    }
    title_matches = {slug: cues for slug, cues in title_matches.items() if cues}
    # A clear title label is stronger than incidental high-frequency words in a
    # 384KB sample (e.g. 《最强农家媳》 contains enough “仙/道” to fool a flat
    # counter).  Ties stay content-driven because hybrid titles are ambiguous.
    if title_matches:
        # “无限……” is a conventional, explicit genre title pattern.  Without
        # this override, incidental words such as “宇宙” or “末日” in a large
        # sample can incorrectly push an infinite-flow novel into sci-fi or
        # apocalypse even though its title already declares the genre.
        if title.startswith("无限"):
            scores["wuxianliu"] += max(scores.values()) + 600.0
        top_title_count = max(len(cues) for cues in title_matches.values())
        top_title_genres = [
            slug for slug, cues in title_matches.items() if len(cues) == top_title_count
        ]
        if len(top_title_genres) == 1:
            scores[top_title_genres[0]] += max(scores.values()) + 300.0
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_slug, best_score = ordered[0]
    second_score = ordered[1][1]
    active_total = sum(value for value in scores.values() if value >= 10) or 1.0
    share = best_score / active_total
    margin = (best_score - second_score) / max(best_score, 1.0)
    genre_confidence = round(max(0.0, min(1.0, 0.55 * share + 0.45 * margin)), 3)

    unsupported_scores = _unsupported_scores(title, sample)
    unsupported_slug, unsupported_score = max(
        unsupported_scores.items(), key=lambda item: item[1]
    )
    supported_title_hit = any(cue in title for cue in _TITLE_SIGNALS.get(best_slug, ()))

    if fiction_score < 0.48:
        decision = "rejected"
        reasons.append("小说结构置信不足")
        genre_slug = ""
    elif chapter_markers < 4:
        decision = "unsupported_or_uncertain"
        reasons.append("抽样未发现足够稳定的章节结构")
        genre_slug = ""
    elif unsupported_score >= 65 and unsupported_score >= best_score * 0.72:
        decision = "unsupported_or_uncertain"
        reasons.append(f"更接近暂未固化的类型：{unsupported_slug}")
        genre_slug = ""
    elif (
        best_score < 80
        or (genre_confidence < 0.36 and not supported_title_hit)
        or genre_confidence < 0.28
    ):
        decision = "unsupported_or_uncertain"
        reasons.append("现有十类无法高置信归类")
        genre_slug = ""
    else:
        decision = "accepted"
        genre_slug = best_slug
        reasons.append("通过小说结构与类型双门槛")

    return ReferenceCorpusRecord(
        relative_path=relative,
        title=title,
        byte_size=stat.st_size,
        fingerprint=hashlib.sha256(sampled_bytes).hexdigest(),
        encoding=encoding,
        chapter_markers_sampled=chapter_markers,
        fiction_score=fiction_score,
        genre_slug=genre_slug,
        genre_label=TEMPLATES[genre_slug]["label"] if genre_slug else "",
        genre_confidence=genre_confidence if genre_slug else 0.0,
        genre_signal_score=best_score,
        decision=decision,
        reasons=reasons,
    )


def scan_reference_corpus(root: Path, files: Iterable[Path] | None = None) -> ReferenceCorpusScan:
    candidates = list(files) if files is not None else sorted(root.rglob("*.txt"))
    records = [classify_reference_file(path, root) for path in candidates]
    decisions = Counter(record.decision for record in records)
    by_genre = Counter(record.genre_slug for record in records if record.genre_slug)
    return ReferenceCorpusScan(
        root=str(root),
        total_txt=len(records),
        accepted=decisions["accepted"],
        unsupported_or_uncertain=decisions["unsupported_or_uncertain"],
        rejected=decisions["rejected"],
        by_genre=dict(sorted(by_genre.items())),
        records=records,
    )
