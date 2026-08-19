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


def test_the_emotion_stages_survive_whichever_shape_the_model_sends() -> None:
    """A real run returned objects where the instruction asked for strings.

    `str(x)` on a dict is its Python repr, so the report carried
    `"{'segment': '第7段', 'note': '发布会高潮…'}"` onto the page — the same failure as the
    revision note that arrived as prose and was iterated into one-character bullets. A coercion
    that never asks what shape it was handed will eventually be handed the other one.
    """
    from app.narrative_core.short_form.pipeline import _emotion_lines

    assert _emotion_lines([{"segment": "第7段", "note": "发布会高潮，主角掌控全局"}]) == [
        "第7段：发布会高潮，主角掌控全局"
    ]
    assert _emotion_lines(["第 3 段：母亲去世"]) == ["第 3 段：母亲去世"]
    # Half an object is still worth printing; nothing at all is not.
    assert _emotion_lines([{"note": "只有说明"}, {"segment": "第9段"}]) == ["只有说明", "第9段"]
    assert _emotion_lines([None, "", "   ", {}]) == []


def test_an_oversized_segment_is_cut_by_asking_again_not_by_arithmetic() -> None:
    """Half the first real run's text sat in four segments, each getting one craft note.

    《糙汉重生·第一卷》 came back as twenty segments of which four exceeded 2,000 characters and
    between them held **54.6% of the piece** — the largest was 5,046. Every column was filled and
    the page looked right, which is what makes this a quality failure rather than a visible one.

    Bisecting by paragraph count was the cheaper repair and the wrong one: these are meant to be
    scenes, and halving one puts the boundary wherever the arithmetic lands. The model is asked
    again instead, once for all of them together.
    """
    from app.narrative_core.short_form.pipeline import apply_resplits

    paragraphs = ["x" * 400] * 20
    spans = [(1, 4), (5, 16), (17, 20)]
    out = apply_resplits(spans, {"splits": [{"index": 2, "ends": [8, 12]}]}, paragraphs)

    assert out == [(1, 4), (5, 8), (9, 12), (13, 16), (17, 20)]
    covered: set[int] = set()
    for start, end in out:
        covered |= set(range(start, end + 1))
    assert covered == set(range(1, 21))
    assert sum(e - s + 1 for s, e in out) == 20


def test_a_careless_split_point_can_shorten_a_segment_but_never_lose_a_paragraph() -> None:
    # Out of range, negative and duplicated cuts are all things a model returns. None of them
    # may reorder the piece or drop text — the same guarantee the first segmentation pass gives.
    from app.narrative_core.short_form.pipeline import apply_resplits

    paragraphs = ["y" * 300] * 10
    out = apply_resplits([(1, 10)], {"splits": [{"index": 1, "ends": [99, -3, 5, 5]}]}, paragraphs)

    assert out == [(1, 5), (6, 10)]
    # And a model that says the span really is one scene is believed.
    assert apply_resplits([(1, 10)], {"splits": [{"index": 1, "ends": []}]}, paragraphs) == [(1, 10)]


def test_a_cleanly_segmented_piece_pays_for_no_extra_call(report) -> None:
    # The re-split is one call for all oversized spans, or none at all. Charging per oversized
    # segment would make a badly-segmented piece cost several times a well-segmented one for
    # the same reading.
    assert report.segments_resplit == 0
    assert report.provider_calls == 1 + 1 + 1  # segment + one read batch + shape


def test_the_carry_forward_takes_the_words_and_not_a_label() -> None:
    """A phrase said twice is only visible if the phrase itself travels.

    Each reading call used to see six segments and nothing before them, so nothing could recur
    and nothing could be overturned. Measured on 《面馆的最后一天》 before this existed: every
    craft move that lived inside one segment was found, and all three that spanned segments were
    missed.

    Carrying the beats rather than a summary of them is the load-bearing part. 「老规矩」 is
    three characters inside one beat; a digest of phases — 「陷入危机」, 「至暗时刻」 — would show
    the shape of the arc and carry none of them.
    """
    from app.narrative_core.short_form.contracts import ShortFormSegment
    from app.narrative_core.short_form.pipeline import CARRY_MAX_SEGMENTS, carry_digest

    segments = [
        ShortFormSegment(
            index=i,
            paragraph_start=i,
            paragraph_end=i,
            characters=500,
            phase="陷入危机",
            beats=["老顾客说了一句老规矩", "她愣住了"],
            emotion_note="至暗时刻",
        )
        for i in range(1, 4)
    ]
    digest = carry_digest(segments)

    assert len(digest) == 3
    assert "老规矩" in digest[0]["beats"][0], "原话没有随前文传下去，重复就无从被发现"
    assert digest[0]["phase"] == "陷入危机"
    assert digest[0]["emotion"] == "至暗时刻"


