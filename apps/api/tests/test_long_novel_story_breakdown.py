"""拆文 — the second reading, and the rules that keep it from becoming the first one again.

A diagnostic report answers "where is this book weak". This answers "why did it land, and
what can I take". The two share a snapshot, a planner and an extraction pass; above L1 they
have nothing in common, and the design (docs/whole-book/STORY_BREAKDOWN_DESIGN) writes down
three invariants because each has a matching failure already on record in the diagnostic:

  * no numeric score anywhere,
  * every claim quotable back to the prose,
  * moments chosen, never allotted one per act.

The provider here is a queue of canned answers, so the whole path runs for free — including
the case that matters most, a model that returns a quotation it made up.
"""

from __future__ import annotations

import json

import pytest

from app.narrative_core.long_novel.budget import ContextCosts, joint_resolve
from app.narrative_core.long_novel.contracts.density import profile
from app.narrative_core.long_novel.extractor import (
    BlockExtractor,
    SourceChapter,
    SourceParagraph,
)
from app.narrative_core.long_novel.orchestrator import RunCoordinator
from app.narrative_core.long_novel.planner import BlockPlanner, PlannedChapter
from app.narrative_core.long_novel.prompts import prompt_template_hash
from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2

CHAPTERS = 96
PARAGRAPHS = 21
COSTS = ContextCosts(3_000, 1_200, 1_800, 400)
LEAD = "老王"

#: The sentence every paragraph of the fake book ends on.
LINE = "老王走进房间。"


def real_quote(chapter: int) -> str:
    """A line that is genuinely in that chapter, and different from every other chapter's.

    Distinct on purpose: nominations are deduplicated by quote, so a fixture that nominated
    one line everywhere would collapse to a single candidate and the selection this file is
    supposed to exercise would never happen.
    """
    return "第%d章第1段，%s" % (chapter, LINE)


#: One the model invented. Reads like the book, appears nowhere in it — which is the failure
#: a breakdown cannot survive, because its whole claim is that the reader can turn to the page.
FAKE_QUOTE = "老王站在门口久久没有动。"


def _asset(refs, first):
    return {
        "chapter_signals": [
            {
                "chapter_ref": ref,
                "dialogue_paragraphs": 6 + ref % 5,
                "action_paragraphs": 3 + ref % 3,
                "interiority_paragraphs": 1 + ref % 4,
                "scene_breaks": 1,
                "new_information_beats": 1 + ref % 4,
                "hook_present": ref % 2 == 0,
                # 拆文 delta: the question this chapter leaves, in its own words.
                "end_hook_question": ("卷宗到底在谁手上？" if ref % 2 == 0 else ""),
                "evidence": [{"paragraph_ref": first}],
            }
            for ref in refs
        ],
        "events": [
            {"summary": "第%d章的关键事件" % ref, "actors": [LEAD], "chapter_ref": ref,
             "evidence": [{"paragraph_ref": first}]}
            for ref in refs
        ],
        "character_state_changes": [],
        "goal_changes": [],
        "choices": [],
        "causal_links": [],
        "suspense_threads": [
            {"question": "第%d章埋下的疑问" % refs[0], "opened_chapter_ref": refs[0],
             "evidence": [{"paragraph_ref": first}]}
        ],
        "suspense_actions": [
            {"thread_ref": "第%d章埋下的疑问" % refs[0], "action_kind": "reveal",
             "information_added": "揭示", "chapter_ref": refs[0],
             "evidence": [{"paragraph_ref": first}]}
        ],
        "relationship_changes": [
            {"from_entity_ref": LEAD, "to_entity_ref": "小陈", "relation": "同事",
             "evidence": [{"paragraph_ref": first}]}
        ],
        "mentions": [
            {"surface_norm": LEAD, "paragraph_ref": first,
             "evidence": [{"paragraph_ref": first}]},
        ],
        "provisional_entities": [
            {"member_mention_indexes": [0], "display_surface_norm": LEAD},
        ],
        # Two nominations per block: one real, one fabricated. The fabricated one must not
        # reach the document, and it must not take the real one down with it.
        "standout_moments": [
            {"chapter_ref": refs[0], "quote": real_quote(refs[0]), "why": "第一次正面出现",
             "evidence": [{"paragraph_ref": first}]},
            {"chapter_ref": refs[0], "quote": FAKE_QUOTE, "why": "听起来很像",
             "evidence": [{"paragraph_ref": first}]},
        ],
    }


