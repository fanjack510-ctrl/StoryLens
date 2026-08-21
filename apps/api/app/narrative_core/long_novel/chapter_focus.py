"""Profile-driven focus for the single-chapter stack (10_ADAPTIVE_PROFILE_LAYER §4.4).

Before 1.2.0 the single-chapter pipeline never knew what book it was reading: a cultivation
ladder novel and a romance were scored with the same 21 reading-mechanics dimensions under
the same neutral instructions. The design doc names this and the whole-book engine's
"type decided after the last paid call" as two instances of one defect — analysis performed
without knowing what the object is.

This module is the chapter-side counterpart of ``deltas.py``, and §4 requires the two to
share one vocabulary: triggers are the same closed axis values from ``contracts/profile.py``,
resolved with the same rules. What differs is the payload. A whole-book delta may add
schema fields; a chapter focus adds **prompt emphasis only** — which of the already-present
dimensions carry this book, and what the scorer should look at when rating them. No field is
added or removed, no rule above the block is modified (INV-P1 by construction), and a book
without a confirmed profile gets a byte-identical prompt (INV-P2: a draft is not enough;
the hash that gates caching must not move for unconfirmed books).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from .contracts.profile import AXES
from .profile_repository import BookProfileRepository

__all__ = [
    "ChapterFocus",
    "GenreAxis",
    "MAX_GENRE_AXES",
    "anchors_for",
    "selected_axes",
    "required_axis_keys",
    "CHAPTER_FOCI",
    "chapter_foci_for",
    "chapter_foci_for_book",
    "chapter_focus_prompt",
    "chapter_focus_for_book",
    "apply_chapter_focus",
    "segmentation_focus_prompt",
    "segmentation_focus_for_book",
    "apply_segmentation_focus",
    "merged_weights",
    "formula_weights_for_book",
    "apply_formula_weights",
    "NO_FOCUS_BY_DESIGN",
    "LENGTH_EXPECTATION",
    "MAIN_CURVE_NAMING",
    "DEFAULT_MAIN_CURVE",
    "main_curve_naming",
    "main_curve_naming_for_book",
    "suppressed_diagnoses",
    "suppressed_diagnoses_for_book",
]


#: The weight blocks a focus may override, and the keys each one accepts. Anything outside
#: this table is a typo, and a typo in a weight table is silent — the term just never
#: contributes — so it is rejected at import time instead.
_WEIGHT_BLOCKS: dict[str, frozenset[str]] = {
    "reading_tension": frozenset({"curiosity", "tension", "emotional_investment"}),
    "reading_momentum": frozenset(
        {"plot_progress", "reading_tension", "pacing_fit", "hook_payoff_fit"}
    ),
    "plot_progress": frozenset(
        {
            "goal_progress",
            "conflict_change",
            "state_change",
            "information_gain",
            "character_agency",
            "causal_coherence",
        }
    ),
}

#: Legal values for ``ChapterFocus.suppressed_diagnoses``. A typo here is silent — the code
#: simply never matches and the diagnosis keeps firing — so it is rejected at import time,
#: same as a misspelled weight block.
_DIAGNOSIS_CODES: frozenset[str] = frozenset(
    {
        "plot_stagnation",
        "empty_fast_pacing",
        "weak_progress",
        "pacing_too_slow",
        "pacing_too_fast",
        "information_overload",
        "weak_curiosity",
        "weak_tension",
        "weak_emotional_investment",
        "suspended_tension",
        "tension_overload",
        "weak_hook",
        "empty_hook",
        "delayed_payoff",
        "abrupt_reveal",
        "effective_payoff",
        "unclear_expression",
        "scene_boundary_anomaly",
        "low_confidence",
    }
)


@dataclass(frozen=True)
class GenreAxis:
    """A scored axis that only exists for books of a certain type (CHG-20260815-100).

    ``anchors`` is the whole point. The 21 base dimensions ship without level anchors, and
    the production sample shows the consequence: on axes where the model has no concrete
    picture of what a 2 looks like, it answers 5 — ``clarity`` came back at 5 for 81% of 42
    real scenes and ``setup_consistency`` never dropped below 4. An axis without anchors is
    not a measurement. Every axis here states what 0, 3 and 5 are in that book's own terms.

    Higher is always better *for this type*: 憋屈控制 scores high when the frustration is
    short and paid, not when there is none, because a 爽文 with no setback has no 爽.
    """

    key: str
    label: str
    anchors: str
    #: Which scene this axis is asked about. Most axes are genuinely per-scene. Two are not:
    #: 开篇抓力 is a property of the chapter's opening and 断章质量 of its ending, and asking
    #: them of every scene produces exactly the noise the first real run showed — the middle
    #: scene of a chapter scored 断章质量=1 because it does not end the chapter, which says
    #: nothing about the writing. The scene payload carries is_chapter_opening /
    #: is_chapter_ending so the model can tell which scene it is holding.
    scope: str = "scene"

    def __post_init__(self) -> None:
        if self.scope not in {"scene", "opening", "ending"}:
            raise ValueError(f"genre axis {self.key}: unknown scope {self.scope}")


@dataclass(frozen=True)
class ChapterFocus:
    """One profile-driven emphasis for chapter-level analysis.

    ``triggers`` is a conjunction: every ``(axis, value)`` pair must hold. A single-pair
    tuple is the common case; the 爽点 focus needs two because §4 binds it to
    male_gratification **and** progression — a female-oriented ladder novel's beats are not
    read the same way.
    """

    key: str
    triggers: tuple[tuple[str, str], ...]
    instruction: str
    axes: tuple[GenreAxis, ...] = ()
    #: Extra rule for the *boundary* prompt, not the scoring prompt. v4.0's definition of a
    #: scene is event-driven — same time, same place, same people, one action chain — and on
    #: 《再也不见》第一章 that produced a technically correct answer that missed the chapter:
    #: 40 paragraphs of dorm banter and the protagonist's confession that he and 齐沫 broke up
    #: came out as ONE scene, because the room, the people and the night never changed. What
    #: changed was the relationship, which the event-driven definition cannot see.
    segmentation: str = ""
    #: Overrides merged into ``reader_journey_formulas_v2.json``'s ``weights`` block, so the
    #: main curve measures what this type's reader is actually deciding. The shipped config
    #: has carried ``"default_genre": "suspense"`` since v2.0 and nothing ever read it — one
    #: suspense-shaped weighting was applied to every book. Scored by it a romance reads as
    #: 「追读意愿 30」, which is not so much wrong as beside the point: a 订阅制 reader has
    #: already paid and is not deciding whether to swipe away.
    #:
    #: Only the blocks named here are replaced, and only key by key, so a book whose profile
    #: declares none is byte-identical to before (INV-P1).
    weights: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    #: Diagnosis codes that do not apply to this type.
    #:
    #: The deterministic diagnoser fires on absolute thresholds — ``tension < 35`` is
    #: ``weak_tension`` for every book there is. Measured on two real chapters, that layer
    #: reports exactly the same thing the hook vocabulary used to: 《我不是戏神》(悬疑) gets
    #: zero diagnoses across six scenes, 《再也不见》(言情) gets three — 「张力不足」 twice and
    #: 「好奇不足」 once. A paid-subscription romance whose opening is quiet is not defective;
    #: it is the form. Flagging it is the same category error as calling its chapter a
    #: failed mystery.
    #:
    #: Suppression is not blanket permission to be flabby: the axis that *does* carry the
    #: book stays armed (a romance still gets ``weak_emotional_investment``), and a book
    #: without a confirmed profile suppresses nothing (INV-P2).
    suppressed_diagnoses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for axis, value in self.triggers:
            enum = AXES.get(axis)
            if enum is None or value not in {item.value for item in enum}:
                raise ValueError(f"chapter focus {self.key}: unknown trigger {axis}={value}")
        for code in self.suppressed_diagnoses:
            if code not in _DIAGNOSIS_CODES:
                raise ValueError(
                    f"chapter focus {self.key}: unknown diagnosis code {code!r}"
                )
        for block, table in self.weights.items():
            if block not in _WEIGHT_BLOCKS:
                raise ValueError(f"chapter focus {self.key}: unknown weight block {block!r}")
            total = sum(float(v) for v in table.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"chapter focus {self.key}: {block} weights sum to {total}, not 1.0"
                )


_HEADER = (
    "## 类型侧重（来自本书已确认的画像）\n"
    "以下侧重只增加观察点，不修改、不放松上文的任何规则、字段或上限。"
)


FAST_FOOD_HOOKS = ChapterFocus(
    key="fast_food_hooks",
    triggers=(("monetization", "fast_food_free"),),
    instruction=(
        "- 本书走免费快餐流，读者随时可划走：特别注意**钩子出现的位置**（第几段才有第一个钩子）、"
        "**冲突首次出现的段号**、单章信息密度是否有大段空转，以及**断章位置的质量**"
        "（章末是悬念收口还是平铺收尾）。这些观察写进相应字段的 rationale。"
    ),
    axes=(
        GenreAxis(
            key="opening_grip",
            label="开篇抓力",
            anchors=(
                "0=读完三分之一仍无冲突、无疑问、无异常；"
                "3=前几段有一处能让人停下的异常或疑问，但被铺陈稀释；"
                "5=首段或次段就抛出冲突/异常/疑问，读者没有划走的窗口。"
            ),
            scope="opening",
        ),
        GenreAxis(
            key="chapter_end_hook",
            label="断章质量",
            anchors=(
                "0=章末把事情说完并收束，读者没有理由翻下一章；"
                "3=章末留了余味但不构成非读不可的悬置；"
                "5=章末停在未答的问题、未落的动作或身份/立场的反转上。"
            ),
            scope="ending",
        ),
    ),
)

PROGRESSION_ENGINE = ChapterFocus(
    key="progression_engine",
    triggers=(("engine", "progression"),),
    # 「立目标 → 受阻 → 兑现」 is the engine, and it is not the property of one audience.
    # GRATIFICATION_BEATS requires male_gratification *and* progression, so 《系统豪横！救宠
    # 奖无限创业金》 — a neutral-audience book whose 84 chapters are exactly that structure,
    # one villain prosecuted and one product line opened per arc — activated only
    # fast_food_hooks: two gated axes and the factory weighting. Its hook vocabulary already
    # read 立标与兑现, because HOOK_VOCABULARY keys on the engine alone. One axis recognised
    # by the naming table and not by the scoring table is not a decision, it is a hole.
    #
    # Registered before GRATIFICATION_BEATS so a 爽文 book's more specific weighting wins the
    # same blocks (merged_weights: later focus replaces the block whole).
    weights={
        "reading_momentum": {
            "plot_progress": 0.30,
            "reading_tension": 0.20,
            "pacing_fit": 0.15,
            "hook_payoff_fit": 0.35,
        },
        "plot_progress": {
            "goal_progress": 0.30,
            "state_change": 0.25,
            "conflict_change": 0.15,
            "information_gain": 0.15,
            "character_agency": 0.10,
            "causal_coherence": 0.05,
        },
    },
    instruction=(
        "- 本书由目标推进：先指明**本章服务于哪一个已经立下的目标**（原样引用正文里的说法），"
        "再说这一章把它推到了哪一步——立下、受阻、部分兑现、还是完成。"
        "「兑现」按**读者能否指着正文说出「这件事成了」**来判断，"
        "不是按人物心情，也不是按叙述者的许诺。"
    ),
    axes=(
        GenreAxis(
            key="goal_clarity",
            label="目标明确度",
            anchors=(
                "0=读完本场景说不出主角在追什么，也说不出谁在挡；"
                "3=目标存在但只在人物心里，正文没有把它说成一件可完成的事；"
                "5=正文里有一个具体、可判定成败的目标，读者能说出「做成什么才算成」。"
                "注意这一项量的是**目标写清楚了没有**，不是目标大不大——"
                "「把这批狗送出收容所」和「统一天下」在这一项上可以同分。"
            ),
        ),
    ),
)

GRATIFICATION_BEATS = ChapterFocus(
    key="gratification_beats",
    triggers=(("audience", "male_gratification"), ("engine", "progression")),
    # A ladder reader tracks whether the promise was paid, so hook_payoff_fit takes the
    # largest share and plot_progress leans on goal_progress and state_change — 升级 is
    # literally a state change, and a chapter where the protagonist ends where he began is
    # the failure mode this weighting has to be able to show.
    weights={
        "reading_momentum": {
            "plot_progress": 0.30,
            "reading_tension": 0.15,
            "pacing_fit": 0.15,
            "hook_payoff_fit": 0.40,
        },
        "plot_progress": {
            "goal_progress": 0.30,
            "state_change": 0.25,
            "conflict_change": 0.20,
            "information_gain": 0.10,
            "character_agency": 0.10,
            "causal_coherence": 0.05,
        },
    },
    instruction=(
        "- 本书是男频升级流：评 hook / payoff 时指明**本章的爽点属于哪一类**"
        "（晋升、获得、打脸、扮猪吃虎、越级压制），以及它在章内的**兑现位置**——"
        "铺垫在本章、兑现也在本章，还是把兑现悬到了下一章。"
    ),
    axes=(
        GenreAxis(
            key="gratification_payoff",
            label="爽点兑现",
            anchors=(
                "0=本场景只有铺垫与受挫，没有任何兑现；"
                "3=有兑现但强度弱，或兑现的对象不是先前施压的那一方；"
                "5=先前的压制被当面、当场、由主角亲手翻转，读者等的那口气出在本场景。"
            ),
        ),
        GenreAxis(
            key="frustration_control",
            label="憋屈控制",
            anchors=(
                "0=通篇受压且不给期限，读者看不到出口；"
                "3=受压有明确的翻盘预告，但本场景未兑现；"
                "5=压制短、指向明确，并在本场景内转为反击。注意：完全没有受挫也不给 5，"
                "无压则无爽。"
            ),
        ),
    ),
)

ROMANCE_BEATS = ChapterFocus(
    key="romance_beats",
    triggers=(("audience", "female_romance"),),
    # 订阅制言情的读者已经付费，不是被悬念拽着走的；开场安静是形式，不是缺陷。情绪投入那一项照常armed。
    suppressed_diagnoses=('weak_tension', 'weak_curiosity',),
    # 情感投入 replaces 追读意愿 as the main curve. Two shifts, both measured against the
    # base suspense weighting: emotional_investment carries the tension block instead of
    # curiosity (a romance reader is not waiting to find something out, she is waiting to
    # see how these two are), and plot_progress drops hard — 《再也不见》第一章 moves the plot
    # almost nowhere and is still doing its job.
    weights={
        "reading_tension": {
            "emotional_investment": 0.50,
            "curiosity": 0.25,
            "tension": 0.25,
        },
        "reading_momentum": {
            "plot_progress": 0.15,
            "reading_tension": 0.45,
            "pacing_fit": 0.15,
            "hook_payoff_fit": 0.25,
        },
    },
    segmentation="\n".join(
        [
            "- 本书是情感向，场景边界**首先看关系状态的变化点**，其次才看地点：",
            "  · 同一个房间、同一批人，如果话题、情绪或两人之间的关系定位发生转折"
            "（从说笑转为坦白、从试探转为摊牌、从并肩转为对峙），**那就是新场景**；",
            "  · 反过来，人物从客厅走到阳台继续同一段对话，地点变了但关系没变，**不要切**。",
            "  一段独处的回想、一次沉默后的开口，都可以自成一个场景。",
        ]
    ),
    instruction=(
        "- 本书是女频情感向：评 emotional_investment / valence 时指明本章处在**哪一个感情节拍**"
        "（初遇、试探、靠近、误会、破裂、和解、确认），以及**糖或刀的强度**——"
        "甜在哪一段、虐在哪一段，写进 rationale。"
    ),
    axes=(
        GenreAxis(
            key="heart_beat_intensity",
            label="心动强度",
            anchors=(
                "0=两人同处一个场景却无任何情绪触点；"
                "3=有触点但停留在客套或误会的层面；"
                "5=有一处具体的、写在正文里的心动瞬间（对视、失语、身体反应、失控的念头）。"
            ),
        ),
        GenreAxis(
            key="relationship_delta",
            label="关系推进",
            anchors=(
                "0=关系温度与场景开始时完全相同；"
                "3=有试探或退让，但关系定位未变；"
                "5=本场景跨过一个可命名的关系节拍（初遇→试探→靠近→误会→破裂→和解→确认），"
                "指明是哪一步。退步也算推进，写明方向。"
            ),
        ),
        GenreAxis(
            key="character_truth",
            label="人物可信度",
            anchors=(
                "0=人物做了违背已建立性格的事，且正文没有任何交代（为推剧情硬掰）；"
                "2=行为说得通，但换成另一个人物也照样成立，看不出是「他」；"
                "5=行为出乎意料，但回头看完全是这个人会做的事。"
                "这一项衡量的是「像不像他」，不是「好不好」——写得再动人，只要不像这个人，就给低分。"
            ),
        ),
        GenreAxis(
            key="emotional_texture",
            label="情绪质感",
            anchors=(
                "0=只有笼统的情绪词（气氛尴尬、五味杂陈、心里一暖），换任何一对男女都能套用；"
                "3=有细节，但是通用细节（下雨、沉默、转身离开）；"
                "5=有只属于这两个人的具体东西——一个他们之间才有的称呼、动作、旧事、物件。"
                "**这一项是慢节奏的正当性所在**：一个场景推进得慢不扣分，写得空才扣分。"
            ),
        ),
    ),
)

PAID_SUBSCRIPTION = ChapterFocus(
    key="paid_subscription",
    triggers=(("monetization", "paid_subscription"),),
    instruction=(
        "- 本书是订阅制（按章付费/会员），读者已经付过钱，不会因为前几段没有钩子就划走——"
        "他们弃的是**追更**。因此不要按「开篇几段内有没有抓住人」来判本章，"
        "而要判**这一章看完之后读者还惦不惦记下一章**。"
        "节奏慢本身不是缺陷，写空才是。"
    ),
    axes=(
        GenreAxis(
            key="chapter_worth",
            label="本章价值",
            anchors=(
                "0=整段跳过不影响后续理解，删掉读者不会察觉；"
                "3=有内容，但都是可以并进别的场景里顺带交代的；"
                "5=有一件只在这里发生、之后会被读者反复回想的事（一句话、一个决定、一次错过）。"
            ),
        ),
        GenreAxis(
            key="return_pull",
            label="追更钩",
            anchors=(
                "0=本章收尾把话说完，读者合上就放下了；"
                "3=有余味，但不构成惦记；"
                "5=读者会带着「他们接下来会怎么样」的念头离开。"
                "注意：订阅制的章末**不必是悬置**，一个未说出口的话、一个停住的动作、"
                "一句余味都算——判据是惦记，不是悬念。"
            ),
            scope="ending",
        ),
    ),
)

MYSTERY_CLUES = ChapterFocus(
    key="mystery_clues",
    triggers=(("engine", "mystery"),),
    # Curiosity is the engine, so it takes the tension block outright. This is close to the
    # shipped default because the shipped default *was* the suspense weighting — the change
    # is that it is now declared as a choice for one type rather than applied to all.
    weights={
        "reading_tension": {
            "curiosity": 0.50,
            "tension": 0.30,
            "emotional_investment": 0.20,
        },
    },
    instruction=(
        "- 本书由悬念驱动：评 information_gain / curiosity / question_lifecycle 时逐条注意"
        "本章**抛出了哪些线索、推进了哪些、回收了哪些**，并判断线索对读者是否**公平**"
        "（答案所需的信息是否在揭晓前给过读者）。误导要标记为误导，不算信息增益。"
    ),
    axes=(
        GenreAxis(
            key="clue_placement",
            label="线索投放",
            anchors=(
                "0=本场景没有投放、推进或回收任何线索；"
                "3=有线索但对读者不构成可推理的材料（只是气氛或暗示）；"
                "5=投放或回收了具体、可验证、能被读者用来推断的线索，指出是哪一条。"
            ),
        ),
        GenreAxis(
            key="fair_play",
            label="信息公平",
            anchors=(
                "0=揭晓依赖读者从未见过的信息；"
                "3=线索给过，但埋得读者几乎不可能注意到；"
                "5=答案所需的信息在揭晓前都以读者可见的方式出现过。"
                "本场景若无揭晓，就按「本场景投放的线索是否对读者可见」评。"
                "误导（红鲱鱼）是手法不是缺陷，但要标出来，且不计入信息增益。"
            ),
        ),
    ),
)

ROMANCE_ENGINE = ChapterFocus(
    key="romance_engine",
    triggers=(("engine", "romance"),),
    # 同上：关系驱动的书低张力低好奇是常态，真正该报警的是情绪没有起伏。
    suppressed_diagnoses=('weak_tension', 'weak_curiosity',),
    instruction=(
        "- 本书由关系驱动：goal_progress 的「目标」按**关系目标**理解（接近、澄清、承诺），"
        "而不只看外部事件；两人关系温度在本章的进退，写进 state_change 的 rationale。\n"
        "- `reader_questions_opened` 在这类书里问的是**关系**，不是谜题："
        "「他到底知不知道她在等？」「这句话说出口会毁掉什么？」都是合法的读者问题。"
        "**不要因为本章没有悬疑式的谜题就判定没有钩子**——那是拿悬疑的尺子量言情。"
    ),
    axes=(
        GenreAxis(
            key="relational_stake",
            label="关系风险",
            anchors=(
                "0=本场景中两人之间没有任何可能失去的东西；"
                "3=有隐忧但未被触碰；"
                "5=本场景明确出现可能让关系倒退或破裂的力量（第三人、身份、误解、外部压力）。"
            ),
        ),
    ),
)

ENSEMBLE_POV = ChapterFocus(
    key="ensemble_pov",
    triggers=(("pov", "ensemble"),),
    instruction=(
        "- 本书是群像多线：先指明**本章通过谁的视角**叙述（用正文原样称呼），"
        "并说明这条线与主线的关系（推进主线 / 平行支线 / 纯铺垫）。"
        "视角人物不是全书主角时，character_agency 按**本章视角人物**评。"
    ),
    axes=(
        GenreAxis(
            key="thread_contribution",
            label="本线贡献",
            anchors=(
                "0=本场景这条线与主线毫无交集，也未建立任何后续所需的东西；"
                "3=推进了支线自身，主线只被提及；"
                "5=本线在本场景交出了主线需要的东西（信息、位置、压力、人物变化）。"
            ),
        ),
    ),
)

EPISODIC_UNIT = ChapterFocus(
    key="episodic_unit",
    triggers=(("engine", "episodic_transmigration"),),
    instruction=(
        "- 本书是单元结构（无限流 / 快穿）：指明本章处在**当前单元的哪个位置**"
        "（入局、探索、规则揭示、决战、结算/过渡），跨单元的主线信息单独指出。"
        "单元切换处的 clarity 下降按结构性成本看待，写明而不是直接扣为缺陷。"
    ),
    axes=(
        GenreAxis(
            key="rule_clarity",
            label="规则清晰",
            anchors=(
                "0=本单元的规则或胜负条件在本场景后仍不可知，读者无法判断处境；"
                "3=规则给了一部分，代价或边界仍模糊；"
                "5=本场景明确了规则、代价与失败后果中的至少两项。"
            ),
        ),
        GenreAxis(
            key="unit_stake",
            label="单元代价",
            anchors=(
                "0=失败没有可见后果；"
                "3=后果被说明但未被演示；"
                "5=本场景让读者看见失败的代价落在具体的人身上。"
            ),
        ),
    ),
)

SLICE_RHYTHM = ChapterFocus(
    key="slice_rhythm",
    triggers=(("engine", "slice_of_life"),),
    # 日常向连「慢」本身都不是缺陷，所以连 pacing_too_slow 一并撤掉；空写仍由情绪质感那一项抓。
    suppressed_diagnoses=('weak_tension', 'weak_curiosity', 'pacing_too_slow',),
    # Low tension is the genre, not a defect, so the tension block leans on investment and
    # the momentum formula stops asking a 种田 chapter to escalate.
    weights={
        "reading_tension": {
            "emotional_investment": 0.55,
            "curiosity": 0.30,
            "tension": 0.15,
        },
        "reading_momentum": {
            "plot_progress": 0.20,
            "reading_tension": 0.40,
            "pacing_fit": 0.25,
            "hook_payoff_fit": 0.15,
        },
    },
    instruction=(
        "- 本书是日常种田向：不要因为**没有强冲突**而压低本章评分——"
        "tension 低是这一类型的常态而非缺陷。注意本章的**情绪回报来源**"
        "（食物、经营进展、人情往来、小目标达成）并写进 rationale。"
    ),
    axes=(
        GenreAxis(
            key="comfort_reward",
            label="情绪回报",
            anchors=(
                "0=本场景既无进展也无满足，只是时间流过；"
                "3=有小回报但写得笼统（「大家都很开心」）；"
                "5=有一处具体可感的回报——食物、经营数字、人情的回应、久等的小目标达成。"
            ),
        ),
        GenreAxis(
            key="texture_density",
            label="生活质感",
            anchors=(
                "0=场景可以发生在任何地方任何时代；"
                "3=有环境描写但停留在通用词；"
                "5=有只属于这个时空的具体物件、手艺、说法或规矩。"
            ),
        ),
    ),
)

ENSEMBLE_POLITICS = ChapterFocus(
    key="ensemble_politics",
    triggers=(("engine", "ensemble_politics"),),
    # The focus's own instruction says to read 「哪一方得到了什么、失去了什么」 and 「谁知道
    # 什么、谁以为什么」, so the curve has to weigh the same things: what moved and who now
    # knows it. character_agency drops because in this form the protagonist is frequently
    # not the mover — 《醉枕江山》第一章 rises 68→84.6 on soldiers arriving and a official
    # ordering a village killed, none of which the viewpoint character causes.
    weights={
        "plot_progress": {
            "information_gain": 0.25,
            "state_change": 0.25,
            "conflict_change": 0.20,
            "goal_progress": 0.15,
            "causal_coherence": 0.10,
            "character_agency": 0.05,
        },
    },
    instruction=(
        "- 本书是群像权谋：推动情节的不是单个人物的目标，而是**势力之间的位置变化**。"
        "评 goal_progress / conflict_change 时按「哪一方得到了什么、失去了什么」来看，"
        "而不是只看主角。人物说的话与他的真实立场可能不一致，"
        "把「谁知道什么、谁以为什么」写进 rationale。"
    ),
    axes=(
        GenreAxis(
            key="power_shift",
            label="势力变动",
            anchors=(
                "0=本场景各方位置与开场完全相同；"
                "3=有交锋但格局未动，只是试探；"
                "5=有一方实质性得到或失去了东西（人、地盘、把柄、名分），指明是哪一方哪一样。"
            ),
        ),
        GenreAxis(
            key="information_asymmetry",
            label="信息差",
            anchors=(
                "0=在场所有人和读者知道的一样多；"
                "3=有人藏了话，但读者也不知道藏的是什么；"
                "5=读者比场上至少一个人多知道一件事，或场上有人比读者多知道一件"
                "**且这一点被明确暗示**。权谋的张力来自谁蒙在鼓里，不是来自吵得凶。"
            ),
        ),
    ),
)

DUAL_LEAD = ChapterFocus(
    key="dual_lead",
    triggers=(("pov", "dual_lead"),),
    instruction=(
        "- 本书是双主角/双视角：先指明**本场景属于哪一方的视角**（用正文原样称呼）。"
        "两条线各自的进度要分开说，不要合成一个「主角推进了多少」。"
    ),
    axes=(
        GenreAxis(
            key="thread_necessity",
            label="换线必要",
            anchors=(
                "0=这一段换到另一方视角没有带来任何对方视角才有的东西，换回来也不损失；"
                "3=有独有信息，但也可以由对方转述；"
                "5=只有站在这一方才能看见（他的误解、他的隐瞒、他此刻不知道的事）。"
                "双线的代价是读者要重新代入一次，这一项衡量那次代入值不值。"
            ),
        ),
    ),
)

#: What the main reading curve is called, and what decision it stands for, per profile. The
#: label is not decoration: 「综合阅读 69」 invites the reader to ask 69 out of what, while
#: 「追读意愿」 and 「情感投入」 each name a decision a real reader makes. Which one applies is a
#: fact about the book, so the backend answers it (INV-P4) rather than letting the client
#: re-derive the genre.
#:
#: Ordered most-specific first; the first matching entry wins.
MAIN_CURVE_NAMING: tuple[tuple[tuple[tuple[str, str], ...], str, str], ...] = (
    (
        (("audience", "female_romance"),),
        "情感投入",
        "读者已经付费或已经追进来了，主线量的是「还在不在乎这些人」，不是「会不会划走」。",
    ),
    (
        (("engine", "romance"),),
        "情感投入",
        "关系驱动的书，主线量的是两个人之间的进退，而不是事件推进了多少。",
    ),
    (
        (("engine", "slice_of_life"),),
        "沉浸度",
        "日常向的书没有强冲突，主线量的是读者愿不愿意在这个世界里多待一会儿。",
    ),
    (
        (("audience", "male_gratification"), ("engine", "progression")),
        "期待值",
        "升级流的读者在等兑现，主线量的是「憋着还是爽着」。",
    ),
    (
        (("engine", "ensemble_politics"),),
        "局势张力",
        "群像权谋的读者跟的既不是某个人的目标，也不是谜底，而是各方位置的变化——"
        "主线量的是「局面绷得有多紧」。",
    ),
    (
        (("monetization", "fast_food_free"),),
        "追读意愿",
        "免费流读者随时可划走，主线量的是「还想不想翻下一页」。",
    ),
    (
        (("engine", "mystery"),),
        "追读意愿",
        "悬念驱动的书，主线量的是读者被未答问题拉着走的程度。",
    ),
)

#: Shown when the book has no confirmed profile. Deliberately the old wording: without a
#: profile there is no basis for claiming which decision the reader is making.
DEFAULT_MAIN_CURVE = ("综合阅读", "本书尚未确认作品画像，主线按通用阅读动力计算。")


#: What to call each of the four things a scene can do to the reader's open questions.
#:
#: The four actions are structural and genre-free — a question is raised, deepened, answered,
#: or carried out of the chapter. Their *names* are not. The shipped set 「提出疑问／加深悬念／
#: 给出回应／留到下章」 is the suspense reading of them, and it was applied to every book. On
#: 《再也不见》 that produced three findings which all say the same thing — 「不足以构成强烈钩子」,
#: 「缺乏吸引力」, 「作为章末钩子强度中等」 — i.e. the book does not run on suspense, recorded as a
#: defect. Renaming the same four actions in the book's own terms is what stops a romance
#: chapter from being read as a failed mystery.
#:
#: Ordered most-specific first, first match wins — same convention as MAIN_CURVE_NAMING.
#: Keys are the structural actions, never shown to the reader.
HOOK_ACTIONS = ("open", "deepen", "answer", "carry")

#: Two more names carried by the same table. `lens` is what the lens itself is called and
#: `first_mark` is what its first-occurrence vital is called — 「钩子回收」 and 「首钩位置」 are
#: as much the suspense reading as 「提出疑问」 was, and renaming only the four actions left a
#: romance chapter reading 「钩子回收 · 首钩位置 P2 · 起了心结」: two vocabularies, one screen.

HOOK_VOCABULARY: tuple[tuple[tuple[tuple[str, str], ...], dict[str, str]], ...] = (
    (
        (("audience", "female_romance"),),
        {
            "open": "起了心结",
            "deepen": "越陷越深",
            "answer": "挑明",
            "carry": "悬而未说",
            "lens": "心结与挑明",
            "first_mark": "第一处牵挂",
        },
    ),
    (
        (("engine", "romance"),),
        {
            "open": "起了心结",
            "deepen": "越陷越深",
            "answer": "挑明",
            "carry": "悬而未说",
            "lens": "心结与挑明",
            "first_mark": "第一处牵挂",
        },
    ),
    (
        (("audience", "male_gratification"), ("engine", "progression")),
        {
            "open": "立下目标",
            "deepen": "受阻加码",
            "answer": "兑现",
            "carry": "留到下章",
            "lens": "立标与兑现",
            "first_mark": "第一个目标",
        },
    ),
    (
        (("engine", "progression"),),
        {
            "open": "立下目标",
            "deepen": "受阻加码",
            "answer": "兑现",
            "carry": "留到下章",
            "lens": "立标与兑现",
            "first_mark": "第一个目标",
        },
    ),
    (
        (("engine", "ensemble_politics"),),
        {
            # A political ensemble's reader is not tracking a mystery's answer, they are
            # tracking who now knows what. 「埋了个局」 opens that, 「摊牌」 closes it.
            "open": "埋了个局",
            "deepen": "局面收紧",
            "answer": "摊牌",
            "carry": "按下不表",
            "lens": "布局与摊牌",
            "first_mark": "第一处布局",
        },
    ),
    (
        (("pov", "dual_lead"),),
        {
            # Two leads: what is open is the gap between what each of them knows.
            "open": "错开了",
            "deepen": "错得更远",
            "answer": "对上了",
            "carry": "悬而未说",
            "lens": "错位与对上",
            "first_mark": "第一处错位",
        },
    ),
    (
        (("engine", "slice_of_life"),),
        {
            "open": "留了个念想",
            "deepen": "念想变重",
            "answer": "落定",
            "carry": "留到下章",
            "lens": "念想与落定",
            "first_mark": "第一处念想",
        },
    ),
)

#: The suspense reading. Correct for mystery and for fast-food free, and the honest default
#: for a book whose profile is not confirmed — with no profile there is no basis for
#: claiming the reader is tracking a relationship rather than a question.
DEFAULT_HOOK_VOCABULARY: dict[str, str] = {
    "open": "提出疑问",
    "deepen": "加深悬念",
    "answer": "给出回应",
    "carry": "留到下章",
    "lens": "钩子回收",
    "first_mark": "首钩位置",
}


#: Axis values that deliberately carry no focus, and why. Declared rather than left absent
#: so the coverage test can tell "nobody got to it yet" apart from "there is nothing
#: type-specific to say", and so a reviewer sees the decision instead of a hole.
NO_FOCUS_BY_DESIGN: dict[tuple[str, str], str] = {
    ("audience", "neutral"): (
        "中性受众就是没有受众侧重——它的意思正是「不按爽感也不按情感来读」，"
        "再加一层侧重等于凭空发明一个倾向。类型判断交给 engine 轴。"
    ),
    ("pov", "single_lead"): "单主角是默认形态，21 项基础维度本来就是按它写的。",
    ("length", "short"): "长度不改变看什么，只改变期待值——见 LENGTH_EXPECTATION。",
    ("length", "medium"): "同上。",
    ("length", "long"): "同上。",
    ("length", "epic"): "同上。",
}

#: Length modulates rather than adds. A 短篇 cannot afford a chapter that only sets up, an
#: 超长篇 can; the axes asked for are the same either way, so this is a note for the
#: prompt rather than a scored dimension.
LENGTH_EXPECTATION: dict[str, str] = {
    "short": "本书篇幅很短，单章的铺垫预算极小：一个只做铺垫、不给回报的场景在这里是奢侈的。",
    "medium": "",
    "long": "",
    "epic": "本书篇幅极长，允许单章慢；判断一个慢场景时看它在长线上有没有位置，不要按单章收支算。",
}

#: Registered chapter foci. Adding one requires the trigger to be a legal axis value (the
#: dataclass enforces it at import time) and a case in ``test_chapter_profile_focus.py``.
#: Order is the per-scene axis budget's priority — see ``selected_axes``.
CHAPTER_FOCI: tuple[ChapterFocus, ...] = (
    FAST_FOOD_HOOKS,
    PAID_SUBSCRIPTION,
    PROGRESSION_ENGINE,
    GRATIFICATION_BEATS,
    ROMANCE_BEATS,
    MYSTERY_CLUES,
    ENSEMBLE_POLITICS,
    ROMANCE_ENGINE,
    ENSEMBLE_POV,
    DUAL_LEAD,
    EPISODIC_UNIT,
    SLICE_RHYTHM,
)


def _resolve_axes(axes: Mapping[str, Any]) -> dict[str, str]:
    """Same resolution rule as ``deltas.deltas_for``: stored shape or plain mapping."""
    resolved: dict[str, str] = {}
    for axis, value in (axes or {}).items():
        resolved[axis] = value.get("value", "") if isinstance(value, Mapping) else str(value)
    return resolved


def chapter_foci_for(axes: Mapping[str, Any]) -> tuple[ChapterFocus, ...]:
    resolved = _resolve_axes(axes)
    return tuple(
        focus
        for focus in CHAPTER_FOCI
        if all(resolved.get(axis) == value for axis, value in focus.triggers)
    )


#: At most this many *per-scene* axes are asked for. The cap counts what every scene pays
#: for: a gated axis (开篇抓力 on the opening, 断章质量 / 追更钩 on the ending) is scored once
#: per chapter, so charging it against the same budget would price a nearly-free question
#: like a per-scene one — and on a 订阅制情感文 that is exactly what squeezed out 情绪质感,
#: the axis that decides whether a slow chapter is worth its length.
MAX_GENRE_AXES = 5


def anchors_for(key: str) -> str:
    """这条轴的 0 / 3 / 5 各是什么样子，按 key 取。

    锚点此前只进提示词，不进响应：屏幕上写着「线索投放 0/5」，而 5 分长什么样只有模型
    知道。读者看到一个分数和一句针对本场的理由，却无从判断这个刻度严不严——
    ``GenreAxis`` 的文档里已经说明了没有锚点的后果（clarity 在 42 个场景里 81% 返回 5），
    那个道理对读者同样成立。

    按 key 现取，而不是写进存下来的产物：这样这次改动之前跑的报告也能显示刻度，
    而且刻度改了以后不会有两份说法。
    """
    for focus in CHAPTER_FOCI:
        for axis in focus.axes:
            if axis.key == key:
                return axis.anchors
    return ""


def selected_axes(foci: Sequence[ChapterFocus]) -> tuple[GenreAxis, ...]:
    """The axes to score, deduplicated, in registration order, capped at ``MAX_GENRE_AXES``.

    Registration order is the priority. ``CHAPTER_FOCI`` runs from the axis that most
    determines how a book is read (monetization, then audience, then engine) downward, so a
    book matching four foci keeps the axes that decide the most about it.
    """
    seen: set[str] = set()
    axes: list[GenreAxis] = []
    per_scene = 0
    for focus in foci:
        for axis in focus.axes:
            if axis.key in seen:
                continue
            if axis.scope == "scene":
                if per_scene >= MAX_GENRE_AXES:
                    continue
                per_scene += 1
            seen.add(axis.key)
            axes.append(axis)
    return tuple(axes)


def required_axis_keys(axes: Sequence[GenreAxis]) -> set[str]:
    """The axes every scene must carry.

    The gated ones are excluded: 开篇抓力 belongs to the chapter's first scene and 断章质量 to
    its last, so demanding them everywhere would be demanding the noise the scope gate exists
    to remove. Everything else is per-scene, and a scene that silently omits one leaves a
    hole in a curve the reader reads across scenes — the first production run under this
    prompt dropped both axes on scene 5 of 6 and nothing noticed.
    """
    return {axis.key for axis in axes if axis.scope == "scene"}


def _axes_block(axes: Sequence[GenreAxis]) -> str:
    if not axes:
        return ""
    lines = [
        "",
        "",
        "### 本书专项维度（写入 genre_axes）",
        "这些维度与上面 21 项并列，不替代也不豁免其中任何一项。level 同样 0—5，"
        "且必须给出正文段号作为证据；给不出证据就给低 level，不要凭印象打高分。",
        "**每一个场景都要给出下面每一条**（标了适用范围的除外）。这一场没有可评的内容，"
        "就给 0 并写明为什么没有——整条略去会让这一场在曲线上凭空断开。",
        "`key` 必须原样取自下面的清单，不得自造；清单之外的维度一律不要写进 genre_axes。",
    ]
    for axis in axes:
        # Two of these are chapter properties. Scoring 断章质量 on a middle scene is not a
        # low score, it is a meaningless one — the scene simply is not where the chapter
        # ends — so those axes are asked only of the scene that actually carries them.
        if axis.scope == "opening":
            gate = "【仅当 is_chapter_opening=true 的场景才给这一条，其它场景不要写】"
        elif axis.scope == "ending":
            gate = "【仅当 is_chapter_ending=true 的场景才给这一条，其它场景不要写】"
        else:
            gate = ""
        lines.append(f"- `{axis.key}`（{axis.label}）：{axis.anchors}{gate}")
    return "\n".join(lines)


_SEG_HEADER = (
    "## 切分侧重（来自本书已确认的画像）"
    + chr(10)
    + "以下规则**优先于**上文的通用场景定义；上文其余部分不变。"
)


def segmentation_focus_prompt(foci: Sequence[ChapterFocus]) -> str:
    """The boundary-prompt block, or "" when this book's profile has nothing to add."""
    parts = [focus.segmentation for focus in foci if focus.segmentation]
    if not parts:
        return ""
    return chr(10) * 2 + _SEG_HEADER + chr(10) + chr(10).join(parts)