def test_the_carry_forward_is_bounded_but_not_a_short_window() -> None:
    """Bounded so a long piece cannot inflate every call; wide enough to be worth having.

    A motif reaches back as far as it reaches. 《面馆的最后一天》 says 「老规矩」 in one segment
    and again six later — a window sized to the reading batch would have missed it by exactly
    that margin.
    """
    from app.narrative_core.short_form.contracts import ShortFormSegment
    from app.narrative_core.short_form.pipeline import (
        CARRY_MAX_SEGMENTS,
        SEGMENTS_PER_READ_CALL,
        carry_digest,
    )

    assert CARRY_MAX_SEGMENTS > SEGMENTS_PER_READ_CALL * 2

    many = [
        ShortFormSegment(index=i, paragraph_start=i, paragraph_end=i, characters=100)
        for i in range(1, CARRY_MAX_SEGMENTS + 20)
    ]
    digest = carry_digest(many)
    assert len(digest) == CARRY_MAX_SEGMENTS
    # The most recent, not the oldest: what a segment reaches back to is usually nearby.
    assert digest[-1]["index"] == many[-1].index


def test_a_wording_that_comes_back_is_found_by_comparison_not_by_asking() -> None:
    """The one thing here a loop does better than a model.

    《面馆的最后一天》 says 「老规矩」 twice, six segments apart. The reading missed it with the
    whole prior reading carried forward, with the instruction naming recurrence first, and with
    the phrase present in both segments' beats. Recurring *objects* it caught; a recurring *line*
    it did not.
    """
    from app.narrative_core.short_form.recurrence import find_recurrences

    texts = {
        1: "老顾客推门进来，说老规矩。她照着下了一碗面。" + "他坐在窗边看报纸。" * 6,
        2: "她翻着母亲的账本，一页一页往后看。" * 8,
        3: "老太太拄着拐进来，说老规矩啊。她愣住了。" + "外面下着雨。" * 8,
    }
    found = find_recurrences(texts)

    # `contains` rather than equals: when both occurrences share an adjacent word the longer
    # string wins the subsumption, and 「说老规矩」 is the same finding. On the real story the two
    # occurrences differ — 要老规矩 and 说「老规矩」 — and the bare phrase comes out.
    hit = next((r for r in found if "老规矩" in r.phrase), None)
    assert hit is not None, [r.phrase for r in found]
    assert hit.segments == (1, 3)


def test_the_story_is_the_baseline_so_common_constructions_do_not_win() -> None:
    """Ranked by how unusual the characters are *here*, not by how often the phrase returns.

    There is no Chinese frequency corpus in this repo and none is needed. Ranking by frequency
    surfaced 「了很久」, 「在桌上」, 「没说话」 — constructions that came back in a third of the
    segments and mean nothing — and buried the motif that came back twice.
    """
    from app.narrative_core.short_form.recurrence import find_recurrences

    common = "他站了很久，没说话，把东西放在桌上。"
    texts = {
        1: common + "老板娘端出一碗牛肉面。" + "外面天黑了。" * 5,
        2: common + "他又站了很久。" + "屋里很安静。" * 6,
        3: "老板娘擦着桌子。" + common + "雨一直下。" * 5,
    }
    ranked = [r.phrase for r in find_recurrences(texts)]

    assert ranked, "什么都没找到"
    assert any("老板娘" in p for p in ranked[:3]), ranked
    # The construction may appear, but never above the distinctive noun.
    if "了很久" in ranked:
        assert ranked.index("了很久") > min(i for i, p in enumerate(ranked) if "老板娘" in p)


def test_fragments_of_one_phrase_are_reported_once() -> None:
    # 「湖北省黄冈市」 generates 「黄冈市」, 「省黄冈市」, 「北省黄冈市」 … all returning in the same
    # two segments. Seven rows for one finding is a concordance, not a reading.
    from app.narrative_core.short_form.recurrence import find_recurrences

    texts = {
        1: "收款人赵建军，地址湖北省黄冈市浠水县。" + "她把单子收好。" * 6,
        2: "她又看了一遍湖北省黄冈市那几个字。" + "外面很冷。" * 6,
    }
    found = [r.phrase for r in find_recurrences(texts)]

    address = [p for p in found if "黄冈" in p]
    assert len(address) == 1, address


def test_a_wording_in_most_of_the_piece_is_furniture() -> None:
    """Telling a motif from a name is the hard part, and coverage is the separation used.

    「母亲」 recurs in nearly every segment of this story and is not a motif; it is who the story
    is about. A wording in two or three segments is a callback; one in nearly all of them is the
    furniture.
    """
    from app.narrative_core.short_form.recurrence import find_recurrences

    texts = {i: f"母亲在面馆里忙着，她把碗摞起来。这是第{i}段的事情。" for i in range(1, 11)}
    found = [r.phrase for r in find_recurrences(texts)]

    assert not any("母亲" in p for p in found), found


