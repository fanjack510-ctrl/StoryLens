"""Chapter and scene segmentation for Chinese web-novel text."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .lexicon import (AD_LINE_RE, PLACE_SUFFIX, PLACE_SUFFIX_GENERIC,
                      PLACE_WORDS, TIME_RE)

CN_NUM = "零一二三四五六七八九十百千两０-９"

# Anchored: "第N章/节/回", "楔子", "序章", "尾声", optionally prefixed by "12."
PAT_ANCHORED = re.compile(
    rf"^[ \t　]*(?:[0-9]{{1,5}}[、.．,]\s*)?"
    rf"((?:第\s*[{CN_NUM}0-9]{{1,8}}\s*[章节回節卷部篇])"
    rf"|(?:楔\s*子)|(?:序\s*[章曲言])|(?:尾\s*声)|(?:正文\s*[^\n]{{0,20}}))"
    rf"[^\n]{{0,60}}$",
    re.M,
)
# Loose: same marker anywhere on the line (aggregator files inline them).
PAT_LOOSE = re.compile(rf"第\s*[{CN_NUM}0-9]{{1,8}}\s*[章节回][^\n]{{0,40}}")
# Numeric-only: "001，xxx" / "12. xxx"
PAT_NUMERIC = re.compile(r"^[ \t　]*([0-9]{1,5}[、.．，,]\s*\S{1,40})[ \t]*$", re.M)

SCENE_BREAK = re.compile(
    r"(?:^[ \t　]*(?:[-—*※·=＝#]{3,}|\*\s*\*\s*\*|※\s*※|＊{2,})[ \t]*$)"
    r"|(?:^[ \t　]*(?:※※※※+|——+)[ \t]*$)",
    re.M,
)


@dataclass
class Chapter:
    seq: int
    title: str
    start: int
    end: int


@dataclass
class Scene:
    seq: int
    start: int
    end: int
    summary: str
    place: str
    time_cue: str


def strip_noise(text: str) -> str:
    """Remove aggregator ad lines while preserving character offsets is not
    possible; instead we return a cleaned copy used only for statistics."""
    out = []
    for line in text.splitlines():
        if AD_LINE_RE.search(line) and len(line) < 200:
            continue
        out.append(line)
    return "\n".join(out)


def find_body_start(text: str) -> int:
    m = re.search(r"-{3,}\s*章节内容开始\s*-{3,}", text)
    if m:
        return m.end()
    m = re.search(r"『内容简介[\s\S]{0,4000}?』", text)
    if m:
        return m.end()
    return 0


def split_chapters(text: str) -> list[Chapter]:
    body0 = find_body_start(text)
    best: list[tuple[int, str]] = []
    for pat in (PAT_ANCHORED, PAT_LOOSE, PAT_NUMERIC):
        hits = [
            (m.start(), text[m.start(): m.end()].strip())
            for m in pat.finditer(text)
            if m.start() >= body0 - 200
        ]
        if len(hits) > len(best):
            best = hits
    if len(best) < 2:
        # single-chunk book: slice into ~12k windows so downstream still works
        n = max(len(text) - body0, 1)
        size = 12000
        cnt = max(1, min(400, (n + size - 1) // size))
        step = n // cnt
        return [
            Chapter(i + 1, f"片段{i + 1}", body0 + i * step,
                    body0 + (i + 1) * step if i < cnt - 1 else len(text))
            for i in range(cnt)
        ]
    best.sort(key=lambda x: x[0])
    # drop duplicate adjacent offsets
    dedup: list[tuple[int, str]] = []
    for pos, title in best:
        if dedup and pos - dedup[-1][0] < 60:
            continue
        dedup.append((pos, title))
    chapters: list[Chapter] = []
    for i, (pos, title) in enumerate(dedup):
        end = dedup[i + 1][0] if i + 1 < len(dedup) else len(text)
        title = re.sub(r"\s+", " ", title)[:80] or f"第{i + 1}章"
        chapters.append(Chapter(i + 1, title, pos, end))
    return _subdivide_oversized(chapters, text)


# Some files only mark 部 / 卷 and use an unrecognised convention for the real
# chapters, so a 300k-char book comes back as three chapters. Scene splitting
# caps at max_scenes per chapter, so that would silently analyse a fraction of
# the book. Anything far above a plausible chapter length gets windowed.
MAX_CHAPTER_CHARS = 20000
SUBDIVIDE_TARGET = 8000


def _subdivide_oversized(chapters: list[Chapter], text: str) -> list[Chapter]:
    if not any(c.end - c.start > MAX_CHAPTER_CHARS for c in chapters):
        return chapters
    out: list[Chapter] = []
    for ch in chapters:
        span = ch.end - ch.start
        if span <= MAX_CHAPTER_CHARS:
            out.append(Chapter(len(out) + 1, ch.title, ch.start, ch.end))
            continue
        cur, part = ch.start, 1
        while cur < ch.end:
            nxt = min(cur + SUBDIVIDE_TARGET, ch.end)
            if nxt < ch.end:
                cut = text.find("\n", nxt)
                if cut != -1 and cut < ch.end and cut - nxt < SUBDIVIDE_TARGET:
                    nxt = cut + 1
            out.append(Chapter(len(out) + 1, f"{ch.title} 片段{part}", cur, nxt))
            cur, part = nxt, part + 1
    return out


def detect_duplicate_chapters(chapters: list[Chapter], text: str) -> dict[int, int]:
    """Map seq -> seq of an earlier identical chapter (by normalized body hash)."""
    seen: dict[str, int] = {}
    dup: dict[int, int] = {}
    for ch in chapters:
        raw = text[ch.start: ch.end]
        nl = raw.find("\n")
        raw = raw[nl + 1:] if nl != -1 else raw       # drop the heading line
        body = re.sub(r"\s+", "", raw)[:4000]
        if len(body) < 120:
            continue
        if body in seen:
            dup[ch.seq] = seen[body]
        else:
            seen[body] = ch.seq
    return dup


# A place name has to start at a real boundary, otherwise a verb gets glued on
# and we end up with junk like "起身走进卧室" or "烟头弹进了路".
_PLACE_LEAD = "在到进去回于往至从由，。！？；：、“”‘’（）\n\r\t 　"
_PLACE_BAD_CHARS = set(
    "的了着过是不很就都也又才还再"                    # particles / adverbs
    "走进出起身拿看说想买卖租住来去回要能会可给让把被"  # verbs
    "自己你我他她它们咱谁大家"                        # pronouns
    "有座个位条只张些多少最更这那每整半另同"          # quantifiers / determiners
    "一二三三四五六七八九十百千万两几"                # numerals
    "如若因为所以但而且并却虽然"                      # conjunctions
    "套份间处块台辆双顶副根串摊层部本封枚幅段笔包袋桶道扇"  # measure words
)


def _place_of(chunk: str) -> str:
    """Scene place label.

    Exact place words win; only then do we fall back to suffix extraction,
    anchoring on the suffix and walking left until punctuation, a non-CJK char
    or a verb/particle - otherwise "他回到桃源村" comes back whole and
    "推开车门" turns into a bogus location.
    """
    head = chunk[:600]
    best_word, best_at = "", len(head) + 1
    for w in PLACE_WORDS:
        i = head.find(w)
        if i != -1 and (i < best_at or (i == best_at and len(w) > len(best_word))):
            best_word, best_at = w, i
    if best_word:
        return best_word
    for suf in sorted(PLACE_SUFFIX, key=len, reverse=True):
        start = 0
        while True:
            i = head.find(suf, start)
            if i == -1:
                break
            start = i + 1
            end = i + len(suf)
            j = i
            while j > 0:
                ch = head[j - 1]
                if not ("一" <= ch <= "鿿"):
                    break
                if ch in _PLACE_LEAD or ch in _PLACE_BAD_CHARS:
                    break
                j -= 1
                if end - j >= 6:
                    break
            name = head[j:end]
            if len(name) > len(suf) and 2 <= len(name) <= 6:
                # `name` is the source world's proper noun (星罗城, 煌明剑宗).
                # The derived layer must not carry it, so only the kind of place
                # survives.
                return PLACE_SUFFIX_GENERIC.get(suf, suf)
    return ""


def _summary_of(chunk: str) -> str:
    clean = strip_noise(chunk)
    sents = re.split(r"(?<=[。！？!?])", clean.replace("　", ""))
    picked: list[str] = []
    for s in sents:
        s = s.strip()
        if 8 <= len(s) <= 70:
            picked.append(s)
        if len(picked) >= 2:
            break
    return ("".join(picked))[:120]


def split_scenes(text: str, ch: Chapter, target: int = 1400,
                 max_scenes: int = 8) -> list[Scene]:
    body = text[ch.start: ch.end]
    if not body.strip():
        return []
    marks = [0] + [m.end() for m in SCENE_BREAK.finditer(body)] + [len(body)]
    marks = sorted(set(marks))
    blocks: list[tuple[int, int]] = []
    for i in range(len(marks) - 1):
        a, b = marks[i], marks[i + 1]
        if b - a < 80:
            continue
        blocks.append((a, b))
    if not blocks:
        blocks = [(0, len(body))]
    # further split long blocks on paragraph boundaries near `target`
    final: list[tuple[int, int]] = []
    for a, b in blocks:
        if b - a <= target * 1.7:
            final.append((a, b))
            continue
        cur = a
        while b - cur > target * 1.7:
            cut = body.find("\n", cur + target)
            if cut == -1 or cut >= b:
                cut = cur + target
            final.append((cur, cut))
            cur = cut
        if b - cur > 60:
            final.append((cur, b))
    final = final[:max_scenes]
    scenes: list[Scene] = []
    for i, (a, b) in enumerate(final):
        chunk = body[a:b]
        tm = TIME_RE.search(chunk[:600])
        scenes.append(
            Scene(
                seq=i + 1,
                start=ch.start + a,
                end=ch.start + b,
                summary=_summary_of(chunk),
                place=_place_of(chunk),
                time_cue=tm.group() if tm else "",
            )
        )
    return scenes
