"""短篇精读 — the contract for reading a whole short piece the way a person breaks one down.

Not a smaller whole-book report. The two answer different questions and are measured in
different units: the whole-book engine's smallest unit is a chapter, and a short piece often
has no chapters at all — 《剩女遇见爱情》 arrived as one 194,000-character "chapter" and could
not be analysed by anything.

The shape here is taken from sixty human breakdowns in `data/raw/breakdowns/`, of which
twenty-one use the 「拆稿学习表」 template. That template is one row per **segment**, six
columns wide:

    分段字数 | 故事进展 | 地点/人物 | 事件/冲突 | 学习之处 | 自己的联想/感慨

Measured on the fifteen of those with a recorded length: 9,143 to 19,199 characters, median
11,830, cut into 8–70 segments — commonly 15–30, so roughly **790 characters a segment**. That
is the working unit of this pipeline, and it is finer than a chapter by an order of magnitude.

Two things the corpus does that this contract deliberately copies:

**It summarises more than it quotes.** Only 37% of the 190 craft notes carry a quotation. The
whole-book breakdown requires a verbatim quote for every claim; here evidence is optional per
segment, because a segment is already a located span of text — the reader can turn to it.

**The emotional note is a label, not a diagnosis.** 112 of them, averaging 24 characters:
「至暗时刻」, 「挑战失败」, 「获得胜利」, 「反转：前任们见面，没有撕逼」. It says where the reader is,
not what the author should change. Diagnosis belongs to 评测 and is not offered here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


#: Where a segment leaves the reader, relative to where it found them. The corpus writes the
#: whole-piece emotion as two lists — 上行情绪 / 下行情绪, each numbered 阶段①②③ — so direction
#: is the thing being recorded, not a magnitude. A 0–100 score here would be a measurement
#: nobody made.
EmotionDirection = Literal["up", "down", "flat"]


class ShortFormSegment(M):
    """One row of the 拆稿学习表, plus the span it was cut from."""

    index: int = Field(ge=1)
    #: Inclusive paragraph range in the piece, 1-based. This is what makes the row checkable:
    #: every column below is a claim about exactly these paragraphs.
    paragraph_start: int = Field(ge=1)
    paragraph_end: int = Field(ge=1)
    #: 分段字数 — counted by the engine, never asked of the model.
    characters: int = Field(ge=0)

    #: 故事进展 — where the story has got to. 「陷入危机」「第2次循环」
    phase: str = ""
    #: 地点/人物 — 「家/女主、外婆、王翠兰」
    setting: str = ""
    #: 事件/冲突 — what happens, in order.
    beats: list[str] = Field(default_factory=list)
    #: 学习之处 — what this move does and what it costs. The corpus averages 41 characters and
    #: writes mechanism: 「再来一次，解决了一些困难，但是出现了漏洞，增加了结局的不确定性」.
    craft: str = ""
    #: 自己的联想/感慨 — where the reader is. Averages 24 characters in the corpus.
    emotion_note: str = ""
    emotion_direction: EmotionDirection = "flat"
    #: What this segment reaches back to, in one line. Empty when it reaches back to nothing.
    #:
    #: A separate field rather than a sentence inside ``craft``, because the whole point is that
    #: it can be checked. Measured on 《面馆的最后一天》 before this existed: the reading found
    #: every craft move that lived inside one segment and none of the three that spanned
    #: segments — a phrase said twice, a reversal of what the reader had assumed, a moment whose
    #: force was that nobody spoke. Each reading call saw six segments and nothing of what came
    #: before, so there was nothing to reach back *to*.
    callback: str = ""
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered(self):
        if self.paragraph_end < self.paragraph_start:
            raise ValueError("segment paragraph range reversed")
        return self


class ShortFormBeat(M):
    """起承转合. Four, contiguous, covering the piece — the same rule as the whole-book
    breakdown, and for the same reason: 「第 9 段属于哪一幕」 has to have an answer."""

    beat: Literal["起", "承", "转", "合"]
    segment_start: int = Field(ge=1)
    segment_end: int = Field(ge=1)
    title: str = ""
    summary: str = ""

    @model_validator(mode="after")
    def ordered(self):
        if self.segment_end < self.segment_start:
            raise ValueError("beat segment range reversed")
        return self


class RecurringPhrase(M):
    """A wording that comes back, and where it comes back.

    Found by comparing strings across segments rather than by asking the model, because that is
    the one thing here code does better. Given 《面馆的最后一天》 with the whole prior reading
    carried forward and the instruction naming recurrence first, the model reliably caught
    recurring *objects* — the chilli oil, the ten-yuan note, the blue notebook — and missed the
    recurring *line*: 「老规矩」, spoken by two different customers six segments apart, present in
    both segments' beats, identified in neither.
    """

    phrase: str
    #: Segment indices it appears in, ascending. Two is the floor — a wording used once is a
    #: wording, not a motif.
    segments: list[int] = Field(default_factory=list)


class ShortFormResult(M):
    version: str = "1.0"
    availability: Literal["available", "partial", "unavailable"] = "unavailable"

    title: str = ""
    character_count: int = 0
    #: 一句话梗概 — the corpus opens every 甲型 sheet with one.
    one_line: str = ""
    #: The single genre the user picked. Short pieces are not asked for five profile axes.
    genre: str = ""

    beats: list[ShortFormBeat] = Field(default_factory=list)
    segments: list[ShortFormSegment] = Field(default_factory=list)
    #: 上行情绪 / 下行情绪, in the corpus's own two-list form. Each entry names the stage and
    #: what lifts or drops there.
    emotion_up: list[str] = Field(default_factory=list)
    emotion_down: list[str] = Field(default_factory=list)

    #: 反复出现的说法, found by comparison rather than asked for.
    recurring: list[RecurringPhrase] = Field(default_factory=list)
    evidence_index: dict[str, dict] = Field(default_factory=dict)
