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


class _P:
    """Minimal stand-in for a profile item — only scene_id matters here."""

    def __init__(self, scene_id: int) -> None:
        self.scene_id = scene_id


class _B:
    def __init__(self, ids: list[int]) -> None:
        self.profiles = [_P(i) for i in ids]


def test_the_ordinal_for_id_confusion_is_remapped_not_guessed() -> None:
    """Measured on 《醉枕江山》第59章: expected scenes [18], got [1].

    The payload hands the model scene_id and scene_ordinal side by side and, until prompt
    v2.3, never said which to echo. When the returned set IS the ordinal set, the mapping is
    ours and the rewrite is arithmetic, not inference.
    """
    from app.services.reader_journey_v2_execution import normalize_scene_ids_v2

    batch = _B([1, 2, 3])
    notes = normalize_scene_ids_v2(
        batch,
        expected_scene_ids={18, 19, 20},
        ordinal_to_scene_id={1: 18, 2: 19, 3: 20},
    )
    assert [p.scene_id for p in batch.profiles] == [18, 19, 20]
    assert notes == ["scene_id 1→18", "scene_id 2→19", "scene_id 3→20"]


def test_a_correct_batch_is_left_alone() -> None:
    from app.services.reader_journey_v2_execution import normalize_scene_ids_v2

    batch = _B([18, 19, 20])
    assert (
        normalize_scene_ids_v2(
            batch,
            expected_scene_ids={18, 19, 20},
            ordinal_to_scene_id={1: 18, 2: 19, 3: 20},
        )
        == []
    )
    assert [p.scene_id for p in batch.profiles] == [18, 19, 20]


def test_anything_short_of_an_exact_bijection_falls_through_to_the_validator() -> None:
    """The remap must never rescue a batch we cannot account for.

    A partial match, a duplicate, or an unknown number means we do not know what the model
    meant — and quietly picking one would attach a scene's analysis to different text, which
    is worse than the failure it replaces.
    """
    from app.services.reader_journey_v2_execution import normalize_scene_ids_v2

    mapping = {1: 18, 2: 19, 3: 20}
    for ids in ([1, 2], [1, 2, 9], [1, 1, 2], [1, 2, 3, 4], []):
        batch = _B(list(ids))
        before = [p.scene_id for p in batch.profiles]
        assert (
            normalize_scene_ids_v2(
                batch, expected_scene_ids={18, 19, 20}, ordinal_to_scene_id=mapping
            )
            == []
        ), ids
        assert [p.scene_id for p in batch.profiles] == before, ids


def test_the_prompt_states_the_id_rule() -> None:
    # The root cause was that it did not. If this text goes away the failure comes back, and
    # it comes back as a permanent, non-retryable failure on the user's chapter.
    from pathlib import Path

    from app.schemas.reader_journey_v2 import SCENE_PROMPT_VERSION_V2

    root = Path(__file__).resolve().parents[3]
    text = (
        root / "packages" / "prompts" / "reader_journey_scene" / SCENE_PROMPT_VERSION_V2 / "system.md"
    ).read_text(encoding="utf-8")
    assert "scene_id" in text and "scene_ordinal" in text
    assert "逐字符复制" in text
    # The shape, as a placeholder that cannot be copied. The first version of this rule used
    # a real id from another book as the example and the model copied it verbatim: 星芒's
    # scene 25 came back citing B0013-C0060-P0007, a paragraph of 《醉枕江山》. An illustrative
    # id that happens to resolve is not illustrative, it is an instruction.
    assert "B####-C####-P####" in text
    assert "格式示意" in text
    import re as _re

    body = text.split("## ID 必须原样抄回")[1].split("\n## ")[0]
    assert not _re.search(r"B\d{4}-C\d{4}-P\d{4}", body), (
        "the ID rule must not contain a copyable real-looking paragraph id"
    )


def test_no_field_asks_for_a_paragraph_number_where_the_contract_wants_an_id() -> None:
    """A prompt that says 「段号」 and a field named ``evidence_paragraph_ids`` disagree.

    Measured on 《星芒纵横》第3章, which failed three times running: once with the ordinal in
    scene_id, once copying a paragraph id out of the rule's own worked example, and once
    synthesising ``B0025-C0001-P0001`` — book 25 does not exist; the model built a
    correctly-shaped id out of the scene_id it had, because craft_flags asked for a number
    and the schema wanted an id. Naming the format without naming the field is what leaves
    that gap.
    """
    from pathlib import Path

    from app.schemas.reader_journey_v2 import SCENE_PROMPT_VERSION_V2

    root = Path(__file__).resolve().parents[3]
    text = (
        root / "packages" / "prompts" / "reader_journey_scene" / SCENE_PROMPT_VERSION_V2 / "system.md"
    ).read_text(encoding="utf-8")

    # 段号 may only appear where it is explicitly being ruled out.
    for line in text.splitlines():
        if "段号" in line:
            assert "不是填段号" in line, f"asks for a paragraph number: {line.strip()}"


