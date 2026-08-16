"""重新分析 V2 → RunCoordinator, for books whose profile is confirmed.

Until this wire existed, nothing in the product called ``RunCoordinator``. Every result the
long-novel engine had ever produced was inserted into the database by hand, which meant the
engine's quality and the product's behaviour were two unrelated facts. These tests hold the
one property that closes that gap: pressing the button on a confirmed book reaches the new
engine, and pressing it on an unconfirmed one does not.

The gateway is a queue of canned responses, so the whole pipeline runs end to end for free.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import sessionmaker

from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.long_novel.profile_repository import BookProfileRepository
from app.narrative_core.services.long_novel_pipeline_v1 import (
    ENGINE_ID,
    book_uses_long_novel_engine,
)
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1
from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
    execute_hierarchical_v2_pipeline_v1,
)
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


AXES = {
    "monetization": {"value": "paid_subscription", "source": "confirmed"},
    "audience": {"value": "male_gratification", "source": "confirmed"},
    "engine": {"value": "progression", "source": "confirmed"},
    "pov": {"value": "single_lead", "source": "confirmed"},
    "length": {"value": "long", "source": "confirmed"},
}


class _ScriptedGateway:
    """Answers every unit with a shape the engine can parse, and records what was asked."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, provider, request):  # noqa: ANN001
        prompt = "".join(str(m.get("content", "")) for m in request.messages)
        self.calls.append(prompt[:40])
        return ModelResponse(
            text=json.dumps(self._answer(prompt), ensure_ascii=False),
            model="scripted",
            finish_reason="stop",
            input_tokens=100,
            output_tokens=50,
        )

    @staticmethod
    def _answer(prompt: str) -> dict:
        if "chapter_signals" in prompt:
            # One L1 block. The chapter refs are read back out of the rendered text, so the
            # block must answer for exactly the chapters it was shown.
            refs = sorted({int(n) for n in _chapter_refs(prompt)})
            return {
                "chapter_signals": [
                    {"chapter_ref": ref, "dialogue_paragraphs": 3, "action_paragraphs": 2,
                     "interiority_paragraphs": 1, "scene_breaks": 1, "new_information_beats": 2,
                     "hook_present": True, "evidence": [{"paragraph_ref": 1}]}
                    for ref in refs
                ],
                "events": [
                    {"summary": "主角登台", "actors": ["陈伶"], "chapter_ref": refs[0],
                     "evidence": [{"paragraph_ref": 1}]}
                ],
                "character_state_changes": [],
                "causal_links": [],
                "suspense_threads": [
                    {"question": "戏神是谁", "opened_chapter_ref": refs[0],
                     "evidence": [{"paragraph_ref": 1}]}
                ],
                "suspense_actions": [
                    {"thread_ref": "戏神是谁", "action_kind": "reveal", "information_added": "他就是",
                     "chapter_ref": refs[0], "evidence": [{"paragraph_ref": 1}]}
                ],
                "relationship_changes": [],
                "goal_changes": [],
                "choices": [],
                "power_beats": [
                    {"entity_ref": "陈伶", "chapter_ref": refs[0], "kind": "promote",
                     "level": "一阶", "why": "登临第一阶", "evidence": [{"paragraph_ref": 1}]}
                ],
                "identity_assertions": [],
                "mentions": [{"surface_norm": "陈伶", "paragraph_ref": 1,
                              "evidence": [{"paragraph_ref": 1}]}],
                "provisional_entities": [
                    {"member_mention_indexes": [0], "display_surface_norm": "陈伶", "role_hint": "主角"}
                ],
                "carry_forward_out": {"open_thread_refs": [], "active_goal_refs": [],
                                      "active_continuity_refs": [], "unresolved_note": ""},
            }
        if "suspense_hooks" in prompt or "event_causality" in prompt:
            # The window schema forbids extras, so the stage answer below cannot stand in for
            # it — every key it does not declare fails validation before the engine sees it.
            # evidence_ids must come from the catalog the prompt carries: the engine rejects
            # an extraction that cites nothing, which is the rule that keeps a window answer
            # anchored to the text rather than to the model's memory of it.
            import re as _re

            found = _re.findall(r"E-\d+-\d+", prompt)
            return {
                "events": ["主角登台"],
                "characters": ["陈伶"],
                "protagonist_goals": ["成名"],
                "suspense_hooks": ["戏神是谁"],
                "evidence_ids": found[:1],
            }
        return {"title": "一段", "summary": "主角登台", "stage_goal": "成名",
                "core_conflict": "无人识得", "major_choice": "登台", "protagonist_state": "紧张"}


