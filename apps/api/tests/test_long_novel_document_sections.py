"""Every page the product renders must come out of a run with something on it.

This is the regression guard for a failure that unit tests cannot see and that a run report
actively hides. Each layer was correct in isolation, every call succeeded, coverage read
100% — and the whole-book screen showed twenty populated sections and seventeen empty ones,
because results were assembled and then not carried across. Counting provider calls says
nothing about that; only looking at the finished document does.

So the assertions here are about the *document*, not the pipeline: does this section have
rows, and do the columns inside those rows say anything. Both questions are needed. The
storyline page can have twenty-four rows and still read as blank if every `participants`
list is empty, and a pacing curve can have ninety-six points that are all the same number.

The provider is fake and the book is small, so this costs nothing and runs in about a
second. That is deliberate: each defect it pins was found by paying for a full 806-chapter
run first.
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

#: Long enough to be read in twelve blocks, which is the size where the whole-book layers used
#: to collapse: twelve blocks gave two Reduction Partitions and therefore one Narrative Stage,
#: and every layer above L1 is sized in stages. At 32 chapters the fixture was read in four
#: blocks and never entered that regime, so a run whose 全书总览 covered only its opening
#: passed this file cleanly. It is also close to the book the defect was measured on
#: (《系统豪横》, 84 chapters in 11 blocks).
CHAPTERS = 96
PARAGRAPHS = 21
COSTS = ContextCosts(3_000, 1_200, 1_800, 400)
LEAD = "老王"


def _block_response(payload):
    """A block asset in the shape a real response takes, including its awkward parts.

    Fenced in markdown and missing optional containers, because real responses are; every
    counter populated, because a response that zeroes them all is now rejected; and the
    suspense actions deliberately varied, because an extraction that returns only "advance"
    leaves the entire suspense tab empty and that shipped once.
    """
    text = str(payload["text"])
    refs = [
        int(line.split("第")[1].split("章")[0].strip())
        for line in text.splitlines()
        if line.startswith("=== 第")
    ]
    first = int(text.split("[p:")[1].split("]")[0])
    asset = {
        "chapter_signals": [
            {
                "chapter_ref": ref,
                "dialogue_paragraphs": 6 + ref % 5,
                "action_paragraphs": 3 + ref % 3,
                # Varied, not constant. Held at 2 it made the 情绪浓度 curve a flat line, which
                # is the exact shape this file exists to reject — the check only reached it once
                # the chart stopped being dominated by a composite curve.
                "interiority_paragraphs": 1 + ref % 4,
                "scene_breaks": 1,
                "new_information_beats": 1 + ref % 4,
                "hook_present": ref % 2 == 0,
                "evidence": [{"paragraph_ref": first}],
            }
            for ref in refs
        ],
        "events": [
            {
                "summary": "第%d章的关键事件" % ref,
                "actors": [LEAD, "小陈"],
                "chapter_ref": ref,
                "evidence": [{"paragraph_ref": first}],
            }
            for ref in refs
        ],
        "character_state_changes": [
            {
                "entity_ref": LEAD,
                "from_state": "在职",
                "to_state": "辞职",
                "chapter_ref": refs[0],
                "evidence": [{"paragraph_ref": first}],
            }
        ],
        "goal_changes": [
            {
                "entity_ref": LEAD,
                "goal_text": "查清第%d章的事" % refs[0],
                "change_kind": "formed",
                "evidence": [{"paragraph_ref": first}],
            }
        ],
        "choices": [
            {
                "entity_ref": LEAD,
                "decision": "留下卷宗",
                "costs": ["失去职位"],
                "gains": ["保住线索"],
                "evidence": [{"paragraph_ref": first}],
            }
        ],
        "causal_links": [
            {
                "cause_fact_ref": "第%d章的关键事件" % ref,
                "effect_fact_ref": "第%d章的关键事件" % (ref + 1),
                "evidence": [{"paragraph_ref": first}],
            }
            for ref in refs[:2]
        ],
        "suspense_threads": [
            {
                "question": "第%d章埋下的疑问" % refs[0],
                "opened_chapter_ref": refs[0],
                "evidence": [{"paragraph_ref": first}],
            }
        ],
        "suspense_actions": [
            {
                "thread_ref": "第%d章埋下的疑问" % refs[0],
                "action_kind": kind,
                "information_added": "%s 带来的信息" % kind,
                "chapter_ref": ref,
                "evidence": [{"paragraph_ref": first}],
            }
            for kind, ref in zip(("advance", "partial", "reveal", "twist", "resolve"), refs)
        ],
        "relationship_changes": [
            {
                "from_entity_ref": LEAD,
                "to_entity_ref": "小陈",
                "relation": "同事",
                "evidence": [{"paragraph_ref": first}],
            }
        ],
        "mentions": [
            {"surface_norm": LEAD, "paragraph_ref": first,
             "evidence": [{"paragraph_ref": first}]}
        ],
        "provisional_entities": [
            {"member_mention_indexes": [0], "display_surface_norm": LEAD}
        ],
    }
    return "```json\n" + json.dumps(asset, ensure_ascii=False) + "\n```", "stop", 900


class _FakeProvider:
    def complete(self, *, payload, max_output_tokens, repair_note=None):
        return _block_response(payload)


#: What each upper layer was actually handed. The document alone cannot show this: a report
#: assembled from the first act and a report assembled from the whole book are the same shape,
#: and the difference is only visible in what the layer was given to read.
SEEN: dict[str, object] = {}


def _stage(stage):
    SEEN.setdefault("stages", []).append(stage)  # type: ignore[union-attr]
    seq = stage["stage_seq"]
    return {
        "stage_seq": seq,
        "title": "第%d幕" % (seq + 1),
        "summary": "阶段概述",
        "stage_goal": "查清卷宗的去向",
        "core_conflict": "新旧主任的对立",
        "major_choice": "把卷宗交出去",
        "protagonist_state": "半信半疑",
        "key_events": ["交接", "追查"],
        "turning_point": "档案室失火",
        "ending_state": "线索中断",
        "next_question": "谁动了卷宗",
    }


def _topic(topic, payload):
    SEEN.setdefault("topics", {})[topic.value] = payload  # type: ignore[index]
    return {
        "summary": "%s 综合结论" % topic.value,
        "structure_stages": [],
        "lifecycles": [],
        "claims": [],
    }


def _assessment(payload):
    SEEN["assessment"] = payload
    return {
        "overall_summary": "总评",
        "dimensions": [{"dimension": "pacing", "rating": "B", "conclusion": "尚可"}],
        "strengths": [
            {"title": "开篇", "why_good": "钩子扎实", "chapter_start": 1, "chapter_end": 4}
        ],
        "issues": [
            {"issue_id": "I1", "priority": "P1", "category": "节奏", "symptom": "中段偏缓",
             "root_cause": "支线过多", "reader_impact": "弃读", "possible_direction": "压缩",
             "chapter_start": 10, "chapter_end": 20}
        ],
        "revision_priorities": [
            {"chapter_ranges": [[10, 20]], "direction": "压缩中段", "preserve": ["主线"]}
        ],
        "preserve_list": ["开篇的悬念铺设"],
    }


def _final(payload):
    SEEN["final"] = payload
    return {
        "one_sentence_story": "一个交接与追查的故事。",
        "protagonist": LEAD,
        "full_summary": "梗概",
        "initial_state": "在职",
        "final_state": "辞职",
        "core_goal": "查清卷宗",
        "core_conflict": "新旧主任的对立",
        "core_question": "谁动了卷宗",
        "major_storylines": ["卷宗线"],
        "major_suspense": ["卷宗去向"],
        "final_climax": "档案室对峙",
        "ending_resolution": ["卷宗归档"],
        "ending_open_questions": ["谁下的令"],
        "story_skeleton": ["起", "承", "转", "合"],
        "primary_genre": "悬疑",
        "secondary_genres": ["职场"],
        "narrative_drivers": ["秘密的逐步揭开"],
        "narrative_traits": ["多线并进"],
    }


@pytest.fixture(scope="module")
def document() -> dict:
    resolution = joint_resolve(
        context_window=128_000,
        provider_max_output_tokens=32_768,
        provider_max_output_tokens_source="probed",
        costs=COSTS,
        mean_chapter_tokens=4_041,
        mean_paragraphs_per_chapter=PARAGRAPHS,
    )
    prof = profile(resolution.density_profile)
    plan = BlockPlanner(
        profile=prof,
        output_budget=resolution.output_budget,
        context_window=128_000,
        costs=COSTS,
    ).plan(
        [
            PlannedChapter(i, 10_000 + i, "h%d" % i, 4_041, PARAGRAPHS)
            for i in range(1, CHAPTERS + 1)
        ]
    )
    sources = {
        i: SourceChapter(
            chapter_order=i,
            source_chapter_id=10_000 + i,
            content_hash="h%d" % i,
            snapshot_chapter_id=10_000 + i,
            paragraphs=[
                SourceParagraph(j, "第%d章第%d段，老王走进房间。" % (i, j), "c%dp%d" % (i, j))
                for j in range(1, PARAGRAPHS + 1)
            ],
        )
        for i in range(1, CHAPTERS + 1)
    }
    coordinator = RunCoordinator(
        extractor=BlockExtractor(
            provider=_FakeProvider(),
            profile=prof,
            output_budget=resolution.output_budget,
            prompt_template_hash=prompt_template_hash(prof),
        ),
        profile=prof,
        stage_interpreter=_stage,
        topic_synthesizer=_topic,
        assessor=_assessment,
        finaliser=_final,
    )
    report = coordinator.run(
        plan=plan,
        chapters_by_order=sources,
        character_count=100_000,
        book_id=1,
        snapshot_id=1,
        revision_hash="rev",
        title="测试书",
        run_id=1,
        provider_name="fake",
        model_name="fake",
    )
    assert not report.blocks_failed, report.blocks_failed
    assert not report.chapters_lost, report.chapters_lost
    return report.document


def test_the_document_validates_against_the_product_contract(document):
    WholeBookAnalysisV2.model_validate(document)


#: Section → path to the list the page renders. A section that regresses to empty is a page
#: that regresses to blank, which is the exact defect this file exists to catch.
SECTIONS = {
    "作品画像·叙事驱动力": ["type_profile", "narrative_drivers"],
    "总览·目标演变": ["overview", "goal_evolution"],
    "总览·关键转折": ["overview", "major_turning_points"],
    "故事·阶段结构": ["story", "structure_stages"],
    "故事·主线支线": ["story", "storylines"],
    "故事·因果链": ["story", "causal_chain"],
    "故事·时间线": ["story", "chronology"],
    "主角·阶段历程": ["characters", "protagonist", "stages"],
    "主角·地位轨迹": ["characters", "protagonist", "external_status_track"],
    "人物·主要人物": ["characters", "major_characters"],
    "人物·关系网": ["characters", "relationships"],
    "悬念·生命周期": ["suspense", "lifecycles"],
    "节奏·曲线": ["pacing", "points"],
    "节奏·事件标记": ["pacing", "event_markers"],
    "章节·功能": ["chapters", "functions"],
    "章节·热力图": ["chapters", "heatmap"],
    "诊断·修改优先级": ["assessment", "revision_priorities"],
    "诊断·保留清单": ["assessment", "preserve_list"],
    "证据索引": ["evidence_index"],
}


@pytest.mark.parametrize("label", sorted(SECTIONS))
def test_every_rendered_section_has_content(document, label):
    node = document
    for step in SECTIONS[label]:
        node = node[step]
    assert node, "%s 是空的：页面会渲染成空白" % label


def test_the_pacing_curve_is_a_reading_and_not_a_flat_line(document):
    """96 identical numbers pass every per-field check and mean nothing on screen.

    A real run published a curve whose 96 bins held 4 distinct values, 72 of them tied at
    the floor, because 87% of chapter signals came back with every counter zero.

    Checks every published curve, not one of them: the chart is now three lines and any of them
    flattening is the same failure. ``reading_drive``, which this used to read, is no longer
    published — it was the sum of two of the lines beside it.

    ``hook_density`` is held to two values rather than three, and that is not a weaker check but
    a different quantity: a chapter either ends on a hook or it does not, so while a bin holds
    one chapter the curve is a square wave by construction. Measured on 《系统豪横》: exactly
    two ranks, 17 and 67. It only becomes graded on a book long enough for a bin to hold
    several chapters, which is the same reason the heatmap carries it per ten chapters.
    """
    for key, distinct in (("plot_progress", 3), ("emotion", 3), ("hook_density", 2)):
        values = [point[key] for point in document["pacing"]["points"]]
        assert len(set(values)) >= distinct, "%s 只有 %d 种取值" % (key, len(set(values)))


def test_claims_resolve_to_evidence_that_exists_in_the_index(document):
    """An evidence id resolving to nothing is worse than none: the link goes nowhere."""
    index = document["evidence_index"]
    assert index, "证据索引为空"
    cited = [
        evidence_id
        for row in document["story"]["chronology"]
        for evidence_id in row["evidence"]
    ]
    assert cited, "没有任何结论引用证据"
    assert all(evidence_id in index for evidence_id in cited)


def test_the_protagonist_is_the_most_mentioned_character(document):
    lead = document["characters"]["major_characters"][0]
    assert lead["name"] == LEAD
    assert lead["role"] == "protagonist"


def test_the_suspense_tab_distinguishes_what_each_action_did(document):
    """All-`advance` extraction leaves clues, reveals and twists empty by construction."""
    kinds = {
        event["type"]
        for lifecycle in document["suspense"]["lifecycles"]
        for event in lifecycle["events"]
    }
    assert len(kinds) >= 3, kinds


def test_the_chapter_list_carries_its_own_summaries(document):
    functions = document["chapters"]["functions"]
    assert len(functions) == CHAPTERS
    filled = [row for row in functions if row["summary"]]
    assert len(filled) == CHAPTERS, "只有 %d/%d 章有摘要" % (len(filled), CHAPTERS)


# --------------------------------------------------------------------- 全书层看到的是全书
#
# The failure these pin is the one the section-emptiness tests above cannot see. On
# 《系统豪横》 every section was populated, every call succeeded, 84/84 chapters carried a
# function row — and the 全书总览 described chapters 1 to 11 and stopped. Nothing was empty;
# the layers that write about the whole book had simply never been shown it.


def test_a_medium_book_gets_more_than_one_narrative_stage(document):
    """One stage means one act, and everything above L1 is sized in stages.

    84 chapters read in 11 blocks used to give 2 partitions and therefore a single stage: one
    interpretation call for the whole novel, one turning point, one journey band, and a story
    topic budget of eight events. A book has acts regardless of how few blocks it took to read.
    """
    stages = document["story"]["structure_stages"]
    assert len(stages) >= 3, "%d 章只切出 %d 个阶段" % (CHAPTERS, len(stages))
    assert stages[0]["chapter_start"] == 1
    assert stages[-1]["chapter_end"] == CHAPTERS
    # Contiguous and non-overlapping: a gap is a stretch of book no act accounts for.
    for earlier, later in zip(stages, stages[1:]):
        assert later["chapter_start"] == earlier["chapter_end"] + 1, stages


def test_the_final_synthesis_is_given_what_happened_and_not_only_where(document):
    """Final used to receive four integers per act and be asked to summarise the book.

    The stage interpretations were already paid for and already covered every chapter; they
    were passed to the renderer and to nothing else. So the one call that writes 全书总览 wrote
    it out of the topic digests, and what survives a digest is the opening.
    """
    stages = SEEN["final"]["stages"]  # type: ignore[index]
    assert stages, "final 收到的 stages 是空的"
    assert all(s.get("title") for s in stages), stages
    assert all(s.get("key_events") for s in stages), stages
    # And the same for the assessment, which grades the book on the same evidence.
    assert all(s.get("title") for s in SEEN["assessment"]["stages"])  # type: ignore[index]


def test_the_story_topic_reads_the_whole_book_and_not_its_first_act(document):
    """Top-K by evidence count is a front-loaded selection, because evidence counts tie.

    ``sorted`` is stable, so ties resolve in extraction order and the survivors are the
    earliest blocks. Measured on 《系统豪横》: eight events, all from the first act.
    """
    events = SEEN["topics"]["story"]["events"]  # type: ignore[index]
    chapters = [int(e["chapter_ref"]) for e in events]
    assert chapters, "story 主题没有收到任何事件"
    assert max(chapters) > CHAPTERS * 0.75, (
        "story 主题只读到第 %d 章为止，全书 %d 章" % (max(chapters), CHAPTERS)
    )
    assert min(chapters) <= CHAPTERS * 0.25, chapters


def test_each_stage_interpreter_reads_across_its_stage_not_its_opening(document):
    """``events[:40]`` is a prefix of a list that arrives in block order."""
    for stage in SEEN["stages"]:  # type: ignore[union-attr]
        if stage["event_count"] <= len(stage["events"]):
            continue  # nothing was dropped, so there is no sampling to check
        span = stage["chapter_end_order"] - stage["chapter_start_order"]
        covered = [int(e.split("章")[0].split("第")[-1]) for e in stage["events"] if "第" in e]
        if not covered or span < 2:
            continue
        assert max(covered) - min(covered) > span * 0.5, stage


# ----------------------------------------------------------------- 评审反馈（CHG-107）
#
# Every assertion below names something a professional reader found in the finished report of
# 《系统豪横》 and that no test could have caught, because each defect produced a page that was
# populated, validated and wrong.


def test_the_ledger_reaches_the_end_of_every_stage(document):
    """`events[::step][:8]` claimed to sample a span and delivered its opening.

    With ``step = n // 8`` the stride rounds down, so eight strided picks stop short of the
    end — and at ``n < 16`` the stride is 1 and it degenerates to a plain prefix. Measured on
    《系统豪横》: the 49–64 stage's 做了什么 ended at chapter 57, the 65–84 stage at 78. Every
    act quietly lost its closing chapters.
    """
    ledger = document["journey"].get("ledger") or []
    assert ledger, "行动台账是空的"
    for row in ledger:
        if row["did_total"] <= len(row["did"]):
            continue  # nothing was dropped, so there is nothing to sample
        span = row["chapter_end"] - row["chapter_start"]
        last = max(int(e["chapter"]) for e in row["did"])
        assert last >= row["chapter_end"] - span * 0.25, (
            "第%d-%d章这一段的台账只到第%d章" % (row["chapter_start"], row["chapter_end"], last)
        )


def test_a_relationship_is_not_the_same_string_three_times(document):
    """`relationship_type`, `initial_state` and `evolution[0]` all held the first relation.

    So a pair that changed once was printed three times and the detail panel counted it as a
    step it had not taken.
    """
    rows = document["characters"]["relationships"]
    assert rows, "关系为空"
    for row in rows:
        assert row["initial_state"] not in row["evolution"], row
        assert row["final_state"] not in row["evolution"], row
        if row["initial_state"] == row["final_state"]:
            assert not row["evolution"], "单步关系不应该有演变项：%s" % row


def test_the_heatmap_does_not_publish_columns_nothing_measures(document):
    """伏笔铺设 and 回收兑现 were the literal 0.0 in every run this engine ever produced.

    They also name what the suspense module answers with real lifecycles, so filling them in
    would be a worse second copy of an existing page rather than a new finding.
    """
    for cell in document["chapters"]["heatmap"]:
        assert cell.get("foreshadow") is None, cell
        assert cell.get("payoff") is None, cell


def test_the_pacing_curve_publishes_only_independent_series(document):
    """Six curves from five counters, three of them recombinations of the other three."""
    point = document["pacing"]["points"][0]
    for derived in ("reading_drive", "tension", "pace_speed"):
        assert derived not in point, "%s 是其它曲线的组合，不应再发布" % derived
    # The composite still has to *work* as an internal signal — it is what finds slow stretches.
    assert isinstance(document["pacing"]["pacing_regions"], list)


def test_a_causal_link_does_not_run_backwards(document):
    """「曾昭野报警抓获李山木 → 系统激活」, with the system activating in chapter 1.

    Both sides name an event some block extracted, so where both can be found the chapter
    numbers settle which came first.
    """
    chapters: dict[str, int] = {}
    for row in document["story"]["chronology"]:
        chapters.setdefault(row["description"], row["chapter"])
    for line in document["story"]["causal_chain"]:
        cause, _, effect = line.partition(" → ")
        assert cause != effect, "因果两端是同一件事：%s" % line
        if cause in chapters and effect in chapters:
            assert chapters[cause] <= chapters[effect], line


def test_the_event_markers_are_not_the_stage_list_again(document):
    """Ten of this book's twelve markers were 「阶段开启」 and 「转折」, one pair per act.

    The chart sits directly under the stage list, so those marks said nothing the reader had
    not just read, and buried the two that did.
    """
    markers = document["pacing"]["event_markers"]
    assert markers, "没有事件标记"
    assert not any(m["marker_type"] == "story_stage" for m in markers), markers


@pytest.mark.parametrize(
    "short,full,merge",
    [
        # A contraction drops the middle and keeps both ends. This is the case that split
        # 《系统豪横》's cast: 洪霞警官 and 洪警官 ranked as two people, each holding half a
        # history, and the character table listed both.
        ("洪警官", "洪霞警官", True),
        ("王主任", "王建国主任", True),
        ("贝姐", "贝小姐", True),
        # A relative keeps the whole name and appends a role, which is why the obvious
        # substring test is wrong: merging these would delete a character from the book.
        ("李山木", "李山木父亲", False),
        ("李山木", "李山木的母亲", False),
        ("李山木", "李山木儿子", False),
        # Different people who merely share a surname, and a name against itself.
        ("赵明", "赵玲", False),
        ("马勇", "马妈妈", False),
        ("张三", "张三丰", False),
        ("曾昭野", "曾昭野", False),
    ],
)
def test_a_contracted_name_merges_but_a_relative_does_not(short, full, merge):
    from app.narrative_core.long_novel.orchestrator import _is_contraction_of

    assert _is_contraction_of(short, full) is merge


def test_merging_a_contraction_keeps_the_fuller_name_and_its_mentions():
    from app.narrative_core.long_novel.orchestrator import _fold_contracted_names

    rows = _fold_contracted_names([
        {"display_surface_norm": "洪霞警官", "centrality": 30, "blocks": 6},
        {"display_surface_norm": "洪警官", "centrality": 12, "blocks": 3},
        {"display_surface_norm": "李山木", "centrality": 20, "blocks": 5},
        {"display_surface_norm": "李山木父亲", "centrality": 8, "blocks": 2},
    ])
    names = [r["display_surface_norm"] for r in rows]
    assert names.count("洪霞警官") == 1 and "洪警官" not in names
    assert "李山木" in names and "李山木父亲" in names
    merged = next(r for r in rows if r["display_surface_norm"] == "洪霞警官")
    assert merged["centrality"] == 42 and merged["aliases"] == ["洪警官"]


def test_the_confirmed_profile_names_the_book_not_the_models_guess():
    """INV-P2, at the one place on the page the user typed in themselves.

    The report printed whatever the final synthesis call guessed — on 《系统豪横》 that was
    「都市生活」 at confidence 0.0, on a page belonging to the user who had confirmed the book
    as 升级流. The axes were already steering extraction and the journey; they were not
    steering the line at the top that names the book.
    """
    from app.narrative_core.long_novel.adapter import build_type_profile_section

    guessed = {"primary_genre": "都市生活", "secondary_genres": ["家庭伦理"]}
    axes = {"engine": "progression", "audience": "male_gratification"}

    confirmed = build_type_profile_section(guessed, axes)
    assert confirmed["primary_genre"] == "男频升级流"
    # The guess is an observation about the text and is kept, just not as the headline.
    assert confirmed["secondary_genres"][0] == "都市生活"
    # A person answered this, which is not the model being sure — it is the question being
    # settled by someone entitled to settle it.
    assert confirmed["genre_confidence"] == 1.0

    # No confirmed axes: the guess stands, and claims no confidence it cannot measure.
    unconfirmed = build_type_profile_section(guessed, {})
    assert unconfirmed["primary_genre"] == "都市生活"
    assert unconfirmed["genre_confidence"] == 0.0
    assert build_type_profile_section(None, {}) is None
    # Axes alone are enough: a confirmed book whose synthesis said nothing still gets named.
    assert build_type_profile_section(None, axes)["primary_genre"] == "男频升级流"


def test_an_assessment_finding_can_be_opened(document):
    """Every dimension and every issue carried an empty evidence list on the real run.

    Beside them sat 419 real quotations in the index. The conclusions were right — 第 43–45 章
    节奏偏缓 is the most actionable line either report produces — and there was no way to read
    the chapters it was about.
    """
    index = document["evidence_index"]
    findings = document["assessment"]["issues"] + document["assessment"]["strengths"]
    assert findings, "评估里没有任何结论"
    for finding in findings:
        assert finding["evidence"], finding
        assert all(e in index for e in finding["evidence"]), finding
        for e in finding["evidence"]:
            chapter = index[e]["chapter_index"]
            assert finding["chapter_start"] <= chapter <= finding["chapter_end"], (
                "引的原文不在这条结论说的章节范围里：%s" % finding
            )

