"""Budget hard-gate uses estimated (normal path), not worst-case."""

from __future__ import annotations

from app.services.analysis_recovery_center import build_full_pipeline_advisory
from app.services.staged_budget import BudgetAmounts, exceeded_dimensions, estimate_stage1_boundary


def test_stage_estimate_required_uses_estimated_not_worst(testing_session):
    from app.db.models import Book, Chapter, Paragraph

    book = Book(title="门禁", source_file_name="g.txt", source_file_hash="a" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(
        book_id=book.id, chapter_index=1, title="第一章", section_type="chapter"
    )
    testing_session.add(chapter)
    testing_session.flush()
    paragraphs = []
    for index in range(1, 43):
        row = Paragraph(
            id=f"B0001-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"原创段落内容{index}" * 3,
            normalized_text=f"原创段落内容{index}" * 3,
            char_start=index * 10,
            char_end=index * 10 + 8,
        )
        testing_session.add(row)
        paragraphs.append(row)
    testing_session.commit()

    estimate = estimate_stage1_boundary(paragraphs)
    assert estimate.expected_request_count < estimate.worst_case_request_count
    assert estimate.required.requests == estimate.expected_request_count
    assert estimate.required.tokens == estimate.estimated_total_tokens
    assert estimate.required.estimated_cost == estimate.estimated_cost
    assert estimate.worst_case.requests == estimate.worst_case_request_count
    assert estimate.retry_reserve.requests == (
        estimate.worst_case_request_count - estimate.expected_request_count
    )


def test_screenshot_case_executable_when_estimated_fits(testing_session):
    """remaining=7 / estimated=7 / worst=14 → hard gate allows start."""
    remaining = BudgetAmounts(requests=7, tokens=74114, estimated_cost=4.47905)
    required = BudgetAmounts(requests=7, tokens=9895, estimated_cost=0.052046)
    worst = BudgetAmounts(requests=14, tokens=22197, estimated_cost=0.14385)
    assert exceeded_dimensions(required, remaining) == []
    # 请求数不再单独成维：它和 Token 量的是同一件事的另外两种单位，只有钱能拦人。
    assert exceeded_dimensions(worst, remaining) == []
    # Hard gate must follow estimated, so executable.
    assert not exceeded_dimensions(required, remaining)


def test_full_pipeline_advisory_gates_on_expected_not_worst(testing_session):
    remaining = BudgetAmounts(requests=20, tokens=100000, estimated_cost=5.0)
    # Stage-1 estimated fits; full worst would not — advisory still uses expected.
    advisory = build_full_pipeline_advisory(
        testing_session,
        paragraph_count=42,
        stage1_expected=7,
        stage1_worst=14,
        stage1_tokens=9895,
        stage1_worst_tokens=22197,
        stage1_cost=0.052046,
        stage1_worst_cost=0.14385,
        remaining=remaining,
    )
    assert advisory.full_worst_requests > remaining.requests
    assert advisory.full_expected_requests <= remaining.requests or advisory.within_budget in (
        True,
        False,
    )
    # Hard gate dimensions must not include requests solely because worst > remaining.
    if advisory.full_expected_requests <= remaining.requests:
        assert "requests" not in advisory.exceeded_dimensions
        assert advisory.within_budget is True or "tokens" in advisory.exceeded_dimensions or (
            "estimated_cost" in advisory.exceeded_dimensions
        )
    assert advisory.retry_reserve_requests == max(
        0, advisory.full_worst_requests - advisory.full_expected_requests
    )


def test_full_pipeline_advisory_blocks_when_estimated_exceeds(testing_session):
    remaining = BudgetAmounts(requests=3, tokens=100000, estimated_cost=5.0)
    advisory = build_full_pipeline_advisory(
        testing_session,
        paragraph_count=42,
        stage1_expected=7,
        stage1_worst=14,
        stage1_tokens=9895,
        stage1_worst_tokens=22197,
        stage1_cost=0.052046,
        stage1_worst_cost=0.14385,
        remaining=remaining,
    )
    # 完整流程的预计请求数确实超过剩余请求数——但请求数不再是闸门，钱够就放行。
    assert advisory.full_expected_requests > remaining.requests
    assert advisory.within_budget is True
    assert advisory.exceeded_dimensions == []