def _chapter_refs(prompt: str) -> list[str]:
    import re

    return re.findall(r"===\s*第\s*(\d+)\s*章", prompt) or ["1"]


def _seed(session):
    # 4 chapters, not the helper's default 3. `book_uses_long_novel_engine` requires at
    # least MIN_VIABLE_CHAPTERS_PER_BLOCK (4) because the planner works in blocks and a book
    # it cannot plan stays on the old engine. With 3 the predicate correctly answers False,
    # so these tests were asserting against a floor they never cleared — the failure was the
    # fixture, not the dispatch rule.
    book, snap_id = seed_sample_s_book(session, chapter_count=4)
    run = create_whole_book_run_v1(
        session, book.id, snap_id, "whole_book_native", "long-novel-dispatch", "formal"
    )
    run.provider_name = "fake"
    run.model_name = "fixture"
    session.commit()
    session.refresh(run)
    return book, run


def test_an_unconfirmed_book_does_not_take_the_new_engine(tmp_path):
    engine = make_engine(tmp_path, "ln-dispatch-unconfirmed.db")
    with sessionmaker(bind=engine)() as session:
        book, _ = _seed(session)
        assert book_uses_long_novel_engine(session, int(book.id)) is False


def test_a_draft_profile_is_not_enough(tmp_path):
    # INV-P2: inference never outranks a person. A draft is the engine's guess, and acting on
    # it would spend money on deltas and change the report's shape without anyone agreeing.
    engine = make_engine(tmp_path, "ln-dispatch-draft.db")
    with sessionmaker(bind=engine)() as session:
        book, _ = _seed(session)
        BookProfileRepository(session).save_draft(int(book.id), AXES)
        session.commit()
        assert book_uses_long_novel_engine(session, int(book.id)) is False


def test_a_confirmed_book_is_dispatched_to_the_long_novel_engine(tmp_path):
    engine = make_engine(tmp_path, "ln-dispatch-confirmed.db")
    with sessionmaker(bind=engine)() as session:
        book, run = _seed(session)
        repo = BookProfileRepository(session)
        repo.save_draft(int(book.id), AXES)  # confirm updates a drafted row
        repo.confirm(int(book.id), AXES)
        session.commit()
        assert book_uses_long_novel_engine(session, int(book.id)) is True

        gateway = _ScriptedGateway()
        out = execute_hierarchical_v2_pipeline_v1(
            session, int(run.id), use_fake_gateway=gateway
        )
        session.commit()

        assert out["pipeline"] == "long_novel_engine"
        assert out["engine_id"] == ENGINE_ID
        assert out["provider_calls"] >= 1
        assert gateway.calls, "the run must actually reach a provider"

        session.refresh(run)
        assert run.status == WholeBookRunStatus.completed.value
        assert run.engine_id == ENGINE_ID

        loaded = WholeBookV2Repository(session).load_result(int(run.id))
        assert loaded is not None
        assert loaded.schema_version == "whole-book-analysis-v2.0"
        assert loaded.analysis_metadata.pipeline_version == "long-novel-engine-1.0"
        assert loaded.pacing.points


def test_the_confirmed_profile_chooses_the_journey_axis(tmp_path):
    # engine=progression must reach the document as a ladder. This is the whole chain in one
    # assertion: confirmed axis → delta → extracted power_beats → journey section → contract.
    engine = make_engine(tmp_path, "ln-dispatch-journey.db")
    with sessionmaker(bind=engine)() as session:
        book, run = _seed(session)
        repo = BookProfileRepository(session)
        repo.save_draft(int(book.id), AXES)  # confirm updates a drafted row
        repo.confirm(int(book.id), AXES)
        session.commit()
        out = execute_hierarchical_v2_pipeline_v1(
            session, int(run.id), use_fake_gateway=_ScriptedGateway()
        )
        session.commit()
        assert out["journey_axis"] == "ladder"
        loaded = WholeBookV2Repository(session).load_result(int(run.id))
        assert loaded.journey.axis == "ladder"
        assert loaded.journey.lead == "陈伶"
        assert loaded.journey.points


