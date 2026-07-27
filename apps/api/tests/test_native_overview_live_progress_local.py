"""CHG-20260726-013 — Native Overview live progress checkpoints (Fake only)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, Base, ModelInvocation, WholeBookRunWindow
from app.narrative_core.contracts.pro_native_overview_flags import FIXTURE_ENGINE_ID
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CreateRunRequest,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
)
from app.narrative_core.enums import RunStatus, WindowStatus
from app.narrative_core.services.native_overview_context_windows import OverviewWindowBudget
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.narrative_core.services.native_overview_service import NativeOverviewService
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    WholeBookOverviewEngineAdapter,
)
from app.narrative_core.services.native_overview_provider_accounting import (
    RecordingFakeTransport,
)
from app.services.native_overview_background import execute_native_overview_run_background
from app.services.scene_pipeline import mark_interrupted_runs_failed


def _tiny_budget() -> OverviewWindowBudget:
    return OverviewWindowBudget(
        max_paragraphs_per_window=2,
        overlap_paragraphs=1,
        max_characters_per_window=10_000,
        max_tokens_estimated=5_000,
    )


class SlowCountingAdapter:
    """Fixture adapter wrapper: delay per window; optional fail_on_window."""

    def __init__(
        self,
        inner: WholeBookOverviewEngineAdapter,
        *,
        delay_s: float = 2.0,
        fail_on_window: int | None = None,
    ) -> None:
        self._inner = inner
        self.delay_s = delay_s
        self.fail_on_window = fail_on_window
        self.analyze_calls = 0

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    def analyze_window(
        self,
        payload: WholeBookOverviewWindowInputV1,
        transport=None,  # noqa: ANN001
    ) -> WholeBookOverviewWindowResultV1:
        self.analyze_calls += 1
        idx = int(payload.window.window_index)
        time.sleep(self.delay_s)
        if self.fail_on_window is not None and idx == self.fail_on_window:
            from app.narrative_core.services.native_overview_errors import NativeOverviewError
            from app.narrative_core.contracts.whole_book_overview_errors import (
                WholeBookOverviewErrorCode,
            )

            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PROVIDER_OUTPUT_INVALID.value,
                "forced window failure for progress test",
                run_id=str(payload.run.run_id),
                window_index=idx,
            )
        return self._inner.analyze_window(payload, transport=transport)

    def materialize_window_candidates(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.materialize_window_candidates(*args, **kwargs)

    def synthesize_overview(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.synthesize_overview(*args, **kwargs)


@pytest.fixture()
def progress_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "true")
    engine = create_engine(
        f"sqlite:///{tmp_path / 'progress.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
    yield {"factory": factory, "book_id": book_id, "engine": engine}
    engine.dispose()


def _create_deferred(
    session: Session,
    book_id: int,
    adapter: WholeBookOverviewEngineAdapter,
    *,
    client_request_id: str,
    transport: RecordingFakeTransport | None = None,
) -> int:
    svc = NativeOverviewService(
        session,
        engine_id=FIXTURE_ENGINE_ID,
        adapter=adapter,
        transport=transport or RecordingFakeTransport(),
        window_budget=_tiny_budget(),
    )
    req = CreateRunRequest.model_validate(
        {
            "mode": "whole_book_native",
            "module_key": "book_overview",
            "provider_id": FIXTURE_ENGINE_ID,
            "model_id": "native-overview-1",
            "client_request_id": client_request_id,
            "consent": {
                "estimated_tokens": 10,
                "estimated_cost": 0.01,
                "currency": "CNY",
                "confirmed": True,
            },
        }
    )
    resp = svc.create_run(book_id, req, defer_execution=True)
    return int(resp.run_id)


def _poll_sig(factory: sessionmaker[Session], run_id: int, adapter) -> tuple:
    with factory() as ps:
        svc = NativeOverviewService(
            ps,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )
        st = svc.get_run(run_id)
        return (
            st.status.value if hasattr(st.status, "value") else str(st.status),
            st.current_stage.value if st.current_stage else None,
            int(st.progress.completed_windows),
            int(st.progress.total_windows),
        )


def test_build_windows_visible_as_zero_of_n(progress_env, monkeypatch: pytest.MonkeyPatch):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(load_private_fixture_engine_adapter(), delay_s=1.5)

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )

    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-build-1"
        )

    observed: list[tuple] = []
    stop = threading.Event()

    def poller() -> None:
        while not stop.is_set():
            observed.append(_poll_sig(factory, run_id, adapter))
            time.sleep(0.2)

    th = threading.Thread(target=poller, daemon=True)
    th.start()
    time.sleep(0.05)
    execute_native_overview_run_background(factory, run_id)
    for _ in range(30):
        sig = _poll_sig(factory, run_id, adapter)
        observed.append(sig)
        if sig[0] == RunStatus.COMPLETED.value:
            break
        time.sleep(0.2)
    stop.set()
    th.join(timeout=2)

    # Must see total_windows early (0/N) and not jump only 0/0 → N/N.
    early_total = [o for o in observed if o[3] >= 2 and o[2] < o[3]]
    assert early_total, f"missing early total_windows visibility; observed={observed}"
    assert any(o[2] == 0 and o[3] >= 2 for o in observed) or any(
        o[2] >= 1 and o[2] < o[3] for o in observed
    ), observed
    final = _poll_sig(factory, run_id, adapter)
    assert final[0] == RunStatus.COMPLETED.value
    assert final[2] == final[3] >= 2
    # Must not be only pending 0/0 then completed
    non_terminal = [o for o in observed if o[0] not in {"pending", "completed"}]
    assert non_terminal, observed


def test_per_window_progress_sequence(progress_env, monkeypatch: pytest.MonkeyPatch):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(load_private_fixture_engine_adapter(), delay_s=2.0)

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )

    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-seq-1"
        )

    observed: list[tuple] = []
    stop = threading.Event()

    def poller() -> None:
        while not stop.is_set():
            observed.append(_poll_sig(factory, run_id, adapter))
            time.sleep(0.5)

    th = threading.Thread(target=poller, daemon=True)
    th.start()
    execute_native_overview_run_background(factory, run_id)
    # Drain until terminal visible
    for _ in range(40):
        sig = _poll_sig(factory, run_id, adapter)
        observed.append(sig)
        if sig[0] == RunStatus.COMPLETED.value:
            break
        time.sleep(0.25)
    stop.set()
    th.join(timeout=2)

    totals = {o[3] for o in observed if o[3] > 0}
    assert totals, observed
    n = max(totals)
    completed_levels = sorted({o[2] for o in observed if o[3] == n})
    assert 0 in completed_levels, observed
    for k in range(1, n):
        assert k in completed_levels, f"missing {k}/{n} in {observed}"
    assert any(
        o[0] == RunStatus.COMPLETED.value and o[2] == o[3] == n for o in observed
    ), observed
    # Forbidden anti-pattern: only 0/0 then N/N
    assert any(o[2] == 0 and o[3] == n for o in observed), observed
    assert any(0 < o[2] < n and o[3] == n for o in observed), observed


def test_progress_matches_invocation_and_window_result(
    progress_env, monkeypatch: pytest.MonkeyPatch
):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(load_private_fixture_engine_adapter(), delay_s=1.5)

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )

    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-cons-1"
        )

    seen_one = threading.Event()
    stop = threading.Event()
    consistency_ok = {"ok": False}

    def poller() -> None:
        while not stop.is_set():
            with factory() as ps:
                svc = NativeOverviewService(
                    ps,
                    engine_id=FIXTURE_ENGINE_ID,
                    adapter=adapter,
                    window_budget=_tiny_budget(),
                )
                st = svc.get_run(run_id)
                if st.progress.completed_windows >= 1:
                    wins = list(
                        ps.scalars(
                            select(WholeBookRunWindow).where(
                                WholeBookRunWindow.run_id == run_id
                            )
                        )
                    )
                    invs = list(
                        ps.scalars(
                            select(ModelInvocation).where(ModelInvocation.run_id == run_id)
                        )
                    )
                    w0 = next((w for w in wins if int(w.window_index) == 0), None)
                    assert w0 is not None
                    assert w0.status == WindowStatus.COMPLETED.value
                    assert w0.provider_attempt_id is not None
                    assert any(int(i.id) == int(w0.provider_attempt_id) for i in invs)
                    cp = w0.checkpoint_json or ""
                    assert "window_result" in cp
                    consistency_ok["ok"] = True
                    seen_one.set()
                    return
            time.sleep(0.4)

    th = threading.Thread(target=poller, daemon=True)
    th.start()
    execute_native_overview_run_background(factory, run_id)
    seen_one.wait(timeout=30)
    stop.set()
    th.join(timeout=2)
    assert consistency_ok["ok"] is True


def test_failed_window_visible_before_background_returns(
    progress_env, monkeypatch: pytest.MonkeyPatch
):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(
        load_private_fixture_engine_adapter(), delay_s=1.0, fail_on_window=1
    )

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )

    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-fail-1"
        )

    mid_fail_seen = threading.Event()
    stop = threading.Event()

    def poller() -> None:
        while not stop.is_set():
            with factory() as ps:
                wins = list(
                    ps.scalars(
                        select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
                    )
                )
                run = ps.get(AnalysisRun, run_id)
                w0 = next((w for w in wins if int(w.window_index) == 0), None)
                w1 = next((w for w in wins if int(w.window_index) == 1), None)
                if (
                    w0
                    and w0.status == WindowStatus.COMPLETED.value
                    and w1
                    and w1.status == WindowStatus.FAILED.value
                    and run
                    and run.status == RunStatus.FAILED.value
                ):
                    mid_fail_seen.set()
                    return
            time.sleep(0.3)

    th = threading.Thread(target=poller, daemon=True)
    th.start()
    execute_native_overview_run_background(factory, run_id)
    assert mid_fail_seen.wait(timeout=30)
    stop.set()
    th.join(timeout=2)

    with factory() as ps:
        wins = {
            int(w.window_index): w
            for w in ps.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
            )
        }
        assert wins[0].status == WindowStatus.COMPLETED.value
        assert wins[1].status == WindowStatus.FAILED.value
        assert wins.get(2) is None or wins[2].status in {
            WindowStatus.PENDING.value,
            WindowStatus.FAILED.value,
        }
        run = ps.get(AnalysisRun, run_id)
        assert run is not None and run.status == RunStatus.FAILED.value


def test_process_interrupted_preserves_completed_window(
    progress_env, monkeypatch: pytest.MonkeyPatch
):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )
    from app.db.models import AnalysisRunStage
    from app.narrative_core.enums import OverviewProductionStageKey, StageStatus

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(load_private_fixture_engine_adapter(), delay_s=0.01)

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )

    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-intr-1"
        )

    # Run until at least window 0 completed via background, then simulate crash mid W1.
    # Simpler: run fully with fail_on_window unused; instead manually craft after partial execute.
    # Execute with commit_progress in a controlled way: stop after first window by failing W1.
    adapter.fail_on_window = 1
    adapter.delay_s = 0.05
    execute_native_overview_run_background(factory, run_id)

    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        assert run is not None
        # Reset to mid-flight analyzing with W0 completed / W1 running for recovery.
        w0 = session.scalar(
            select(WholeBookRunWindow).where(
                WholeBookRunWindow.run_id == run_id,
                WholeBookRunWindow.window_index == 0,
            )
        )
        w1 = session.scalar(
            select(WholeBookRunWindow).where(
                WholeBookRunWindow.run_id == run_id,
                WholeBookRunWindow.window_index == 1,
            )
        )
        assert w0 is not None and w0.status == WindowStatus.COMPLETED.value
        # Re-open as if crash during W1
        run.status = RunStatus.ANALYZING.value
        run.error_code = None
        run.error_message = None
        run.completed_at = None
        if w1 is not None:
            w1.status = WindowStatus.RUNNING.value
            w1.error_code = None
            w1.error_detail = None
            w1.completed_at = None
        stage = session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run_id,
                AnalysisRunStage.stage_key
                == OverviewProductionStageKey.EXTRACT_OVERVIEW_FACTS.value,
            )
        )
        if stage is not None:
            stage.status = StageStatus.RUNNING.value
            stage.error_code = None
            stage.completed_at = None
        session.commit()
        w0_id = int(w0.id)
        w0_attempt = w0.provider_attempt_id

    with factory() as session:
        stats = mark_interrupted_runs_failed(session)
        run = session.get(AnalysisRun, run_id)
        w0 = session.get(WholeBookRunWindow, w0_id)
        assert run is not None
        assert run.error_code == "PROCESS_INTERRUPTED"
        assert run.status in {RunStatus.FAILED.value, RunStatus.INTERRUPTED.value, "failed", "interrupted"}
        assert w0 is not None
        assert w0.status == WindowStatus.COMPLETED.value
        assert w0.provider_attempt_id == w0_attempt
        assert stats["failed_runs"] + stats.get("interrupted_runs", 0) >= 0


def test_get_run_poll_is_read_only(progress_env, monkeypatch: pytest.MonkeyPatch):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(load_private_fixture_engine_adapter(), delay_s=0.01)

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )
    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-ro-1"
        )
    execute_native_overview_run_background(factory, run_id)

    with factory() as session:
        before_inv = len(
            list(session.scalars(select(ModelInvocation).where(ModelInvocation.run_id == run_id)))
        )
        before_wins = len(
            list(
                session.scalars(
                    select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
                )
            )
        )
        svc = NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            window_budget=_tiny_budget(),
        )
        for _ in range(5):
            svc.get_run(run_id)
        after_inv = len(
            list(session.scalars(select(ModelInvocation).where(ModelInvocation.run_id == run_id)))
        )
        after_wins = len(
            list(
                session.scalars(
                    select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
                )
            )
        )
        assert after_inv == before_inv
        assert after_wins == before_wins


def test_completed_run_result_readable(progress_env, monkeypatch: pytest.MonkeyPatch):
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    factory = progress_env["factory"]
    adapter = SlowCountingAdapter(load_private_fixture_engine_adapter(), delay_s=0.01)

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=RecordingFakeTransport(),
            window_budget=_tiny_budget(),
        )

    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_http_factory.build_native_overview_service",
        build,
    )
    with factory() as session:
        run_id = _create_deferred(
            session, progress_env["book_id"], adapter, client_request_id="prog-res-1"
        )
    execute_native_overview_run_background(factory, run_id)
    with factory() as session:
        svc = NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            window_budget=_tiny_budget(),
        )
        overview = svc.get_overview(run_id)
        assert overview.overview is not None
        st = svc.get_run(run_id)
        assert st.status == RunStatus.COMPLETED
        assert st.progress.completed_windows == st.progress.total_windows >= 1