def test_re_reading_a_piece_keeps_the_boundaries_it_already_had() -> None:
    """One boundary moving renumbers every segment after it, and callbacks cite segment numbers.

    Measured across three runs of the same 8,577-character story: thirteen boundaries came back
    identical every time, and all the disagreement sat in one stretch where the prose genuinely
    has no clean scene break. That is the text, not unreliability — but a second reading that
    re-cut the piece would silently invalidate every reference the first one wrote.

    Reusing also skips the segmentation and the re-split, so a second reading costs two calls
    fewer.
    """
    provider = _Provider()
    spans = [(1, 6), (7, 12), (13, 18), (19, 24)]
    report = run_short_form(
        provider=provider, paragraphs=PARAGRAPHS, title="老屋", reuse_spans=spans
    )

    assert report.spans_reused is True
    assert [(s.paragraph_start, s.paragraph_end) for s in report.result.segments] == spans
    assert "segment" not in provider.calls and "resplit" not in provider.calls
    assert provider.calls == ["read", "shape"]


def test_boundaries_from_a_text_that_has_since_changed_are_not_reused() -> None:
    """Stale boundaries cite paragraphs that have moved.

    Every segment would be a window onto the wrong prose while looking entirely normal — the
    columns fill, the counts add up, and the analysis is about a different passage than the one
    it names.
    """
    provider = _Provider()
    report = run_short_form(
        provider=provider,
        paragraphs=PARAGRAPHS,
        reuse_spans=[(1, 6), (7, 12)],  # only 12 of 24 paragraphs
    )

    assert report.spans_reused is False
    assert "segment" in provider.calls


def test_a_callback_that_cites_a_segment_that_cannot_exist_is_dropped() -> None:
    """A citation to nothing looks exactly like a finding on the page.

    Pointing forward is not a callback, and pointing past the end of the piece is a reference to
    a segment nobody can turn to. Both were possible and neither was checked.
    """
    from app.narrative_core.short_form.pipeline import _checked_callback

    assert _checked_callback("呼应第 2 段的账本", index=5, known=20) == "呼应第 2 段的账本"
    assert _checked_callback("呼应第 9 段的十块钱", index=5, known=20) == ""
    assert _checked_callback("呼应第 99 段", index=5, known=20) == ""
    # Naming no segment is a legitimate way to say it, and there is nothing to verify.
    assert _checked_callback("呼应开头的价目表", index=5, known=20) == "呼应开头的价目表"
    assert _checked_callback("", index=5, known=20) == ""


def test_a_callback_with_a_right_number_and_an_invented_claim_is_dropped() -> None:
    """The segment number was already checked. What it says about that segment was not.

    Measured on 《面馆的最后一天》: of sixteen callbacks the reading produced, fifteen were sound
    and one said 「呼应第12段夹克男欠账」 — a segment that is 寻找赵建军未果 and contains no jacket
    and no debt. A correct number carrying an invented claim, printed identically to a real
    finding. It was the only one of the sixteen with no rare character in common with the segment
    it cited; the next lowest matched one of five and was half right, so the threshold is zero.
    """
    from app.narrative_core.short_form.recurrence import names_something_in

    found = "赵建军的汇款单压在蓝色塑料皮的账本下面，母亲翻了很久。"
    absent = "第二天我去找赵建军，敲门没人应，楼道里堆着纸箱，我等了很久就走了。"
    # Long enough to have a vocabulary. Under about four hundred characters a character used
    # once is still a large share of the text, nothing counts as rare, and the check abstains.
    whole = (
        "母亲把辣椒油端上桌，母亲说老规矩。我在店里等母亲，母亲没说话。"
        + found
        + absent
        + "我在店里坐了很久，看着门外的雨，没有客人进来。母亲在里面洗碗，水声一直响着。"
        + "后来我把桌子擦了一遍又一遍，把凳子摆好，把灯关了一盏。天黑得很慢。"
        + "我想着要不要跟母亲说，想了很久还是没有说出来，就那样坐到了天亮。"
        + "第二天早上母亲照常开门，照常把水烧上，照常把面下进锅里，什么也没有问我。"
        # Distinct filler, not a repeat: repeating the same prose scales counts and length
        # together and leaves every share exactly where it was.
        "巷口的修车铺换了招牌，卖水果的换成了卖手机壳的，只有我们这家还挂着从前的木牌子。"
        "对面新开的连锁店贴着彩色海报，晚上亮到十二点，隔着马路能听见里面放歌。"
        "父亲走的那年冬天特别冷，管道冻裂过一次，师傅来修了整整一个下午才通。"
        "我小时候在这条街上学骑自行车，摔在拐角的水泥台阶上，膝盖留下一道疤到现在。"
        "老顾客里有个退休的教师，每周三来一次，坐靠窗那张桌子，从不加醋。"
    )

    assert names_something_in("呼应第 6 段的汇款单", found, whole_text=whole) is True
    assert names_something_in("呼应第 12 段夹克男欠账", absent, whole_text=whole) is False
    # Half right is kept. 「呼应第13段存根和磨损的碗」 named two things and only the bowls were
    # in that segment; a fractional threshold would have taken it, and it was a real finding.
    assert names_something_in("呼应第 6 段的汇款单和夹克男", found, whole_text=whole) is True
    # 呼应/第/段 are absent from every story and would otherwise score as maximally rare,
    # failing every callback including the true ones.
    assert names_something_in("呼应第 6 段", found, whole_text=whole) is True
