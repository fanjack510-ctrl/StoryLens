"""短篇精读: does a whole short piece come out the other side, with nothing dropped?

The failure this file exists to catch is silent. Every column can be filled, every segment can
look right, and paragraphs 5–7 can simply not be in the analysis — because the model numbered a
boundary carelessly and the pipeline believed it. Nothing on the finished page says so. So the
assertions here are about **coverage** first and content second.

The provider is fake and the piece is small, so this costs nothing.
"""

from __future__ import annotations

import json

import pytest

from app.narrative_core.short_form.contracts import ShortFormResult
from app.narrative_core.short_form.dispatch import is_short_form
from app.narrative_core.short_form.pipeline import (
    SEGMENTS_PER_READ_CALL,
    _abutting_beats,
    plan_segments,
    run_short_form,
)

#: A 24-paragraph piece of roughly 9,600 characters — the low end of the human corpus, which
#: runs 9,143 to 19,199 characters.
PARAGRAPHS = [f"第{i}段。" + "他站在门口看着屋里的人，没有说话。" * 22 for i in range(1, 25)]


class _Provider:
    """Answers the three prompts in turn, the way a compliant model would."""

    def __init__(self, *, boundaries: list[int] | None = None) -> None:
        # Paragraph at which each segment ends. Six segments over 24 paragraphs.
        self.boundaries = boundaries or [4, 8, 12, 16, 20, 24]
        self.calls: list[str] = []

    def complete(self, *, payload, max_output_tokens):  # noqa: ANN001 - test double
        instruction = str(payload.get("instruction", ""))
        if "切成若干" in instruction:
            self.calls.append("segment")
            return json.dumps(
                {"segments": [{"paragraph_start": 0, "paragraph_end": b, "why": "地点变了"}
                              for b in self.boundaries]},
                ensure_ascii=False,
            )
        if "拆稿表" in instruction:
            self.calls.append("read")
            return "```json\n" + json.dumps(
                {
                    "segments": [
                        {
                            "index": row["index"],
                            "phase": "陷入危机",
                            "setting": "老屋/女主、债主",
                            "beats": ["债主上门", "她翻出母亲的存折"],
                            "craft": "把坏消息放在她刚以为熬过去的时候，读者的松懈变成了第二次紧张。",
                            "emotion_note": "至暗时刻：看不到出路",
                            "emotion_direction": "down",
                        }
                        for row in payload["segments"]
                    ]
                },
                ensure_ascii=False,
            ) + "\n```"
        self.calls.append("shape")
        return json.dumps(
            {
                "one_line": "她为还清母亲欠下的债，把老屋改成早点铺，最后赎回了母亲的存折",
                "beats": [
                    {"beat": "起", "segment_start": 1, "segment_end": 2, "title": "债主上门", "summary": "开局"},
                    {"beat": "承", "segment_start": 3, "segment_end": 4, "title": "支起早点铺", "summary": "过程"},
                    {"beat": "转", "segment_start": 5, "segment_end": 5, "title": "存折是假的", "summary": "转折"},
                    {"beat": "合", "segment_start": 6, "segment_end": 6, "title": "赎回", "summary": "收束"},
                ],
                "emotion_up": ["第 4 段：第一天卖光了，她笑了"],
                "emotion_down": ["第 1 段：债主上门，为第 4 段的第一次进账积欠"],
            },
            ensure_ascii=False,
        )


@pytest.fixture()
def report():
    return run_short_form(provider=_Provider(), paragraphs=PARAGRAPHS, title="老屋", genre="现实题材")


def test_the_result_validates_and_covers_the_whole_piece(report) -> None:
    result = report.result
    assert isinstance(result, ShortFormResult)
    ShortFormResult.model_validate(result.model_dump())
    assert result.availability == "available"

    covered: set[int] = set()
    for segment in result.segments:
        covered |= set(range(segment.paragraph_start, segment.paragraph_end + 1))
    assert covered == set(range(1, len(PARAGRAPHS) + 1)), "有段落没有进入任何一段"

    # No paragraph analysed twice, either — that inflates whatever it says.
    assert sum(s.paragraph_end - s.paragraph_start + 1 for s in result.segments) == len(PARAGRAPHS)