def segmentation_focus_for_book(session: Session, book_id: int) -> str:
    return segmentation_focus_prompt(chapter_foci_for_book(session, book_id))


def apply_segmentation_focus(prompt: Any, session: Session, book_id: int) -> Any:
    """Append the book's boundary rule to a ``PromptBundle``; identity when there is none."""
    block = segmentation_focus_for_book(session, book_id)
    if not block:
        return prompt
    system = prompt.system + block
    digest = hashlib.sha256(
        (system + prompt.user_template + prompt.repair_template).encode()
    ).hexdigest()
    return type(prompt)(
        task_type=prompt.task_type,
        version=prompt.version,
        system=system,
        user_template=prompt.user_template,
        repair_template=prompt.repair_template,
        content_hash=digest,
    )


def chapter_focus_prompt(foci: Sequence[ChapterFocus]) -> str:
    """The block to append, or "" — and empty is the load-bearing case: with no focus the
    prompt must stay byte identical, or every unprofiled book's prompt hash moves."""
    if not foci:
        return ""
    return (
        "\n\n"
        + _HEADER
        + "\n"
        + "\n".join(focus.instruction for focus in foci)
        + _axes_block(selected_axes(foci))
    )


def main_curve_naming(axes: Mapping[str, Any]) -> tuple[str, str]:
    """The main curve's name and the decision it stands for, for these axes."""
    resolved = _resolve_axes(axes)
    for triggers, label, why in MAIN_CURVE_NAMING:
        if all(resolved.get(axis) == value for axis, value in triggers):
            return label, why
    return DEFAULT_MAIN_CURVE


