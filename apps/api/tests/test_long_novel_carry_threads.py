"""Carry-forward of suspense threads across blocks.

The defect this pins: on a real 806-chapter novel, **40 threads were opened and 0 were
resolved**. Two causes, both silent.

The slate identified a thread by ``THR-`` plus a hash of its question. A handle names nothing
the model can see in the text, so it could never match an action to a thread — and `hash()`
on a str is randomised per process, so the same book produced different handles on every run.

And the slate never reached the model at all. It was computed, threaded through the
coordinator, placed in the payload, and stopped there; nothing put it in the prompt. Every
block met the book's open questions for the first time.
"""

from __future__ import annotations

from app.narrative_core.long_novel.contracts.density import profile
from app.narrative_core.long_novel.contracts.l1 import (
    BlockAsset,
    CarryForwardState,
    EvidenceRef,
    SuspenseAction,
    SuspenseThread,
)
from app.narrative_core.long_novel.extractor import BlockExtractor, RenderedBlock
from app.narrative_core.long_novel.prompts import build_user_prompt
from app.narrative_core.long_novel.reducer import (
    CARRY_THREADS_SHOWN,
    build_carry_out,
    refers_to_thread,
    render_carry_in,
)

QUESTION = "鸽子艾尹到底是什么？为什么会出现？"
EV = [EvidenceRef(paragraph_ref=1)]


def _asset(threads=(), actions=()) -> BlockAsset:
    return BlockAsset(
        asset_schema_version="1",
        suspense_threads=[
            SuspenseThread(question=q, opened_chapter_ref=1, evidence=EV) for q in threads
        ],
        suspense_actions=[
            SuspenseAction(thread_ref=r, action_kind=k, chapter_ref=9, evidence=EV)
            for r, k in actions
        ],
    )


def test_the_slate_carries_the_question_itself_not_an_opaque_handle():
    """A handle names nothing the model can see; the question is what it can match on."""
    carry = build_carry_out(_asset(threads=[QUESTION]), CarryForwardState())
    assert carry.open_thread_refs == [QUESTION]


def test_the_slate_is_identical_across_processes():
    """`hash()` on a str is randomised per process — the same book must not drift."""
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app.narrative_core.long_novel.contracts.l1 import (BlockAsset, CarryForwardState,"
        " EvidenceRef, SuspenseThread)\n"
        "from app.narrative_core.long_novel.reducer import build_carry_out\n"
        "a = BlockAsset(asset_schema_version='1', suspense_threads=["
        "SuspenseThread(question=%r, opened_chapter_ref=1, evidence=[EvidenceRef(paragraph_ref=1)])])\n"
        "print(build_carry_out(a, CarryForwardState()).open_thread_refs)\n"
    ) % (str(__import__("pathlib").Path(__file__).resolve().parents[1]), QUESTION)

    import os

    outs = []
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
        assert done.returncode == 0, done.stderr
        outs.append(done.stdout)
    assert outs[0] == outs[1]


def test_a_resolving_action_closes_the_thread_even_when_it_paraphrases():
    """A thread resolved in chapter 400 must not stay open because the wording drifted."""
    opened = build_carry_out(_asset(threads=[QUESTION]), CarryForwardState())
    closed = build_carry_out(_asset(actions=[("鸽子艾尹到底是什么", "resolve")]), opened)
    assert closed.open_thread_refs == []


def test_an_unrelated_resolve_leaves_the_thread_open():
    opened = build_carry_out(_asset(threads=[QUESTION]), CarryForwardState())
    still = build_carry_out(_asset(actions=[("完全无关的另一个疑问", "resolve")]), opened)
    assert still.open_thread_refs == [QUESTION]


def test_the_slate_is_bounded_so_the_prompt_does_not_grow_with_the_book():
    carry = CarryForwardState(open_thread_refs=[f"第{i}个疑问是什么？" for i in range(200)])
    rendered = render_carry_in(carry)
    assert rendered.count("  - ") == CARRY_THREADS_SHOWN


def test_an_empty_slate_renders_to_nothing():
    """The first block has no history, and must not be handed an empty heading."""
    assert render_carry_in(CarryForwardState()) == ""


def test_the_rendered_slate_tells_the_model_to_reuse_the_wording():
    rendered = render_carry_in(CarryForwardState(open_thread_refs=[QUESTION]))
    assert QUESTION in rendered
    assert "原样照抄" in rendered
    assert "resolve" in rendered


def test_the_slate_reaches_the_prompt():
    """It used to stop at the payload. Everything above is pointless if this fails."""
    carry = CarryForwardState(open_thread_refs=[QUESTION])
    extractor = BlockExtractor(
        provider=object(), profile=profile("D_HIGH"), output_budget=16_000
    )
    payload = extractor.build_payload(RenderedBlock(text="正文", n_paragraphs=1), carry)
    assert QUESTION in str(payload["carry_summary"])

    prompt = build_user_prompt(
        rendered_text="正文",
        profile=profile("D_HIGH"),
        carry_in_summary=str(payload["carry_summary"]),
    )
    assert QUESTION in prompt


def test_thread_matching_tolerates_rephrasing_but_not_collision():
    assert refers_to_thread("教堂低语声", "教堂中的低语声是否来自葛莫娜？")
    assert refers_to_thread("鸽子艾尹到底是什么？为什么会出现？", "鸽子艾尹到底是什么？")
    assert not refers_to_thread("十一年前的大火", "鸽子艾尹到底是什么？")
    # Too short a shared core would match half the book's questions.
    assert not refers_to_thread("是的", "是否有人在说话？")
