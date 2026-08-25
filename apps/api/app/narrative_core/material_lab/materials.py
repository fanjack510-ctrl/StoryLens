"""Stage 2: EVIDENCE-BOUND KNOWLEDGE CLASSIFICATION.

Atoms + GenreTemplate -> Material rows carrying an abstracted ``core_pattern``
and one directly verifiable evidence sentence. The abstract pattern is used for
deduplication; the user-facing summary is never filled with a fabricated template.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .atoms import Atom
from .genre_templates import template_for
from .lexicon import (CLASS_MEASURE, MASS_OBJECTS, TRACE_CLASSES, measure_word,
                      object_class)

# ------------------------------------------------------------------ helpers
STRATEGY_TYPE = {
    "object_anomaly": "线索",
    "behavior": "行为",
    "person_doubt": "人物",
    "env_anomaly": "场景",
    "time_memory": "线索",
    "event": "事件",
    "state": "设定",
    "relation": "关系",
    "hook": "钩子",
    "structure": "结构",
}

OWNERSHIP_CUES = ["不属于", "不是他的", "不是她的", "陌生", "别人的", "另一个人的", "谁的"]
PLACEMENT_CUES = ["出现在", "放在", "留在", "落在", "藏在", "塞在", "压在", "夹在"]

# Max drafts per template category, per scene.
MAX_PER_CATEGORY = 3


@dataclass
class Draft:
    material_type: str
    category_key: str
    subcategory_key: str
    title: str
    concise_example: str
    core_pattern: str
    mechanism: str
    suspense_question: str
    applicable_stage: str
    applicable_scene: str
    emotion: str
    tags: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)


def _pick(atoms: list[Atom], t: str) -> list[Atom]:
    return [a for a in atoms if a.atom_type == t]


def _first(atoms: list[Atom], t: str, default=None):
    xs = _pick(atoms, t)
    return xs[0] if xs else default


def _hits(text: str, cues: list[str]) -> list[str]:
    # 单字词在长篇正文里几乎必然误报：例如科幻“制度”曾用“法”，于是
    # “无法”也被识别成法规；玄幻的“级”同样会命中普通的“高级”。
    return [c for c in cues if c and len(c.strip()) >= 2 and c in text]


def _knowledge_sentence(
    text: str,
    *,
    anchors: list[str],
    prefer_last: bool = False,
) -> str:
    """从命中位置附近选真实证据句，不再用分类槽位拼模板句。

    这里只做抽取，不生成新的文学判断。找不到足够完整的证据句就返回空串，
    调用方会放弃该候选。人物名保留在本地证据句中，避免不可靠的词法姓名
    识别把普通短语替换成“相关人物”并破坏句意。
    """
    raw_sentences = re.split(r"(?<=[。！？!?])|[\r\n]+", text.replace("　", " "))
    sentences = [re.sub(r"\s+", " ", item).strip() for item in raw_sentences]
    sentences = [item for item in sentences if 12 <= len(item) <= 180]
    if not sentences:
        return ""

    anchored = [
        item for item in sentences
        if anchors and any(anchor in item for anchor in anchors if anchor)
    ]
    candidates = anchored or (list(reversed(sentences)) if prefer_last else [])
    if not candidates:
        return ""
    sentence = max(
        candidates,
        key=lambda item: (
            sum(1 for anchor in anchors if anchor and anchor in item),
            -abs(len(item) - 64),
        ),
    )

    sentence = sentence.strip(" \t\r\n\"'“”‘’")
    return sentence if len(sentence) <= 180 else sentence[:178].rstrip() + "……"


def _stage_allows(category_stage: str, actual_stage: str) -> bool:
    """限制只在有意义的全书阶段提取该分类。

    “全书/主线/章末”不额外限制；章末仍由 ``is_chapter_end`` 单独控制。
    其余标签是模板声明的知识位置，不允许把第 500 章的普通设定误当开篇。
    """
    if category_stage in {"", "全书", "主线", "章末"}:
        return True
    allowed = {
        "开篇": {"开篇"},
        "前中段": {"开篇", "前中段"},
        "中段": {"前中段", "中段"},
        "中后段": {"中段", "后段"},
        "后段": {"后段", "结局"},
        "结局": {"结局"},
    }
    return actual_stage in allowed.get(category_stage, {actual_stage})


# ------------------------------------------------------ core pattern engine
# Classes that name a place, not something a character can carry. "人物持有
# 不属于自己的居所空间" is nonsense, so these get their own phrasing.
NON_PORTABLE_CLASSES = {"居所空间"}


def abstract_object_pattern(obj: str, place: str, has_owner_conflict: bool) -> tuple[str, str]:
    cls = object_class(obj)
    if cls in NON_PORTABLE_CLASSES:
        if has_owner_conflict:
            return ("某处空间的实际归属与登记不一致", "归属矛盾 + 隐藏用途")
        return ("某处空间的用途与它的外观对不上", "用途矛盾 + 延迟解释")
    if has_owner_conflict:
        return (f"人物持有不属于自己的{cls}",
                "所有权矛盾 + 隐藏关系")
    if place:
        return (f"{cls}出现在它不该出现的位置",
                "位置矛盾 + 使用痕迹")
    return (f"一{CLASS_MEASURE.get(cls, '件')}{cls}被反复提及却没有被解释",
            "信息缺口 + 延迟解释")


def abstract_behavior_pattern(cue: str) -> tuple[str, str]:
    table = {
        "撒谎": ("人物在无需说谎的场合说了谎", "动机不明 + 保护对象"),
        "说谎": ("人物在无需说谎的场合说了谎", "动机不明 + 保护对象"),
        "回避": ("人物刻意回避一个本可以正常回答的问题", "回避范围即秘密范围"),
        "口供": ("多份陈述在同一个细节上互相冲突", "证词矛盾 + 至少一人有隐情"),
        "反常": ("人物对本该震惊的事表现得过于平静", "情绪反应与情境不匹配"),
    }
    for k, v in table.items():
        if k in cue:
            return v
    return ("人物的行为与其声称的立场不一致", "言行矛盾 + 隐藏动机")


def abstract_person_pattern(sub: str) -> tuple[str, str]:
    table = {
        "identity_odd": ("一个人的身份材料在两处记录中对不上", "档案矛盾 + 身份替换"),
        "relation_mismatch": ("被公开承认的关系与实际关系不一致", "关系错位 + 长期隐瞒"),
        "blank_history": ("人物的经历中有一段无法查证的空白", "信息真空 + 可填充空间"),
        "familiarity": ("陌生人对主角表现出不该有的熟悉", "认知不对等 + 前史存在"),
        "info_conflict": ("同一个人在不同来源里有两套事实", "来源冲突 + 至少一份是假的"),
        "disappearance": ("一个人的消失没有留下任何过程记录", "过程缺失 + 有人清理"),
        "hidden_truth": ("已经成立的结论被人重新排列过顺序", "结论被改写 + 原始版本尚存"),
        "swap": ("两个人的身份在很早以前就被交换过", "早期替换 + 长期无人察觉"),
        "hidden_origin": ("人物的出身被家族有意识地改写", "出身改写 + 利益动因"),
    }
    v = table.get(sub)
    if v:
        return v
    return ("人物的公开身份与真实来历存在落差", "身份落差 + 揭示时机")


def abstract_env_pattern(sub: str, place: str) -> tuple[str, str]:
    """A corePattern must stay abstract.

    The concrete place is deliberately NOT interpolated here: putting a source
    place name into the pattern would leak source material into the derived
    layer and would also fragment one pattern into hundreds of near-copies.
    The concrete place still reaches the user through `applicableScene` and the
    composed example.
    """
    del place  # intentionally unused - see docstring
    table = {
        "space": ("场所的实际结构比记录中多出一部分", "空间冗余 + 被隐藏用途"),
        "routine": ("场所的日常秩序中有唯一一处例外", "例外即指向"),
        "physical_trace": ("现场留下的痕迹与声称的经过对不上", "痕迹矛盾 + 现场被整理"),
        "closed_place": ("场所从内部封闭，却仍然发生了变化", "封闭矛盾 + 未知通路"),
        "repeating": ("同一种异常在同一场所按固定周期重复", "周期性 + 人为维持"),
    }
    return table.get(sub, ("现场出现了无法用常理解释的细节", "环境异常 + 悬置解释"))


def abstract_time_pattern(sub: str) -> tuple[str, str]:
    table = {
        "time_shift": ("一份记录的时间早于它可能存在的时间", "时间悖论 + 伪造或误记"),
        "memory_gap": ("人物对一段时期完全没有记忆，其他人却记得", "记忆缺口 + 他人版本"),
        "repetition": ("同一件事在不同时间以相同方式重演", "重复结构 + 幕后重演者"),
        "posthumous": ("某人在被确认死亡之后仍产生了新的记录", "死后活动 + 身份被使用"),
        "impossible_time": ("同一个人被证明同时出现在两个地方", "不可能同时 + 替身或误证"),
    }
    return table.get(sub, ("事件的时间线存在无法调和的缺口", "时间矛盾 + 未知补足"))


# Restating the category as "X·Y构型" is not an abstraction - it just renames
# the bucket. Each non-suspense strategy gets a real structural statement, with
# the subcategory label as the only concrete slot.
_GENERIC_BY_STRATEGY = {
    "state": ("{sub}被确立为人物的起点条件，它限制了之后可以发生的事",
              "初始条件 + 行动边界"),
    "structure": ("{sub}被反复回收，成为贯穿长线的锚点",
                  "长线锚点 + 延迟兑现"),
    "event": ("{sub}打断了当前节奏，把人物推进一个新的处境",
              "节奏打断 + 处境迁移"),
    "relation": ("两方的关系被重新定义为{sub}，双方都没有说破",
                 "关系错位 + 未言明的默契"),
    "hook": ("本段停在{sub}刚刚成立的瞬间，解释被推到下一段",
             "悬置解释 + 跨段驱动"),
}
_GENERIC_FALLBACK = ("{sub}发生了一次不可逆的变化，人物的可选项随之收窄",
                     "不可逆变化 + 选项收窄")


def abstract_generic(label: str, sub_label: str, genre_label: str,
                     strategy: str = "") -> tuple[str, str]:
    pat, mech = _GENERIC_BY_STRATEGY.get(strategy, _GENERIC_FALLBACK)
    return (pat.format(sub=sub_label or label), mech)


def suspense_questions(strategy: str, obj: str, sub_label: str) -> str:
    if strategy == "object_anomaly" and obj:
        return f"这{measure_word(obj)}{obj}属于谁？它为什么在这里？它还能指向什么？"
    if strategy == "behavior":
        return "他在保护谁？说谎的代价是什么？真话会牵出什么？"
    if strategy == "person_doubt":
        return "哪一份记录是真的？落差期间他在哪里？谁替他做的登记？"
    if strategy == "env_anomaly":
        return "这处例外是谁留下的？它维持了多久？谁在维持它？"
    if strategy == "time_memory":
        return "两条时间线哪一条被改过？改动者想遮住哪一段？"
    tail = {
        "state": "这个起点条件会在什么时候反过来变成障碍？",
        "structure": "这条线会在哪一段被回收？谁先想起它？",
        "event": "这次变动谁受损？谁一直在等它发生？",
        "relation": "两个人里谁会先说破？说破的代价是什么？",
        "hook": "被压住的那一句，下一段由谁先说出来？",
    }.get(strategy)
    if tail:
        return tail
    return f"{sub_label or '这处变化'}接下来会往哪个方向推进？"


# --------------------------------------------------------------- generation
def generate_drafts(genre_slug: str, atoms: list[Atom], scene_text: str,
                    *, place: str, time_cue: str, is_chapter_end: bool,
                    stage_hint: str) -> list[Draft]:
    tpl = template_for(genre_slug)
    if not tpl:
        return []
    genre_label = tpl["label"]
    # Mass nouns (真气/灵气/…) are real atoms but cannot be "found" as one item.
    objs = [o for o in _pick(atoms, "OBJECT") if o.value not in MASS_OBJECTS]
    chars = _pick(atoms, "CHARACTER")
    emo_atom = _first(atoms, "EMOTION")
    emotion = emo_atom.value if emo_atom else ""
    drafts: list[Draft] = []
    for cat in tpl["categories"]:
        strategy = cat["strategy"]
        if not _stage_allows(cat.get("stage", ""), stage_hint):
            continue
        if strategy == "hook" and not is_chapter_end:
            continue
        # Per-category budget so late categories in the template are never
        # starved by a global cap (e.g. 时间记忆 sits at the end of 悬疑).
        cat_made = 0
        for sub in cat["subcategories"]:
            cues = sub["cues"]
            hit = _hits(scene_text, cues) if cues else []
            if cues and not hit:
                continue
            if strategy == "hook":
                pass  # hook has no cue list; allowed at chapter end

            obj = ""
            if strategy == "object_anomaly":
                cand = [o for o in objs
                        if any(c in o.value or o.value in c for c in cues)] or objs
                if not cand:
                    continue
                obj = cand[0].value

            owner_conflict = bool(_hits(scene_text, OWNERSHIP_CUES))
            placed = bool(_hits(scene_text, PLACEMENT_CUES))

            if strategy == "object_anomaly":
                cp, mech = abstract_object_pattern(obj, place if placed else "", owner_conflict)
            elif strategy == "behavior":
                cp, mech = abstract_behavior_pattern(hit[0] if hit else sub["label"])
            elif strategy == "person_doubt":
                cp, mech = abstract_person_pattern(sub["key"])
            elif strategy == "env_anomaly":
                cp, mech = abstract_env_pattern(sub["key"], place)
            elif strategy == "time_memory":
                cp, mech = abstract_time_pattern(sub["key"])
            else:
                cp, mech = abstract_generic(cat["label"], sub["label"],
                                            genre_label, strategy)

            example = _knowledge_sentence(
                scene_text,
                anchors=hit + ([obj] if obj else []),
                prefer_last=(strategy == "hook"),
            )
            if not example:
                continue
            title = _make_title(
                strategy, obj, sub["label"], cat["label"],
                owner_conflict=owner_conflict, placed=placed,
            )
            tags = _make_tags(genre_label, cat["label"], sub["label"], obj, emotion, place)
            drafts.append(Draft(
                material_type=STRATEGY_TYPE.get(strategy, "资料"),
                category_key=cat["key"],
                subcategory_key=sub["key"],
                title=title,
                concise_example=example,
                core_pattern=cp,
                mechanism=mech,
                suspense_question=suspense_questions(strategy, obj, sub["label"]),
                applicable_stage=stage_hint or cat.get("stage", ""),
                applicable_scene=place or "通用场景",
                emotion=emotion,
                tags=tags,
                signals={
                    "cue_hits": len(hit),
                    "objects": len(objs),
                    "characters": len(chars),
                    "owner_conflict": owner_conflict,
                    "strategy": strategy,
                    "scene_len": len(scene_text),
                    "summary_source": "matched_evidence_sentence",
                },
            ))
            cat_made += 1
            if cat_made >= MAX_PER_CATEGORY:
                break
    return drafts


def _make_title(
    strategy: str,
    obj: str,
    sub_label: str,
    cat_label: str,
    *,
    owner_conflict: bool = False,
    placed: bool = False,
) -> str:
    if strategy == "object_anomaly" and obj:
        # owner/placement cues are detected at scene scope while the displayed
        # evidence is one sentence.  Claiming “归属异常/位置异常” in the title
        # can therefore outrun the visible sentence.  The taxonomy already
        # carries the intended knowledge class; keep the title evidence-safe.
        return f"{cat_label}·{sub_label}"
    if strategy == "hook":
        return f"{cat_label}·停在解释之前"
    return f"{cat_label}·{sub_label}"


def _make_tags(genre_label, cat_label, sub_label, obj, emotion, place) -> list[str]:
    tags = [genre_label, cat_label, sub_label]
    if obj:
        tags += [obj, object_class(obj)]
    if emotion:
        tags.append(emotion)
    if place:
        tags.append(place)
    out, seen = [], set()
    for t in tags:
        t = (t or "").strip()
        if t and t not in seen and len(t) <= 12:
            seen.add(t)
            out.append(t)
    return out[:8]