def main_curve_naming_for_book(session: Session, book_id: int) -> tuple[str, str]:
    """Naming for a book, defaulting unless its profile is confirmed (INV-P2)."""
    try:
        stored = BookProfileRepository(session).get(int(book_id))
    except Exception:  # noqa: BLE001 — unreadable profile = no profile
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return DEFAULT_MAIN_CURVE
    if not stored or not stored.get("confirmed_at"):
        return DEFAULT_MAIN_CURVE
    return main_curve_naming(stored.get("axes") or {})


def hook_vocabulary(axes: Mapping[str, Any]) -> dict[str, str]:
    """What to call open / deepen / answer / carry, for these axes."""
    resolved = _resolve_axes(axes)
    for triggers, table in HOOK_VOCABULARY:
        if all(resolved.get(axis) == value for axis, value in triggers):
            return dict(table)
    return dict(DEFAULT_HOOK_VOCABULARY)


def hook_vocabulary_for_book(session: Session, book_id: int) -> dict[str, str]:
    """Vocabulary for a book, defaulting unless its profile is confirmed (INV-P2).

    A drafted profile is an inference; naming the reader's experience off an inference is
    exactly the substitution INV-P2 forbids, so an unconfirmed book keeps the suspense
    wording it has today.
    """
    try:
        stored = BookProfileRepository(session).get(int(book_id))
    except Exception:  # noqa: BLE001 — unreadable profile = no profile
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return dict(DEFAULT_HOOK_VOCABULARY)
    if not stored or not stored.get("confirmed_at"):
        return dict(DEFAULT_HOOK_VOCABULARY)
    return hook_vocabulary(stored.get("axes") or {})


