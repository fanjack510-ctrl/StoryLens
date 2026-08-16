# -*- coding: utf-8 -*-
"""V2 结果的来源校验：指纹要写，问句不该被当成断言。

Two defects that only showed together.

1. ``persist_finalized_v2_profiles`` never wrote ``source_context_fingerprint``. The v1
   pipeline always has. With no fingerprint, ``classify_integrity_status`` returns
   ``legacy_unverified`` for every v2 result, which is what put 「旧版分析尚未完成来源校验，
   仅供参考」 on top of freshly-run native analyses — and, worse, meant the integrity guard
   could not detect edited text under any v2 run at all.

2. Writing the fingerprint switched the guard on, and it immediately hid every hook field
   (``display_policy: hide_field``), blanking the reader questions on the page. The cause is
   a category error: ``validate_claim_entities_against_evidence`` asks whether a claim's
   words appear in the paragraph it cites, and a reader question is not a claim about the
   text — it is what the text makes the reader wonder.

   Measured on 《再也不见》第一章: 「他到底能不能放下齐沫？」 cited to the paragraph that genuinely
   raises it scored 23 of 24 tokens unsupported; the same question cited to an unrelated
   paragraph from a different book scored 24 of 24. The check has no discriminating power on
   this field type, so running it there produces only false positives.
"""

from __future__ import annotations

from app.services.analysis_grounding import (
    ERROR_EVIDENCE_CLAIM,
    classify_integrity_status,
    validate_claim_entities_against_evidence,
    validate_evidence_scope,
)
from app.services.analysis_integrity_guard import _is_question_text


def test_a_question_is_not_an_assertion() -> None:
    assert _is_question_text("他到底能不能放下齐沫？")
    assert _is_question_text("Who is he?")
    assert not _is_question_text("背后声音的出现是强钩子，但出现在场景中段。")
    assert not _is_question_text("")
    assert not _is_question_text(None)


def test_the_entity_check_cannot_tell_a_grounded_question_from_an_ungrounded_one() -> None:
    """The measurement that justifies the exemption, kept executable.

    If some future extractor makes this check able to separate the two, this test fails and
    the exemption should be revisited — that is the point of pinning it.
    """
    question = "他到底能不能放下齐沫？"
    grounded = (
        "我冷笑道，你以为女人真的是衣服啊？就算是衣服，脱下时也有个冷暖适应的过程。"
        "何况她不是衣服。她是我爱了两年的齐沫。"
    )
    unrelated = "那是位披着大红戏袍的少年，背后还立着另一个自己。"

    def unsupported(evidence: str) -> int:
        issues = validate_claim_entities_against_evidence(
            claim_text=question,
            evidence_texts={"B0007-C0002-P0042": evidence},
            cited_paragraph_ids=["B0007-C0002-P0042"],
        )
        return len(issues[0].entities) if issues else 0

    # Both are flagged, and by comparable amounts — the signal is not there.
    assert unsupported(grounded) > 0
    assert unsupported(unrelated) > 0


def test_an_assertion_in_the_same_item_is_still_checked() -> None:
    # The exemption is per text, not per item: exempting a question must not smuggle a
    # neighbouring false claim past the guard.
    issues = validate_claim_entities_against_evidence(
        claim_text="陈伶在戏道古藏里见到了九君与帝神道的师兄师姐",
        evidence_texts={"B0007-C0002-P0002": "走在学校的林荫小道上，觉得这条路无限的长。"},
        cited_paragraph_ids=["B0007-C0002-P0002"],
    )
    assert issues and issues[0].code == ERROR_EVIDENCE_CLAIM


def test_a_question_still_has_to_cite_a_paragraph_inside_its_scene() -> None:
    # Scope is a different check and it is NOT exempted: a question may be unquotable, but
    # it must still point at text that exists in this scene.
    issues = validate_evidence_scope(
        evidence_paragraph_ids=["B0007-C0002-P0099"],
        allowed_paragraph_ids=["B0007-C0002-P0001", "B0007-C0002-P0002"],
        book_prefix="B0007-",
    )
    assert issues, "a question citing outside its scene must still be rejected"


def test_a_stored_fingerprint_is_what_separates_verified_from_legacy() -> None:
    assert classify_integrity_status([], fingerprint_state="ok") == "trusted"
    assert (
        classify_integrity_status([], fingerprint_state="missing_legacy")
        == "legacy_unverified"
    )
    assert (
        classify_integrity_status([], fingerprint_state="mismatch")
        == "data_integrity_failed"
    )


def test_v2_persist_computes_the_fingerprint_the_verifier_recomputes() -> None:
    """Both sides must read the same paragraphs and the same versions.

    Diverging on either produces ``mismatch``, which the UI reports as tampering rather than
    as a bug — a worse failure than the missing fingerprint this replaced.
    """
    import inspect

    from app.services import reader_journey_v2_persist as persist
    from app.services import analysis_integrity_guard as guard

    source = inspect.getsource(persist._source_context_fingerprint)
    # Same paragraph reader as the verifier.
    assert "_paragraphs_for_scene" in source
    assert "_paragraphs_for_scene" in inspect.getsource(guard.scan_journey_profile_grounding)
    # Same three versions, taken off the run rather than off module constants.
    for field in ("scene_prompt_version", "scene_contract_version", "formula_version"):
        assert f"journey_run.{field}" in source