class _FakeProvider:
    def complete(self, *, payload, max_output_tokens, repair_note=None):
        text = str(payload["text"])
        refs = [
            int(line.split("第")[1].split("章")[0].strip())
            for line in text.splitlines()
            if line.startswith("=== 第")
        ]
        first = int(text.split("[p:")[1].split("]")[0])
        body = json.dumps(_asset(refs, first), ensure_ascii=False)
        return "```json\n" + body + "\n```", "stop", 900


SEEN: dict[str, object] = {}


def _stage(stage):
    seq = stage["stage_seq"]
    return {"stage_seq": seq, "title": "第%d幕" % (seq + 1), "summary": "阶段概述",
            "stage_goal": "查清卷宗", "core_conflict": "对立", "major_choice": "交出去",
            "protagonist_state": "半信半疑", "key_events": ["交接"],
            "turning_point": "档案室失火", "ending_state": "中断", "next_question": "谁动了卷宗"}


def _beats(payload):
    SEEN["beats_input"] = payload
    return {"four_beats": [
        {"beat": b, "title": "第%d段发生的事" % i, "summary": "经过",
         "chapter_start": i * 24 + 1, "chapter_end": (i + 1) * 24}
        for i, b in enumerate(("起", "承", "转", "合"))
    ]}


def _moments(candidates):
    SEEN["moment_candidates"] = candidates
    picked = [
        {"rank": i + 1, "title": "第%d个瞬间" % (i + 1), "quote": row["quote"],
         "why_it_lands": "身份倒转，读者第一次看清他", "chapter": row["chapter"]}
        for i, row in enumerate(candidates[:9])
    ]
    # A tenth the selector wrote itself. L1 never nominated it, so it never passed the
    # verbatim check against the book — and it must not slip through one layer later.
    picked.append({"rank": 10, "title": "自己编的", "quote": FAKE_QUOTE,
                   "why_it_lands": "听起来不错", "chapter": 1})
    return {"count_rationale": "只有九个真正站得住", "standout_moments": picked}


def _cast(payload):
    SEEN["cast_input"] = payload
    return {
        "supporting_cast": [
            {"name": "小陈", "function": "主角的对照面——他选了安稳，主角选了追查"},
            # A row the model should not have written: it says so itself. Filtered rather than
            # printed, because a cast list padded with people who never appear is what a
            # professional reader caught in the diagnostic's character table.
            {"name": "某某", "function": "未出场，无明确功能"},
        ],
        "cast_note": "都很克制，做完各自那件事就退场",
    }


def _techniques(payload):
    SEEN["technique_input"] = payload
    return {"reusable_techniques": [
        {"name": "把一句谎话重复到所有人都知道",
         "what_it_is": "同一个借口在三处被不同的人问起",
         "why_it_works": "读者比角色先知道，等待她自己承认",
         "transfers_to": "任何有身份差距的故事"}
    ]}


@pytest.fixture(scope="module")
def document() -> dict:
    resolution = joint_resolve(
        context_window=128_000, provider_max_output_tokens=32_768,
        provider_max_output_tokens_source="probed", costs=COSTS,
        mean_chapter_tokens=4_041, mean_paragraphs_per_chapter=PARAGRAPHS,
    )
    prof = profile(resolution.density_profile)
    plan = BlockPlanner(
        profile=prof, output_budget=resolution.output_budget,
        context_window=128_000, costs=COSTS,
    ).plan([
        PlannedChapter(i, 10_000 + i, "h%d" % i, 4_041, PARAGRAPHS)
        for i in range(1, CHAPTERS + 1)
    ])
    sources = {
        i: SourceChapter(
            chapter_order=i, source_chapter_id=10_000 + i, content_hash="h%d" % i,
            snapshot_chapter_id=10_000 + i,
            paragraphs=[
                SourceParagraph(j, "第%d章第%d段，%s" % (i, j, LINE), "c%dp%d" % (i, j))
                for j in range(1, PARAGRAPHS + 1)
            ],
        )
        for i in range(1, CHAPTERS + 1)
    }
    coordinator = RunCoordinator(
        extractor=BlockExtractor(
            provider=_FakeProvider(), profile=prof,
            output_budget=resolution.output_budget,
            prompt_template_hash=prompt_template_hash(prof),
        ),
        profile=prof,
        stage_interpreter=_stage,
        # Every diagnostic unit absent, exactly as the 拆文 mode passes them.
        beat_shaper=_beats,
        moment_selector=_moments,
        cast_reader=_cast,
        technique_reader=_techniques,
    )
    report = coordinator.run(
        plan=plan, chapters_by_order=sources, character_count=100_000,
        book_id=1, snapshot_id=1, revision_hash="rev", title="测试书", run_id=1,
        provider_name="fake", model_name="fake",
        profile_axes={"audience": "female_romance", "engine": "romance"},
    )
    assert not report.blocks_failed, report.blocks_failed
    return report.document