def suppressed_diagnoses(foci: Sequence[ChapterFocus]) -> frozenset[str]:
    """Union of the matching foci's suppressions."""
    return frozenset(code for focus in foci for code in focus.suppressed_diagnoses)


def suppressed_diagnoses_for_book(session: Session, book_id: int) -> frozenset[str]:
    """Suppressions for a book, empty unless its profile is confirmed (INV-P2).

    A drafted profile is an inference, and silently withdrawing a defect flag on the
    strength of an inference is worse than the false positive it removes: the reader has no
    way to know a warning was suppressed.
    """
    try:
        stored = BookProfileRepository(session).get(int(book_id))
    except Exception:  # noqa: BLE001 — unreadable profile = no profile
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return frozenset()
    if not stored or not stored.get("confirmed_at"):
        return frozenset()
    return suppressed_diagnoses(chapter_foci_for(stored.get("axes") or {}))


def merged_weights(foci: Sequence[ChapterFocus]) -> dict[str, dict[str, float]]:
    """Collapse the matching foci's weight overrides, block by block.

    Registration order decides when two foci touch the same block: the later one wins, so a
    engine-level statement can refine what an audience-level one set. Blocks nobody names are
    absent from the result, which is how the caller knows to keep the shipped config for
    them rather than substituting a zeroed table.
    """
    out: dict[str, dict[str, float]] = {}
    for focus in foci:
        for block, table in focus.weights.items():
            out[block] = {key: float(value) for key, value in table.items()}
    return out


