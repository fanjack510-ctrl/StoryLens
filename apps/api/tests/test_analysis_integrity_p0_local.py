"""Local tests for grounding / fingerprint / scope integrity (CHG-20260722-005)."""

from __future__ import annotations

import hashlib

import pytest

from app.services.analysis_context_fingerprint import (
    build_request_scope_binding,
    compute_source_context_fingerprint,
    paragraph_content_hash,
)
from app.services.analysis_grounding import (
    ERROR_EVIDENCE_CLAIM,
    ERROR_EVIDENCE_SCOPE,
    ERROR_GROUNDING_ENTITY,
    assert_async_result_identity,
    classify_integrity_status,
    validate_claim_entities_against_evidence,
    validate_entities_in_scene_or_aliases,
    validate_evidence_scope,
)


def test_fingerprint_changes_when_paragraph_text_changes():
    ids = ["B0001-C0001-P0001", "B0001-C0001-P0002"]
    h1 = [paragraph_content_hash("甲文"), paragraph_content_hash("乙文")]
    h2 = [paragraph_content_hash("甲文"), paragraph_content_hash("丙文")]
    a = compute_source_context_fingerprint(
        book_id=1,
        chapter_id=2,
        analysis_run_id=3,
        scene_id=4,
        ordered_paragraph_ids=ids,
        paragraph_content_hashes=h1,
        prompt_version="p1",
        contract_version="c1",
    )
    b = compute_source_context_fingerprint(
        book_id=1,
        chapter_id=2,
        analysis_run_id=3,
        scene_id=4,
        ordered_paragraph_ids=ids,
        paragraph_content_hashes=h2,
        prompt_version="p1",
        contract_version="c1",
    )
    assert a != b


def test_request_scope_binding_includes_content_hash_and_ids():
    binding = build_request_scope_binding(
        book_id=10,
        chapter_id=1221,
        analysis_run_id=9,
        scene_ids=[77, 78],
        ordered_paragraph_ids=["B0010-C0001-P0017"],
        exact_input_content_hash="abc",
        prompt_version="v1",
        contract_version="1.6",
        formula_version="f1",
        analysis_mode="reader_journey_scene",
        provider="aliyun_qwen_plus",
        model_id="qwen",
    )
    assert binding["book_id"] == 10
    assert binding["analysis_run_id"] == 9
    assert binding["exact_input_content_hash"] == "abc"
    assert binding["scene_ids"] == [77, 78]


def test_different_books_same_ordinal_have_different_scope_keys():
    a = build_request_scope_binding(
        book_id=1,
        chapter_id=2,
        analysis_run_id=1,
        scene_ids=[5],
        ordered_paragraph_ids=["B0001-C0002-P0001"],
        exact_input_content_hash="hash-a",
        prompt_version="p",
        contract_version="c",
        formula_version="f",
        analysis_mode="reader_journey_scene",
        provider="p",
        model_id="m",
    )
    b = build_request_scope_binding(
        book_id=2,
        chapter_id=2,
        analysis_run_id=2,
        scene_ids=[5],
        ordered_paragraph_ids=["B0002-C0002-P0001"],
        exact_input_content_hash="hash-b",
        prompt_version="p",
        contract_version="c",
        formula_version="f",
        analysis_mode="reader_journey_scene",
        provider="p",
        model_id="m",
    )
    assert hashlib.sha256(str(a).encode()).hexdigest() != hashlib.sha256(str(b).encode()).hexdigest()


def test_evidence_from_other_book_rejected():
    issues = validate_evidence_scope(
        evidence_paragraph_ids=["B0002-C0001-P0001"],
        allowed_paragraph_ids=["B0001-C0001-P0001"],
        book_prefix="B0001-",
        scene_id=1,
        scene_ordinal=5,
    )
    assert any(i.code == ERROR_EVIDENCE_SCOPE for i in issues)


def test_evidence_from_other_scene_rejected():
    issues = validate_evidence_scope(
        evidence_paragraph_ids=["B0001-C0001-P0099"],
        allowed_paragraph_ids=["B0001-C0001-P0001", "B0001-C0001-P0002"],
        book_prefix="B0001-",
        scene_id=1,
        scene_ordinal=5,
    )
    assert any(i.code == ERROR_EVIDENCE_SCOPE for i in issues)