def test_a_careless_boundary_does_not_lose_the_paragraphs_between(report) -> None:
    """The defect that made this file necessary.

    A model that ends one segment at 4 and starts the next at 8 is not describing a gap; it is
    numbering carelessly. Believing it drops 5–7 out of the analysis, and the report then reads
    as complete because every segment it *does* show is fine.
    """
    spans = plan_segments(
        {"segments": [{"paragraph_start": 1, "paragraph_end": 4},
                      {"paragraph_start": 8, "paragraph_end": 10}]},
        total_paragraphs=14,
    )
    covered: set[int] = set()
    for start, end in spans:
        covered |= set(range(start, end + 1))
    assert covered == set(range(1, 15))
    assert spans[-1][1] == 14, "末尾剩下的段落也必须归入最后一段"


def test_the_four_beats_partition_the_segments() -> None:
    # 「第 11 段属于哪一幕」 must have exactly one answer, whatever the model returns.
    beats = _abutting_beats(
        [
            {"beat": "起", "segment_start": 1, "segment_end": 9},
            {"beat": "承", "segment_start": 9, "segment_end": 12},
            {"beat": "转", "segment_start": 12, "segment_end": 12},
            {"beat": "合", "segment_start": 12, "segment_end": 12},
        ],
        last_segment=12,
    )
    assert [b.beat for b in beats] == ["起", "承", "转", "合"]
    assert beats[0].segment_start == 1 and beats[-1].segment_end == 12
    for earlier, later in zip(beats, beats[1:]):
        assert later.segment_start == earlier.segment_end + 1
        assert earlier.segment_end >= earlier.segment_start


def test_every_segment_carries_the_six_columns(report) -> None:
    """Six, because five is a different product.

    The corpus's template is 分段字数 / 故事进展 / 地点人物 / 事件冲突 / 学习之处 / 情绪. Drop the
    craft column and it is a synopsis; drop the emotion column and it is a plot outline.
    """
    for segment in report.result.segments:
        assert segment.characters > 0, "分段字数由引擎数出来，不该为零"
        assert segment.phase and segment.setting
        assert segment.beats
        assert segment.craft
        assert segment.emotion_note
        assert segment.emotion_direction in ("up", "down", "flat")


def test_the_reading_pass_is_batched_rather_than_one_call_per_segment(report) -> None:
    # One call per segment would cost six times as much on a piece this size for no more
    # information; one call for all of them overruns the output ceiling and truncates the craft
    # notes, which are the longest column.
    provider_calls = report.provider_calls
    expected_read_calls = -(-report.segments_planned // SEGMENTS_PER_READ_CALL)
    assert provider_calls == 1 + expected_read_calls + 1
    assert report.segments_planned == 6


def test_an_empty_piece_says_so_rather_than_calling_the_model() -> None:
    provider = _Provider()
    report = run_short_form(provider=provider, paragraphs=["", "   "], title="空")
    assert provider.calls == []
    assert report.failures == ["EMPTY_TEXT"]
    assert report.result is not None and report.result.availability == "unavailable"


def test_length_alone_does_not_decide_which_pipeline_a_book_gets() -> None:
    """《剩女遇见爱情》 is 194,004 characters in one chapter — a novel whose split failed.

    A chapter-count rule calls it short and reads a whole novel in one sitting. A word-count
    rule calls it long, sends it to an engine that needs chapters, and it produces nothing.
    Requiring both is what separates a short piece from a book we failed to split.
    """
    assert is_short_form(character_count=11_830, chapter_count=0) is True
    assert is_short_form(character_count=11_830, chapter_count=15) is True
    assert is_short_form(character_count=194_004, chapter_count=1) is False
    assert is_short_form(character_count=79_616, chapter_count=0) is False
    assert is_short_form(character_count=147_030, chapter_count=46) is False
    assert is_short_form(character_count=0, chapter_count=0) is False