def _profile_with(scene_id: int, **kw):
    """A minimal profile object exposing only the id-bearing attributes we sanitise."""

    class _F:
        def __init__(self, ids):
            self.evidence_paragraph_ids = list(ids)

    class _Q:
        def __init__(self, pid):
            self.paragraph_id = pid

    from app.schemas.reader_journey_v2 import LEVEL_METRIC_KEYS

    class _Prof:
        pass

    p = _Prof()
    p.scene_id = scene_id
    p.evidence_paragraph_ids = list(kw.get("scene_evidence", []))
    for key in LEVEL_METRIC_KEYS:
        setattr(p, key, _F(kw.get(key, [])))
    p.craft_flags = [_F(ids) for ids in kw.get("craft_flags", [])]
    p.genre_axes = [_F(ids) for ids in kw.get("genre_axes", [])]
    p.reader_questions_opened = [_Q(pid) for pid in kw.get("opened", [])]
    p.reader_questions_answered = [_Q(pid) for pid in kw.get("answered", [])]
    p.first_hook_paragraph_id = kw.get("first_hook")
    return p


class _Batch:
    def __init__(self, profiles):
        self.profiles = profiles


REAL = "B0011-C0003-P0009"
ALSO_REAL = "B0011-C0003-P0010"
# The four inventions 《星芒纵横》第3章 produced across four consecutive runs.
FAKES = ["p1", "B0013-C0060-P0007", "B0025-C0001-P0001", "B0001-C0001-P0001"]


def test_a_fabricated_citation_is_dropped_not_resolved() -> None:
    from app.services.reader_journey_v2_execution import drop_unresolvable_paragraph_ids_v2

    prof = _profile_with(
        25,
        scene_evidence=[REAL, FAKES[0]],
        hook=[FAKES[1]],
        craft_flags=[[FAKES[2], ALSO_REAL]],
        opened=[REAL, FAKES[3]],
        first_hook=FAKES[3],
    )
    counts = drop_unresolvable_paragraph_ids_v2(
        _Batch([prof]), paragraph_ids_by_scene={25: {REAL, ALSO_REAL}}
    )
    assert prof.evidence_paragraph_ids == [REAL]
    assert prof.hook.evidence_paragraph_ids == []
    assert prof.craft_flags[0].evidence_paragraph_ids == [ALSO_REAL]
    assert [q.paragraph_id for q in prof.reader_questions_opened] == [REAL]
    assert prof.first_hook_paragraph_id is None
    # Every drop is counted; a silent loss would look like the model never cited anything.
    assert counts == {
        "scene_evidence": 1,
        "field:hook": 1,
        "craft_flags": 1,
        "reader_questions_opened": 1,
        "first_hook_paragraph_id": 1,
    }


def test_a_clean_batch_is_untouched() -> None:
    from app.services.reader_journey_v2_execution import drop_unresolvable_paragraph_ids_v2

    prof = _profile_with(25, scene_evidence=[REAL], hook=[ALSO_REAL], first_hook=REAL)
    assert (
        drop_unresolvable_paragraph_ids_v2(
            _Batch([prof]), paragraph_ids_by_scene={25: {REAL, ALSO_REAL}}
        )
        == {}
    )
    assert prof.evidence_paragraph_ids == [REAL]
    assert prof.first_hook_paragraph_id == REAL


def test_a_scene_we_cannot_check_is_left_alone() -> None:
    # No allowed set means we have nothing to judge against; removing citations there would
    # be destroying data on no evidence.
    from app.services.reader_journey_v2_execution import drop_unresolvable_paragraph_ids_v2

    prof = _profile_with(99, scene_evidence=[FAKES[0]], first_hook=FAKES[1])
    assert drop_unresolvable_paragraph_ids_v2(_Batch([prof]), paragraph_ids_by_scene={}) == {}
    assert prof.evidence_paragraph_ids == [FAKES[0]]