def test_claim_evidence_mismatch_when_entity_missing_in_cited_paragraph():
    issues = validate_claim_entities_against_evidence(
        claim_text="古青试探林年，揭示旧识关系并戏弄其身份",
        evidence_texts={"B0010-C0001-P0018": "夜色渐浓，街灯亮起。"},
        cited_paragraph_ids=["B0010-C0001-P0018"],
        scene_id=77,
        scene_ordinal=5,
        field_path="hooks[0]",
        min_unsupported_entities=1,
    )
    assert any(i.code == ERROR_EVIDENCE_CLAIM for i in issues)


def test_grounding_entity_mismatch_for_foreign_entities():
    issues = validate_entities_in_scene_or_aliases(
        claim_text="众神之主古青召见林年并重提旧约",
        scene_text="林年走进房间，看见桌子上的信件。",
        scene_id=1,
        scene_ordinal=1,
        min_foreign_entities=2,
    )
    assert any(i.code == ERROR_GROUNDING_ENTITY for i in issues)


def test_async_identity_mismatch_raises():
    with pytest.raises(ValueError, match="ASYNC_RESULT_IDENTITY_MISMATCH"):
        assert_async_result_identity(
            result_run_id=9,
            expected_run_id=9,
            result_scene_id=1,
            expected_scene_id=2,
        )


def test_async_fingerprint_mismatch_raises():
    with pytest.raises(ValueError, match="ANALYSIS_CONTEXT_MISMATCH"):
        assert_async_result_identity(
            result_run_id=9,
            expected_run_id=9,
            result_scene_id=1,
            expected_scene_id=1,
            result_fingerprint="aaa",
            expected_fingerprint="bbb",
        )


def test_classify_legacy_and_failed():
    assert classify_integrity_status([], fingerprint_state="missing_legacy") == "legacy_unverified"
    from app.services.analysis_grounding import GroundingIssue

    soft = [
        GroundingIssue(code=ERROR_EVIDENCE_CLAIM, message="x", scene_id=1, scene_ordinal=5)
    ]
    # Soft claim issues on legacy artifacts become partial, not whole-Journey hard-fail.
    assert classify_integrity_status(soft, fingerprint_state="missing_legacy") == "partially_trusted"
    assert classify_integrity_status([], fingerprint_state="missing_legacy") == "legacy_unverified"

    severe = [
        GroundingIssue(
            code=ERROR_EVIDENCE_SCOPE,
            message="证据段落不属于当前Book",
            scene_id=1,
            scene_ordinal=5,
            paragraph_ids=["B0002-C0001-P0001"],
        )
    ]
    assert classify_integrity_status(severe, fingerprint_state="missing_legacy") == "data_integrity_failed"
    assert (
        classify_integrity_status(soft, fingerprint_state="ok") == "partially_trusted"
    )
    assert classify_integrity_status([], fingerprint_state="mismatch") == "data_integrity_failed"


def test_craft_commentary_is_not_treated_as_story_entities():
    from app.services.analysis_grounding import is_craft_commentary_text

    assert is_craft_commentary_text("典型的强钩子开头，通过非常规视角吸引读者继续阅读。")
    assert not is_craft_commentary_text("齐夏查看卡片，揭示自己为说谎者。")


def test_provider_messages_are_request_local():
    """HTTP adapter must build payload from the current request only."""
    from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
    from app.model_gateway.base import ModelRequest
    import inspect

    src = inspect.getsource(OpenAICompatibleProvider.generate)
    assert "request.messages" in src
    assert "self.messages" not in src
    # Construct two independent requests — no shared mutable history on provider.
    provider = OpenAICompatibleProvider(
        name="fake",
        base_url="http://127.0.0.1:9",
        api_key="x",
        default_model="m",
        timeout_seconds=1,
        max_context_tokens=1024,
        enabled=False,
    )
    req_a = ModelRequest(messages=[{"role": "user", "content": "BookA正文甲"}], model="m")
    req_b = ModelRequest(messages=[{"role": "user", "content": "BookB正文乙"}], model="m")
    assert req_a.messages[0]["content"] != req_b.messages[0]["content"]
    assert not hasattr(provider, "messages")