def formula_weights_for_book(session: Session, book_id: int) -> dict[str, dict[str, float]]:
    """This book's weight overrides, or {} unless its profile is confirmed (INV-P2)."""
    return merged_weights(chapter_foci_for_book(session, book_id))


def apply_formula_weights(
    config: Mapping[str, Any], overrides: Mapping[str, Mapping[str, float]]
) -> dict[str, Any]:
    """Return a copy of the formula config with ``weights`` blocks replaced.

    Replaced whole, not merged key by key: a weight table is a distribution summing to 1,
    so mixing half of one with half of another produces a table that sums to neither and
    silently rescales every score. ``__post_init__`` already checked each declared block
    sums to 1; this keeps that guarantee true of what the deriver actually sees.
    """
    if not overrides:
        return dict(config)
    merged = dict(config)
    weights = dict(merged.get("weights") or {})
    for block, table in overrides.items():
        weights[block] = dict(table)
    merged["weights"] = weights
    return merged


def chapter_foci_for_book(session: Session, book_id: int) -> tuple[ChapterFocus, ...]:
    """The foci a book's *confirmed* profile selects, or () (INV-P2).

    Reads defensively: a database from before the profile migration has no
    ``book_profiles`` table, and a chapter run on such a database must behave exactly like
    a run on a book that never had a profile — the focus is an enhancement, never the
    reason an analysis fails.
    """
    try:
        stored = BookProfileRepository(session).get(int(book_id))
    except Exception:  # noqa: BLE001 — unreadable profile = no profile
        # The failed SELECT leaves the session's transaction poisoned; roll it back so the
        # pipeline that lent us the session can keep using it.
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return ()
    if not stored or not stored.get("confirmed_at"):
        return ()
    return chapter_foci_for(stored.get("axes") or {})