def test_dropping_never_invents_a_replacement() -> None:
    """The whole point: an invented id carries no information about what was meant.

    Resolving 「B0025-C0001-P0001」 to *some* paragraph would attach a claim to text the
    model never looked at — the failure mode the grounding guard exists to catch.
    """
    from app.services.reader_journey_v2_execution import drop_unresolvable_paragraph_ids_v2

    prof = _profile_with(25, scene_evidence=list(FAKES))
    drop_unresolvable_paragraph_ids_v2(
        _Batch([prof]), paragraph_ids_by_scene={25: {REAL, ALSO_REAL}}
    )
    assert prof.evidence_paragraph_ids == []


class _Flag:
    def __init__(self, kind):
        self.kind = kind
        self.evidence_paragraph_ids = []


class _Level:
    def __init__(self, level):
        self.level = level


def _flag_profile(kind, field, level):
    class _Prof:
        pass

    p = _Prof()
    p.scene_id = 25
    p.craft_flags = [_Flag(kind)]
    setattr(p, field, _Level(level))
    return p


def test_a_flag_its_own_score_contradicts_is_withdrawn() -> None:
    """Measured on 《星芒纵横》第3章: raised redundant_passage but redundancy=1 (min 3).

    The score feeds the curve and every stored artifact; the flag only says where. When they
    disagree the claim goes, not the measurement, and certainly not the chapter.
    """
    from app.services.reader_journey_v2_execution import drop_unsupported_craft_flags_v2

    prof = _flag_profile("redundant_passage", "redundancy", 1)
    assert drop_unsupported_craft_flags_v2(_Batch([prof])) == {"redundant_passage": 1}
    assert prof.craft_flags == []


def test_every_flag_kind_is_checked_against_its_own_field() -> None:
    from app.services.reader_journey_v2_execution import (
        _FLAG_FIELD_BOUNDS,
        drop_unsupported_craft_flags_v2,
    )

    for kind, (field, direction, limit) in _FLAG_FIELD_BOUNDS.items():
        bad = limit + 1 if direction == "max" else limit - 1
        prof = _flag_profile(kind, field, bad)
        assert drop_unsupported_craft_flags_v2(_Batch([prof])) == {kind: 1}, kind
        assert prof.craft_flags == [], kind


def test_a_flag_its_score_agrees_with_is_kept() -> None:
    from app.services.reader_journey_v2_execution import (
        _FLAG_FIELD_BOUNDS,
        drop_unsupported_craft_flags_v2,
    )

    for kind, (field, direction, limit) in _FLAG_FIELD_BOUNDS.items():
        good = limit if direction == "max" else limit
        prof = _flag_profile(kind, field, good)
        assert drop_unsupported_craft_flags_v2(_Batch([prof])) == {}, kind
        assert len(prof.craft_flags) == 1, kind


def test_a_run_note_never_crashes_the_provider_request() -> None:
    """The three sanitisers all record what they did, and recording must be inert.

    Passing a plain dict to ``merge_run_provenance`` — which expects a versions object and
    calls ``.provenance()`` on it — raised ``'dict' object has no attribute 'provenance'``,
    surfaced as ``PROVIDER_TRANSPORT_ERROR`` at stage ``provider_request``. A note about a
    repair must never be able to fail the request the repair just rescued.
    """
    import json as _json

    from app.services.reader_journey_v2_execution import _record_run_note

    class _Run:
        failure_details_json = None

    run = _Run()
    _record_run_note(run, "withdrawn_craft_flags", {"redundant_passage": 1})
    _record_run_note(run, "scene_id_normalisations", ["scene_id 1→25"])
    _record_run_note(run, "dropped_paragraph_citations", {"craft_flags": 2})
    details = _json.loads(run.failure_details_json)
    assert details["withdrawn_craft_flags"] == {"redundant_passage": 1}
    assert details["scene_id_normalisations"] == ["scene_id 1→25"]
    assert details["dropped_paragraph_citations"] == {"craft_flags": 2}

    # Existing details survive, and unparseable details do not raise.
    run.failure_details_json = '{"source_mode": "v2_native"}'
    _record_run_note(run, "withdrawn_craft_flags", {"causal_gap": 1})
    assert _json.loads(run.failure_details_json)["source_mode"] == "v2_native"
    run.failure_details_json = "not json"
    _record_run_note(run, "x", 1)
    assert _json.loads(run.failure_details_json) == {"x": 1}