def test_the_run_reports_progress_while_it_works(tmp_path):
    """The gap a user actually hit: the run worked and the page said 无法读取数据.

    ``/v2/progress`` reads a checkpoint the *hierarchical* engine writes. This pipeline wrote
    none, so the endpoint 404'd for the whole run and the client flipped between "loading" and
    "cannot read". The run was fine; nothing was reporting it.
    """
    from app.narrative_core.whole_book_v2.contracts import V2_STAGES

    engine = make_engine(tmp_path, "ln-dispatch-progress.db")
    with sessionmaker(bind=engine)() as session:
        book, run = _seed(session)
        repo = BookProfileRepository(session)
        repo.save_draft(int(book.id), AXES)
        repo.confirm(int(book.id), AXES)
        session.commit()

        execute_hierarchical_v2_pipeline_v1(session, int(run.id), use_fake_gateway=_ScriptedGateway())
        session.commit()

        progress = WholeBookV2Repository(session).load_progress(int(run.id))
        assert progress is not None, "the endpoint would 404 without this"
        assert progress.current_stage == "complete"
        assert progress.current_stage in V2_STAGES  # a stage the client has a label for
        assert progress.overall_percent == 100.0
        assert progress.provider_calls_completed >= 1
        assert progress.total_chapters == progress.current_chapter


def test_progress_is_written_during_the_run_not_only_at_the_end(tmp_path):
    seen: list[tuple[str, float, int]] = []

    class _Watching(_ScriptedGateway):
        def __init__(self, session, run_id):
            super().__init__()
            self._session, self._run_id = session, run_id

        async def generate(self, provider, request):
            response = await super().generate(provider, request)
            row = WholeBookV2Repository(self._session).load_progress(self._run_id)
            if row is not None:
                seen.append((row.current_stage, row.overall_percent, row.provider_calls_completed))
            return response

    engine = make_engine(tmp_path, "ln-dispatch-progress-live.db")
    with sessionmaker(bind=engine)() as session:
        book, run = _seed(session)
        repo = BookProfileRepository(session)
        repo.save_draft(int(book.id), AXES)
        repo.confirm(int(book.id), AXES)
        session.commit()
        execute_hierarchical_v2_pipeline_v1(
            session, int(run.id), use_fake_gateway=_Watching(session, int(run.id))
        )
        session.commit()

    assert seen, "no progress was visible at any point during the run"
    # It moves, and it moves because calls completed — not because a stage flipped.
    assert seen[-1][2] > seen[0][2]
    assert seen[-1][1] >= seen[0][1]
    assert any(stage == "extract_windows" for stage, _, _ in seen)


def test_the_estimate_describes_the_engine_that_will_actually_run():
    """Pinned against two measured runs, because the previous estimate was not.

    The prepare panel showed 12 windows / 30 calls for 《深海余烬》. The run that followed
    made 101 blocks and 114 calls. The token total was close enough that the *cost* looked
    right, which is exactly why the wrong counts survived — so these assertions are against
    the observed block and call counts, not against the code that produced them.
    """
    from app.narrative_core.services.long_novel_pipeline_v1 import estimate_long_novel_plan

    # 《深海余烬》 806 chapters / 2,402,385 chars → observed: 101 blocks, 114 calls.
    deep = estimate_long_novel_plan(chapter_count=806, character_count=2_402_385)
    assert deep["blocks"] == 101
    assert abs(deep["estimated_provider_calls"] - 114) <= 5

    # 《我不是戏神》 1299 chapters / 2,748,792 chars → observed: 163 blocks.
    stage = estimate_long_novel_plan(chapter_count=1299, character_count=2_748_792)
    assert stage["blocks"] == 163

    # A book with no character count must still plan rather than divide by zero.
    assert estimate_long_novel_plan(chapter_count=0, character_count=0)["blocks"] >= 1


