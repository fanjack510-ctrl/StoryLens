"""StoryLens 章节/段落 -> 创作资料草稿。纯函数，不落库。

编排逻辑逐点对照 novel-material-lab 的 `pipeline.analyze_book`：
场景切分参数、strip_noise、<80 字跳过、stage_hint 分位、is_chapter_end、
重复章节跳过，全部保持一致——对数脚本靠这一点才能把两边的结果对上。
唯一的结构差异：源项目对全书原文跑 `split_chapters`，这里章节边界直接
取 StoryLens 导入产物（Chapter + Paragraph），场景切分从章节文本内部开始。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .atoms import Atom, extract_all
from .lexicon import GENRE_SIGNALS
from .materials import Draft, generate_drafts
from .textseg import Chapter as SegChapter
from .textseg import _subdivide_oversized, split_scenes, strip_noise

# 与源项目 config.DEFAULTS 一致
SCENE_TARGET_CHARS = 1400
MAX_SCENES_PER_CHAPTER = 8
MIN_SCENE_CHARS = 80


@dataclass
class SceneMaterials:
    chapter_seq: int
    chapter_title: str
    scene_seq: int
    char_start: int  # 章节内偏移
    char_end: int
    place: str
    time_cue: str
    summary: str
    atoms: list[Atom] = field(default_factory=list)
    drafts: list[Draft] = field(default_factory=list)


@dataclass
class BookMaterials:
    genre_slug: str
    genre_confidence: float
    chapter_count: int
    duplicate_chapters: int
    skipped_short_scenes: int
    scenes: list[SceneMaterials] = field(default_factory=list)

    @property
    def drafts(self) -> list[Draft]:
        return [d for sc in self.scenes for d in sc.drafts]


def chapter_text_from_paragraphs(paragraphs) -> str:
    """StoryLens Paragraph 序列 -> 章节正文。

    接受 ORM 对象或任何带 normalized_text/raw_text 的对象；段落间用换行连接，
    与导入前原文的段落边界一致（场景切分靠 \\n 找段落断点）。
    """
    parts = []
    for p in paragraphs:
        text = getattr(p, "normalized_text", None) or getattr(p, "raw_text", "")
        parts.append(text)
    return "\n".join(parts)


def guess_genre(text: str) -> tuple[str, float]:
    """与源项目 importer.guess_genre 逐行一致（该函数原挂在绑 db 的 importer 里，
    本体是纯函数，故在此重置）。"""
    sample = text[:120000] + text[len(text) // 2: len(text) // 2 + 60000]
    scores: dict[str, float] = {}
    for slug, sig in GENRE_SIGNALS.items():
        scores[slug] = sum(sample.count(w) * wt for w, wt in sig.items())
    if not scores:
        return "", 0.0
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values()) or 1
    return (best, round(scores[best] / total, 3)) if scores[best] > 30 else ("", 0.0)


def _stage_hint(chapter_seq: int, total_chapters: int) -> str:
    ratio = chapter_seq / max(total_chapters, 1)
    return ("开篇" if ratio <= 0.12 else "前中段" if ratio <= 0.4
            else "中段" if ratio <= 0.7 else "后段" if ratio <= 0.92 else "结局")


def _dup_body_key(text: str) -> str:
    """与 textseg.detect_duplicate_chapters 的归一化一致（去首行后压空白取前 4000）。
    这里的输入已不含标题行，所以只做压空白截断。"""
    return re.sub(r"\s+", "", text)[:4000]


def extract_chapter_materials(
    text: str,
    *,
    genre_slug: str,
    chapter_seq: int,
    total_chapters: int,
    title: str = "",
) -> tuple[list[SceneMaterials], int]:
    """单章文本 -> 各场景的资料草稿。返回 (场景列表, 因过短跳过的场景数)。"""
    # 源项目对 >20k 字的章节先窗口化再切场景（否则 8 场景上限会静默丢掉
    # 章节后半），这里复用同一个函数保持行为一致。
    seg_chapters = _subdivide_oversized(
        [SegChapter(seq=chapter_seq, title=title, start=0, end=len(text))], text)
    stage = _stage_hint(chapter_seq, total_chapters)
    out: list[SceneMaterials] = []
    skipped = 0
    for seg_ch in seg_chapters:
        scenes = split_scenes(text, seg_ch, target=SCENE_TARGET_CHARS,
                              max_scenes=MAX_SCENES_PER_CHAPTER)
        for i, sc in enumerate(scenes):
            chunk = text[sc.start: sc.end]
            clean = strip_noise(chunk)
            if len(clean) < MIN_SCENE_CHARS:
                skipped += 1
                continue
            atoms = extract_all(clean, sc.place or "", sc.time_cue or "")
            drafts = generate_drafts(
                genre_slug, atoms, clean,
                place=sc.place or "",
                time_cue=sc.time_cue or "",
                is_chapter_end=(i == len(scenes) - 1),
                stage_hint=stage,
            )
            out.append(SceneMaterials(
                chapter_seq=chapter_seq, chapter_title=title, scene_seq=sc.seq,
                char_start=sc.start, char_end=sc.end,
                place=sc.place, time_cue=sc.time_cue, summary=sc.summary,
                atoms=atoms, drafts=drafts,
            ))
    return out, skipped


def extract_book_materials(
    chapters: list[tuple[str, str]],
    genre_slug: str = "",
) -> BookMaterials:
    """整本书 -> 资料草稿。

    `chapters` 是 (标题, 正文) 序列，按章节顺序；正文可用
    `chapter_text_from_paragraphs` 从 StoryLens Paragraph 拼出。
    genre_slug 留空时按全文猜测（与源项目导入时的建议逻辑相同）。
    """
    full_text = "\n".join(t for _, t in chapters)
    confidence = 0.0
    if not genre_slug:
        genre_slug, confidence = guess_genre(full_text)

    seen_bodies: set[str] = set()
    total = len(chapters)
    scenes: list[SceneMaterials] = []
    dup_count = 0
    skipped_total = 0
    for seq0, (title, text) in enumerate(chapters):
        body_key = _dup_body_key(text)
        if len(body_key) >= 120:
            if body_key in seen_bodies:
                dup_count += 1
                continue
            seen_bodies.add(body_key)
        ch_scenes, skipped = extract_chapter_materials(
            text, genre_slug=genre_slug, chapter_seq=seq0 + 1,
            total_chapters=total, title=title,
        )
        scenes.extend(ch_scenes)
        skipped_total += skipped
    return BookMaterials(
        genre_slug=genre_slug, genre_confidence=confidence,
        chapter_count=total, duplicate_chapters=dup_count,
        skipped_short_scenes=skipped_total, scenes=scenes,
    )
