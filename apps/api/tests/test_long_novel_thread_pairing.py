"""L2 suspense pairing — which reveal answers which question.

This is the judgement a block structurally cannot make. A thread is opened in chapter 25 and
answered in chapter 400; the block holding chapter 400 sees eight chapters. Carrying the open
slate forward got threads *recognised* across blocks — measured on the real book, 27 of 40
are revisited across block boundaries, one spanning 791 chapters — but only 1 of 40 was ever
marked resolved, because "is this the answer" was being asked block by block.

The rule these tests exist to hold: **an unpaired thread beats an invented pairing.** A
thread wrongly marked 已回收 tells an author the line is closed, so they stop looking for the
hole — strictly worse than leaving it open.
"""

from __future__ import annotations

from app.narrative_core.long_novel.contracts.l1 import (
    BlockAsset,
    EvidenceRef,
    SuspenseAction,
    SuspenseThread,
)
from app.narrative_core.long_novel.orchestrator import RunCoordinator

EV = [EvidenceRef(paragraph_ref=1)]
Q1 = "门对面是什么？"
Q2 = "十一年前的大火是谁放的？"


def _assets() -> dict[str, BlockAsset]:
    return {
        "blk-1": BlockAsset(
            asset_schema_version="1",
            suspense_threads=[
                SuspenseThread(question=Q1, opened_chapter_ref=2, evidence=EV),
                SuspenseThread(question=Q2, opened_chapter_ref=75, evidence=EV),
            ],
            suspense_actions=[
                SuspenseAction(thread_ref=Q1, action_kind="advance",
                               information_added="又提到了那扇门", chapter_ref=18, evidence=EV),
            ],
        ),
        "blk-9": BlockAsset(
            asset_schema_version="1",
            suspense_actions=[
                SuspenseAction(thread_ref=Q1, action_kind="reveal",
                               information_added="门后是失乡号的甲板", chapter_ref=400, evidence=EV),
                SuspenseAction(thread_ref="", action_kind="twist",
                               information_added="纵火的是审判官自己", chapter_ref=612, evidence=EV),
            ],
        ),
    }


def _lifecycles():
    return [
        {"question": Q1, "chapter_start": 2, "chapter_end": 18, "status": "unresolved", "events": []},
        {"question": Q2, "chapter_start": 75, "chapter_end": 75, "status": "unresolved", "events": []},
    ]


def test_only_revealing_beats_are_offered_for_pairing():
    """`advance` is movement without revelation — offering it only invites a false pairing."""
    payload = RunCoordinator._pairing_input(RunCoordinator, _assets())
    kinds = {r["kind"] for r in payload["reveals"]}
    assert kinds == {"reveal", "twist"}
    assert all("又提到了那扇门" != r["text"] for r in payload["reveals"])
    assert {t["question"] for t in payload["threads"]} == {Q1, Q2}


def test_a_pairing_closes_the_thread_and_records_the_answer():
    payload = RunCoordinator._pairing_input(RunCoordinator, _assets())
    lifecycles = _lifecycles()
    reveal = next(r for r in payload["reveals"] if r["chapter"] == 400)
    thread = next(t for t in payload["threads"] if t["question"] == Q1)

    closed = RunCoordinator._apply_pairs(
        lifecycles, payload,
        {"pairs": [{"thread_id": thread["thread_id"], "reveal_id": reveal["reveal_id"],
                    "answer": "门通向失乡号"}]},
    )
    assert closed == 1
    answered = next(l for l in lifecycles if l["question"] == Q1)
    assert answered["status"] == "resolved"
    assert answered["truth"] == "门通向失乡号"
    # The span now reaches the chapter that answered it, not the last time it was mentioned.
    assert answered["chapter_end"] == 400
    # The thread nobody answered is left alone.
    assert next(l for l in lifecycles if l["question"] == Q2)["status"] == "unresolved"


def test_an_empty_answer_is_not_a_resolution():
    payload = RunCoordinator._pairing_input(RunCoordinator, _assets())
    lifecycles = _lifecycles()
    closed = RunCoordinator._apply_pairs(
        lifecycles, payload,
        {"pairs": [{"thread_id": "T1", "reveal_id": payload["reveals"][0]["reveal_id"],
                    "answer": "  "}]},
    )
    assert closed == 0
    assert all(l["status"] == "unresolved" for l in lifecycles)


def test_a_pair_naming_something_that_was_not_sent_is_dropped():
    """A hallucinated id must not close a thread — 已回收 stops an author looking."""
    payload = RunCoordinator._pairing_input(RunCoordinator, _assets())
    lifecycles = _lifecycles()
    closed = RunCoordinator._apply_pairs(
        lifecycles, payload,
        {"pairs": [{"thread_id": "T1", "reveal_id": "R999", "answer": "凭空捏造的答案"}]},
    )
    assert closed == 0
    assert all(l["status"] == "unresolved" for l in lifecycles)


def test_no_pairs_at_all_leaves_every_thread_open():
    payload = RunCoordinator._pairing_input(RunCoordinator, _assets())
    lifecycles = _lifecycles()
    for result in ({}, {"pairs": []}, None):
        assert RunCoordinator._apply_pairs(lifecycles, payload, result) == 0
    assert all(l["status"] == "unresolved" for l in lifecycles)


def test_the_payload_is_bounded_so_it_does_not_grow_with_the_book():
    """The input must be O(1) in book length — that is the property the design exists for."""
    assets = {
        f"blk-{i}": BlockAsset(
            asset_schema_version="1",
            suspense_threads=[
                SuspenseThread(question=f"第{i * 5 + j}个疑问？", opened_chapter_ref=i * 8 + 1,
                               evidence=EV)
                for j in range(5)
            ],
            suspense_actions=[
                SuspenseAction(thread_ref="", action_kind="reveal",
                               information_added=f"第{i}块的揭示{j}", chapter_ref=i * 8 + j + 1,
                               evidence=EV)
                for j in range(5)
            ],
        )
        for i in range(100)
    }
    payload = RunCoordinator._pairing_input(RunCoordinator, assets)
    assert len(payload["threads"]) == RunCoordinator.PAIRING_THREADS_MAX
    assert len(payload["reveals"]) == RunCoordinator.PAIRING_REVEALS_MAX