def test_the_token_estimate_is_fitted_to_measured_runs():
    """Three complete runs, every figure read from the usage ledger rather than forecast.

    A flat per-character rate under-reported the first two by 12% and 25%, because input is the
    text *plus* a per-call prompt overhead that a character count cannot see. Those two fitted
    the input coefficients exactly, so the agreement was interpolation and this test said the
    third book would be the real test.

    《系统豪横》 is that book, and it moved the model twice. Its input landed inside 5% without
    a refit, which is the validation the note asked for. Its *output* was 25% out, because it is
    the first run whose calls are not overwhelmingly block calls — 57% blocks against 87% for
    《深海余烬》 — and a block call and a bounded synthesis unit do not cost the same thing. They
    are now counted separately, at 2,815 and 421 output tokens.
    """
    from app.narrative_core.services.long_novel_pipeline_v1 import estimate_long_novel_plan

    # 《深海余烬》 806 章 / 2,402,385 字 → 114 calls, 1,885,739 in, 281,485 out, ¥2.449
    deep = estimate_long_novel_plan(chapter_count=806, character_count=2_402_385)
    assert abs(deep["estimated_input_tokens"] - 1_885_739) / 1_885_739 < 0.05
    assert abs(deep["estimated_output_tokens"] - 281_485) / 281_485 < 0.10

    # 《凶宅笔记》 277 章 / 797,953 字 → 46 calls, 671,493 in, 104,393 out, ¥0.880
    house = estimate_long_novel_plan(chapter_count=277, character_count=797_953)
    assert abs(house["estimated_input_tokens"] - 671_493) / 671_493 < 0.05
    assert abs(house["estimated_output_tokens"] - 104_393) / 104_393 < 0.10

    # 《系统豪横》 84 章 / 195,269 字 → 21 calls (12 block + 9 unit), 208,590 in, 39,840 out.
    # The short book is where a per-call blended rate breaks, so it is the one that has to hold.
    system = estimate_long_novel_plan(chapter_count=84, character_count=195_269)
    assert abs(system["estimated_input_tokens"] - 208_590) / 208_590 < 0.05
    assert abs(system["estimated_output_tokens"] - 39_840) / 39_840 < 0.10

    # The old flat model's failure, kept as the thing not to regress to: characters alone
    # cannot produce both books' input, because the overhead differs by call count.
    assert deep["estimated_input_tokens"] / 2_402_385 != house["estimated_input_tokens"] / 797_953


def test_a_book_with_no_text_still_yields_a_usable_estimate():
    from app.narrative_core.services.long_novel_pipeline_v1 import estimate_long_novel_plan

    plan = estimate_long_novel_plan(chapter_count=0, character_count=0)
    assert plan["blocks"] >= 1
    assert plan["estimated_input_tokens"] > 0
    assert plan["estimated_output_tokens"] > 0


def test_the_cost_band_contains_what_the_two_runs_actually_cost():
    """Priced through the estimator's own function, not by scaling its total.

    Scaling the hierarchical cost by a token ratio left 7–8% short: the two engines have
    different input-to-output mixes and the two are priced differently, so one multiplier
    cannot carry both. Both measured spends now fall inside the band.
    """
    from app.narrative_core.services.long_novel_pipeline_v1 import estimate_long_novel_plan
    from app.narrative_core.services.whole_book_cost_estimate_service import (
        estimate_pre_run_cost_cny,
    )

    for chapters, chars, spent in ((806, 2_402_385, 2.4487), (277, 797_953, 0.8803)):
        plan = estimate_long_novel_plan(chapter_count=chapters, character_count=chars)
        low, high, failed = estimate_pre_run_cost_cny(
            "deepseek-v4-flash",
            estimated_input_tokens=plan["estimated_input_tokens"],
            estimated_output_tokens_min=round(plan["estimated_output_tokens"] * 0.85),
            estimated_output_tokens_max=round(plan["estimated_output_tokens"] * 1.25),
        )
        assert not failed and low is not None and high is not None
        assert float(low) <= spent <= float(high), (
            f"{chapters} 章 / {chars} 字：实付 {spent} 不在 {float(low):.3f}–{float(high):.3f} 区间内"
        )