def chapter_focus_for_book(session: Session, book_id: int) -> str:
    """The focus block for a book, "" unless its profile is confirmed (INV-P2)."""
    return chapter_focus_prompt(chapter_foci_for_book(session, book_id))


def apply_chapter_focus(prompt: Any, session: Session, book_id: int) -> Any:
    """Append the book's focus block to a ``PromptBundle`` system prompt.

    Returns the bundle unchanged (same object, same hash) when there is nothing to add.
    The content hash is recomputed with the same formula ``load_prompt`` uses, so recorded
    provenance keeps describing the text that actually ran.
    """
    block = chapter_focus_for_book(session, book_id)
    if not block:
        return prompt
    system = prompt.system + block
    digest = hashlib.sha256((system + prompt.user_template + prompt.repair_template).encode()).hexdigest()
    return type(prompt)(
        task_type=prompt.task_type,
        version=prompt.version,
        system=system,
        user_template=prompt.user_template,
        repair_template=prompt.repair_template,
        content_hash=digest,
    )


#: What to call the book's type, from the axes a person confirmed.
#:
#: The whole-book report has been printing whatever the final synthesis call guessed — on
#: 《系统豪横》 that was 「都市生活」 with a confidence of 0.0, sitting on a page belonging to a
#: user who had themselves confirmed the book as 升级流. INV-P2 says human confirmation
#: outranks inference, and nowhere is that clearer than here: the profile is the one thing on
#: the screen the user typed in, and the report contradicted it.
#:
#: Ordered most-specific first; the first matching entry wins. Genre in the web-novel sense is
#: mostly engine plus audience — 升级流 is 升级流 whoever it is written for, but a 男频 one and
#: a 女频 one are not sold, read or written the same way, so where both axes are confirmed both
#: are said.
GENRE_NAMING: tuple[tuple[tuple[tuple[str, str], ...], str], ...] = (
    ((("engine", "progression"), ("audience", "male_gratification")), "男频升级流"),
    ((("engine", "progression"), ("audience", "female_romance")), "女频升级流"),
    ((("engine", "progression"),), "升级流"),
    ((("engine", "romance"), ("audience", "female_romance")), "女频言情"),
    ((("engine", "romance"),), "言情"),
    ((("engine", "mystery"),), "悬疑"),
    ((("engine", "ensemble_politics"),), "群像权谋"),
    ((("engine", "slice_of_life"),), "种田日常"),
    ((("engine", "episodic_transmigration"),), "快穿单元剧"),
    # No engine confirmed, but an audience is: worth saying, and honestly less than the above.
    ((("audience", "female_romance"),), "女频"),
    ((("audience", "male_gratification"),), "男频"),
)


def genre_naming(axes: Mapping[str, Any]) -> str:
    """The confirmed profile's own name for this book's type, or "" if the axes say nothing."""
    resolved = _resolve_axes(axes)
    for triggers, label in GENRE_NAMING:
        if all(resolved.get(axis) == value for axis, value in triggers):
            return label
    return ""