def test_the_document_still_validates(document):
    WholeBookAnalysisV2.model_validate(document)


def test_every_breakdown_section_has_content(document):
    b = document["story_breakdown"]
    assert b["availability"] == "available"
    for key in ("four_beats", "standout_moments", "chapter_hooks",
                "reusable_techniques", "supporting_cast"):
        assert b[key], "%s 是空的" % key


def test_the_four_beats_are_four_and_cover_the_book(document):
    beats = document["story_breakdown"]["four_beats"]
    assert [b["beat"] for b in beats] == ["起", "承", "转", "合"]
    assert beats[0]["chapter_start"] == 1
    assert beats[-1]["chapter_end"] == CHAPTERS
    for earlier, later in zip(beats, beats[1:]):
        assert later["chapter_start"] == earlier["chapter_end"] + 1, beats


def test_an_invented_quotation_never_reaches_the_report(document):
    """The one failure a breakdown cannot survive, blocked at both layers it can enter.

    L1 checks each nomination against the block's own text; the selector may then only choose
    from what L1 nominated. A model asked for a memorable line will write one that sounds like
    the book — and a breakdown whose quotations are paraphrases is worse than one with none,
    because the reader who turns to the page is the reader who finds out.
    """
    moments = document["story_breakdown"]["standout_moments"]
    assert moments, "一条爆点都没有"
    assert all(m["quote"] != FAKE_QUOTE for m in moments), moments
    assert all(m["quote"].startswith("第") and m["quote"].endswith(LINE) for m in moments)
    # And the fabrication did not take its honest sibling down with it.
    candidates = SEEN["moment_candidates"]
    assert all(c["quote"] != FAKE_QUOTE for c in candidates)
    assert len(candidates) >= 8, "候选只有 %d 条，选不出什么" % len(candidates)


def test_the_moment_count_is_the_engines_own_and_it_says_why(document):
    b = document["story_breakdown"]
    assert b["moment_count_rationale"], "没有说明为什么是这个数"
    # The invented tenth is gone; nothing padded the list back to a round number, which is
    # exactly what the design forbids.
    assert len(b["standout_moments"]) == 9


def test_the_chapter_hooks_are_questions_in_the_books_own_words(document):
    hooks = document["story_breakdown"]["chapter_hooks"]
    assert hooks
    assert all(h["question"].endswith(("？", "?")) for h in hooks), hooks[:3]
    assert [h["chapter"] for h in hooks] == sorted(h["chapter"] for h in hooks)
    # Only the chapters that actually left a question, not one row per chapter.
    assert len(hooks) < CHAPTERS


def test_the_breakdown_carries_no_score_anywhere(document):
    """INV-B1. A judgement this reading cannot state in words is one it has not made."""
    allowed = {"rank", "chapter", "chapter_start", "chapter_end"}

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
                assert not (numeric and key not in allowed), "%s.%s 是个分数" % (path, key)
                walk(value, path + "." + key)
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(document["story_breakdown"], "story_breakdown")


def test_a_diagnostic_run_leaves_the_breakdown_honestly_absent():
    """Absent because it was not read, which is not the same as nothing being worth quoting."""
    from app.narrative_core.long_novel.adapter import to_whole_book_v2

    doc = to_whole_book_v2(
        book_id=1, snapshot_id=1, revision_hash="r", title="t", chapter_count=1,
        character_count=1, run_id=1, provider_name="p", model_name="m",
        real_provider_calls=1,
        pacing={"availability": "unavailable", "points": [], "event_markers": [],
                "pacing_regions": []},
        chapters={"availability": "unavailable", "functions": [], "heatmap": []},
    )
    assert doc["story_breakdown"]["availability"] == "unavailable"
    assert doc["story_breakdown"]["standout_moments"] == []
    WholeBookAnalysisV2.model_validate(doc)


def test_a_character_who_never_appears_is_not_in_the_cast(document):
    """「未出场，无明确功能」 is not a function, it is the model saying the row is a mistake."""
    cast = document["story_breakdown"]["supporting_cast"]
    assert cast, "配角为空"
    assert all("未出场" not in x["function"] for x in cast), cast
    assert [x["name"] for x in cast] == ["小陈"]


def test_the_cast_is_judged_once_as_a_whole_not_certified_one_by_one(document):
    """A per-character  came back true for all twenty-three on the real run.

    A flag that cannot come out false is the heatmap's hard-coded zero wearing a boolean, so
    the question moved to where it can actually be answered: one line about the cast.
    """
    b = document["story_breakdown"]
    assert b["cast_note"], "没有对整批配角的判断"
    assert all("stays_in_lane" not in x for x in b["supporting_cast"])

