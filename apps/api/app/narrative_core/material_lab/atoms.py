"""Stage 1 of analysis: FACT EXTRACTION -> Story Atoms.

Nine atom types, produced by deterministic lexical analysis so the pipeline
works with no API key. An AI provider, when configured, refines the same
structure (see providers.py) rather than replacing it.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .lexicon import (ACTION_VERBS, ANOMALY_CUES, DECEPTION_CUES, EVENT_CUES,
                      INFO_CUES, INVESTIGATION_VERBS, OBJECT_WORDS, OBJ2CLASS,
                      RELATION_WORDS, STOPWORDS, TIME_RE, emotion_of)

ATOM_TYPES = ["CHARACTER", "RELATIONSHIP", "SCENE", "OBJECT", "EVENT",
              "ACTION", "TIME", "INFORMATION", "EMOTION"]

SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭林钟徐邱骆高夏蔡田樊胡凌霍虞万支"
    "柯昝管卢莫房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴"
)
NAME_RE = re.compile(rf"[{SURNAMES}][一-龥]{{1,2}}")
TITLE_RE = re.compile(
    r"(?:小|老|阿)[一-龥]|"
    r"[一-龥]{1,3}(?:先生|小姐|夫人|公子|少爷|大人|队长|所长|局长|"
    r"教授|医生|警官|师父|师兄|师姐|长老|宗主|掌门|王爷|娘娘|嬷嬷|婆子)"
)
QUOTE_RE = re.compile(r"[“\"']([^”\"'\n]{2,120})[”\"']")

# Role nouns act as character anchors when no personal name is present -
# very common in Chinese crime / web fiction narration.
ROLE_NOUNS = [
    "死者", "凶手", "嫌疑人", "刑警", "警察", "法医", "证人", "目击者", "家属",
    "邻居", "同事", "老板", "掌柜", "老人", "孩子", "女人", "男人", "村民",
    "队长", "所长", "医生", "护士", "记者", "管家", "丫鬟", "长老", "宗主",
    "队友", "幸存者", "少年", "少女", "书生", "将军", "皇帝", "夫人", "小姐",
]


@dataclass
class Atom:
    atom_type: str
    value: str
    norm_value: str
    salience: float = 0.0
    char_pos: int = 0
    meta: dict = field(default_factory=dict)


def _clean(t: str) -> str:
    return t.replace("　", "").replace("\r", "")


def extract_characters(text: str) -> list[Atom]:
    cnt: Counter[str] = Counter()
    pos: dict[str, int] = {}
    for m in NAME_RE.finditer(text):
        w = m.group()
        if w in STOPWORDS or len(w) < 2:
            continue
        cnt[w] += 1
        pos.setdefault(w, m.start())
    for m in TITLE_RE.finditer(text):
        w = m.group()
        if 2 <= len(w) <= 6:
            cnt[w] += 1
            pos.setdefault(w, m.start())
    for w in ROLE_NOUNS:
        n = text.count(w)
        if n:
            cnt[w] += n
            pos.setdefault(w, text.find(w))
    out = []
    for w, c in cnt.most_common(12):
        if c < 2:
            continue
        out.append(Atom("CHARACTER", w, w, salience=min(1.0, c / 12), char_pos=pos[w],
                        meta={"mentions": c}))
    return out


def extract_relationships(text: str, chars: list[Atom]) -> list[Atom]:
    out: list[Atom] = []
    seen = set()
    names = [c.value for c in chars]
    for rw in RELATION_WORDS:
        idx = text.find(rw)
        if idx < 0:
            continue
        window = text[max(0, idx - 30): idx + 30]
        who = next((n for n in names if n in window), "")
        key = f"{who}|{rw}"
        if key in seen:
            continue
        seen.add(key)
        out.append(Atom("RELATIONSHIP", f"{who}-{rw}" if who else rw, rw,
                        salience=0.5 if who else 0.3, char_pos=idx,
                        meta={"role": rw, "anchor": who}))
        if len(out) >= 8:
            break
    return out


def extract_objects(text: str) -> list[Atom]:
    out: list[Atom] = []
    seen = set()
    for w in OBJECT_WORDS:
        idx = text.find(w)
        if idx < 0 or w in seen:
            continue
        seen.add(w)
        cnt = text.count(w)
        out.append(Atom("OBJECT", w, OBJ2CLASS.get(w, "物件"),
                        salience=min(1.0, cnt / 5), char_pos=idx,
                        meta={"count": cnt, "class": OBJ2CLASS.get(w, "物件")}))
        if len(out) >= 14:
            break
    return out


def extract_events(text: str) -> list[Atom]:
    out: list[Atom] = []
    for w in EVENT_CUES:
        idx = text.find(w)
        if idx < 0:
            continue
        sent = _sentence_at(text, idx)
        if len(sent) < 8:
            continue
        out.append(Atom("EVENT", sent[:90], w, salience=0.6, char_pos=idx,
                        meta={"cue": w}))
        if len(out) >= 10:
            break
    return out


def extract_actions(text: str) -> list[Atom]:
    out: list[Atom] = []
    hits = 0
    for w in ACTION_VERBS + INVESTIGATION_VERBS:
        idx = text.find(w)
        if idx < 0:
            continue
        sent = _sentence_at(text, idx)
        if len(sent) < 8:
            continue
        out.append(Atom("ACTION", sent[:80], w, salience=0.4, char_pos=idx,
                        meta={"verb": w}))
        hits += 1
        if hits >= 10:
            break
    return out


def extract_time(text: str) -> list[Atom]:
    out: list[Atom] = []
    seen = set()
    for m in TIME_RE.finditer(text):
        w = m.group()
        if w in seen:
            continue
        seen.add(w)
        out.append(Atom("TIME", w, w, salience=0.4, char_pos=m.start()))
        if len(out) >= 8:
            break
    return out


def extract_information(text: str) -> list[Atom]:
    out: list[Atom] = []
    for w in INFO_CUES:
        idx = text.find(w)
        if idx < 0:
            continue
        sent = _sentence_at(text, idx)
        if len(sent) < 10:
            continue
        out.append(Atom("INFORMATION", sent[:100], w, salience=0.6,
                        char_pos=idx, meta={"cue": w}))
        if len(out) >= 8:
            break
    for m in list(QUOTE_RE.finditer(text))[:4]:
        out.append(Atom("INFORMATION", m.group(1)[:100], "对白", salience=0.5,
                        char_pos=m.start(), meta={"cue": "dialogue"}))
    return out


def extract_emotion(text: str) -> list[Atom]:
    emo, density = emotion_of(text)
    if not emo:
        return []
    return [Atom("EMOTION", emo, emo, salience=min(1.0, density / 8),
                 char_pos=0, meta={"density": density})]


def extract_scene_atom(text: str, place: str, time_cue: str) -> list[Atom]:
    label = place or (time_cue or "未标注场景")
    return [Atom("SCENE", label, label, salience=0.5, char_pos=0,
                 meta={"place": place, "time": time_cue})]


def _sentence_at(text: str, idx: int) -> str:
    left = max(text.rfind("。", 0, idx), text.rfind("\n", 0, idx),
               text.rfind("！", 0, idx), text.rfind("？", 0, idx))
    right_candidates = [text.find(p, idx) for p in "。！？\n"]
    right_candidates = [r for r in right_candidates if r != -1]
    right = min(right_candidates) if right_candidates else min(len(text), idx + 80)
    return _clean(text[left + 1: right + 1]).strip()


def anomaly_score(text: str) -> float:
    n = sum(text.count(c) for c in ANOMALY_CUES)
    return round(n / max(len(text), 1) * 1000, 3)


def deception_score(text: str) -> float:
    n = sum(text.count(c) for c in DECEPTION_CUES)
    return round(n / max(len(text), 1) * 1000, 3)


def extract_all(text: str, place: str = "", time_cue: str = "") -> list[Atom]:
    t = _clean(text)
    chars = extract_characters(t)
    atoms: list[Atom] = []
    atoms += chars
    atoms += extract_relationships(t, chars)
    atoms += extract_scene_atom(t, place, time_cue)
    atoms += extract_objects(t)
    atoms += extract_events(t)
    atoms += extract_actions(t)
    atoms += extract_time(t)
    atoms += extract_information(t)
    atoms += extract_emotion(t)
    return atoms
