"""场景切分 v4.0 的映射与防御 (CHG-20260815-099).

The failure this replaces is on record: v3.5 returned the first value of every enum for all
67 transitions of a 68-paragraph chapter and produced one scene. What is pinned here is the
mapping from scene starts to boundaries, and that nothing the model says is trusted without
being checked against the paragraphs that exist.
"""

from __future__ import annotations

from app.schemas.scene import SceneSegmentationResultV40
from app.services.scene_segmentation_v40 import (
    build_segmentation_snapshot,
    map_segments_to_boundaries,
)

IDS = [f"B0010-C0002-P{n:04d}" for n in range(1, 11)]


def _result(starts, markers=None, why=None):
    return SceneSegmentationResultV40.model_validate(
        {
            "markers": markers or [],
            "scenes": [
                {"start": s, "where": f"地点{s}", "why": (why or {}).get(s, "")} for s in starts
            ],
        }
    )


def test_scene_starts_become_boundaries_after_the_previous_paragraph() -> None:
    out = map_segments_to_boundaries(_result([1, 4, 8]), chapter_id="C1", paragraph_ids=IDS)
    # A scene starting at 4 means the boundary sits after paragraph 3.
    assert [b.after_paragraph_id for b in out.boundaries] == [IDS[2], IDS[6]]


def test_start_one_is_not_a_boundary() -> None:
    # The chapter opening is not a cut; counting it would make every chapter start twice.
    out = map_segments_to_boundaries(_result([1]), chapter_id="C1", paragraph_ids=IDS)
    assert out.boundaries == []


def test_out_of_range_and_duplicate_starts_are_dropped() -> None:
    # start=0 cannot arrive — the contract rejects it — but a number past the last
    # paragraph can, and did in earlier versions when the model counted its own way.
    out = map_segments_to_boundaries(
        _result([1, 4, 4, 99, 11]), chapter_id="C1", paragraph_ids=IDS
    )
    assert [b.after_paragraph_id for b in out.boundaries] == [IDS[2]]


def test_starts_are_ordered_regardless_of_model_order() -> None:
    out = map_segments_to_boundaries(_result([8, 1, 4]), chapter_id="C1", paragraph_ids=IDS)
    assert [b.after_paragraph_id for b in out.boundaries] == [IDS[2], IDS[6]]


def test_reason_carries_the_models_own_words() -> None:
    out = map_segments_to_boundaries(
        _result([1, 5], why={5: "进入厨房，地点改变"}), chapter_id="C1", paragraph_ids=IDS
    )
    assert out.boundaries[0].reason_summary == "进入厨房，地点改变"


def test_marker_supplies_the_reason_when_the_scene_has_none() -> None:
    out = map_segments_to_boundaries(
        SceneSegmentationResultV40.model_validate(
            {
                "markers": [{"n": 5, "kind": "location", "what": "走进厨房"}],
                "scenes": [{"start": 1}, {"start": 5}],
            }
        ),
        chapter_id="C1",
        paragraph_ids=IDS,
    )
    assert out.boundaries[0].reason_summary == "走进厨房"


def test_empty_segmentation_yields_one_scene_rather_than_a_guess() -> None:
    out = map_segments_to_boundaries(
        SceneSegmentationResultV40.model_validate({"markers": [], "scenes": []}),
        chapter_id="C1",
        paragraph_ids=IDS,
    )
    assert out.boundaries == []
    assert out.overall_confidence == 1.0


def test_snapshot_numbers_paragraphs_from_one() -> None:
    snap = build_segmentation_snapshot(
        chapter_id="C1", title="第一章", paragraph_ids=IDS[:3], texts=["甲", "乙", "丙"]
    )
    assert [p["n"] for p in snap["paragraphs"]] == [1, 2, 3]
    assert [p["text"] for p in snap["paragraphs"]] == ["甲", "乙", "丙"]
    # Ids are not sent: the model only has to echo a small integer back.
    assert "B0010" not in str(snap["paragraphs"])


def test_a_marker_the_scene_list_dropped_still_becomes_a_boundary() -> None:
    """The second step of 先标记后切分 discards its own findings, and does so at random.

    《再也不见》第一章, identical payload, temperature 0, three runs: the marker lands on the
    chapter's turn every time; the scene list keeps it twice. Whether a reader saw the real
    division was luck. The program takes the union instead of asking the model twice.
    """
    out = map_segments_to_boundaries(
        SceneSegmentationResultV40.model_validate(
            {
                "markers": [
                    {"n": 1, "kind": "location", "what": "从林荫小道到寝室"},
                    {"n": 6, "kind": "action_chain", "what": "打闹结束，宣布分手"},
                ],
                "scenes": [{"start": 1}, {"start": 4}],
            }
        ),
        chapter_id="C1",
        paragraph_ids=IDS,
    )
    assert [b.after_paragraph_id for b in out.boundaries] == [IDS[2], IDS[4]]
    # The marker-only cut still carries a reason — the marker's own words.
    assert out.boundaries[1].reason_summary == "打闹结束，宣布分手"


def test_the_union_changes_nothing_when_the_two_lists_agree() -> None:
    # 《我不是戏神》第一章 returned identical markers and starts. The union must be a no-op
    # wherever the model is already self-consistent, or it would over-cut every chapter.
    same = SceneSegmentationResultV40.model_validate(
        {
            "markers": [{"n": n, "kind": "location", "what": f"移动{n}"} for n in (1, 4, 8)],
            "scenes": [{"start": n} for n in (1, 4, 8)],
        }
    )
    out = map_segments_to_boundaries(same, chapter_id="C1", paragraph_ids=IDS)
    assert [b.after_paragraph_id for b in out.boundaries] == [IDS[2], IDS[6]]


def test_a_marker_outside_the_chapter_is_dropped_like_any_other_claim() -> None:
    out = map_segments_to_boundaries(
        SceneSegmentationResultV40.model_validate(
            {
                "markers": [{"n": 99, "kind": "time", "what": "第二天"}],
                "scenes": [{"start": 1}, {"start": 5}],
            }
        ),
        chapter_id="C1",
        paragraph_ids=IDS,
    )
    assert [b.after_paragraph_id for b in out.boundaries] == [IDS[3]]
