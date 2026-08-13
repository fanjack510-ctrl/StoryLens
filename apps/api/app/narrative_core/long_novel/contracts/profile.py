"""The five profile axes and their closed value sets (10_ADAPTIVE_PROFILE_LAYER §3, §8.2).

Every axis is a **closed set**. This is not tidiness: the axes dispatch extraction deltas,
report modules and assessment weights, and an engine cannot select a delta for a value it
does not recognise. The confirmation UI renders these as dropdowns for the same reason —
free text would let a user pick something nothing knows how to act on.

The dividing line, stated once:

    值驱动行为的字段必须是闭集;仅用于展示的字段可以是模型自由文本。

So the axes below are closed, while `primary_genre` ("仙侠") and `narrative_drivers`
("身份谜团") stay free text in the output document, because they are read by people rather
than by code.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "Monetization",
    "Audience",
    "NarrativeEngine",
    "PointOfView",
    "BookLength",
    "AXES",
    "AXIS_LABELS",
    "is_legal",
]


class Monetization(str, Enum):
    """Axis 1 — how the book reaches its reader, which decides where the analysis weight goes.

    Free ad-supported platforms acquire readers through an algorithmic feed, so the opening
    three chapters decide whether the book is read at all. Paid platforms are found through
    rankings and tolerate a longer approach, but live or die on retention past the paywall.
    """

    FAST_FOOD_FREE = "fast_food_free"
    PAID_SUBSCRIPTION = "paid_subscription"


class Audience(str, Enum):
    """Axis 2 — what the reader is there for, which decides the instrument.

    A male-oriented progression novel is measured by its gratification beats; a romance is
    measured by its relationship beats. Using one ruler on the other produces a confident
    wrong answer, which is worse than no answer.
    """

    MALE_GRATIFICATION = "male_gratification"
    FEMALE_ROMANCE = "female_romance"
    NEUTRAL = "neutral"


class NarrativeEngine(str, Enum):
    """Axis 3 — what actually pulls the reader forward."""

    PROGRESSION = "progression"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    ENSEMBLE_POLITICS = "ensemble_politics"
    SLICE_OF_LIFE = "slice_of_life"
    EPISODIC_TRANSMIGRATION = "episodic_transmigration"


class PointOfView(str, Enum):
    """Axis 4 — decided by counting mentions across the whole book, never by a sample.

    See ``profile_stats.pov_from_distribution``: on a real 806-chapter book the opening
    tenth says ``SINGLE_LEAD`` and the whole book says ``ENSEMBLE``.
    """

    SINGLE_LEAD = "single_lead"
    DUAL_LEAD = "dual_lead"
    ENSEMBLE = "ensemble"


class BookLength(str, Enum):
    """Axis 5 — computed from the character count; affects planning, not schema."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    EPIC = "epic"


AXES: dict[str, type[Enum]] = {
    "monetization": Monetization,
    "audience": Audience,
    "engine": NarrativeEngine,
    "pov": PointOfView,
    "length": BookLength,
}

#: What the confirmation dropdowns say. Kept beside the values so the label a user picks and
#: the value the engine dispatches on cannot drift apart.
AXIS_LABELS: dict[str, dict[str, str]] = {
    "monetization": {
        "fast_food_free": "快餐免费流(番茄/七猫/书旗)",
        "paid_subscription": "付费订阅流(起点/晋江)",
    },
    "audience": {
        "male_gratification": "男频爽文向",
        "female_romance": "女频情感向",
        "neutral": "中性 / 双向",
    },
    "engine": {
        "progression": "升级流",
        "mystery": "悬疑推理",
        "romance": "情感关系",
        "ensemble_politics": "权谋群像",
        "slice_of_life": "日常种田",
        "episodic_transmigration": "无限流 / 快穿(单元结构)",
    },
    "pov": {
        "single_lead": "单主角",
        "dual_lead": "双主角 / CP 双线",
        "ensemble": "群像多线",
    },
    "length": {
        "short": "短篇(<50 万字)",
        "medium": "中篇(50–150 万字)",
        "long": "长篇(150–400 万字)",
        "epic": "超长篇(>400 万字)",
    },
}


def is_legal(axis: str, value: str) -> bool:
    """Is this a value the engine can dispatch on?

    Used to reject both a model that invents a genre name and a client that posts one. An
    illegal value must never be stored: a profile the engine cannot read is worse than an
    unconfirmed one, because it looks decided.
    """
    enum = AXES.get(axis)
    return bool(enum) and value in {member.value for member in enum}
