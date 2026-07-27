"""Zero-cost proof: mid-run other Session cannot see window progress until background commit."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

db = Path(os.environ["TEMP"]) / "storylens-forensic-progress.db"
if db.exists():
    db.unlink()
os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["PRO_NATIVE_OVERVIEW_ENABLED"] = "true"

from app.db.models import (  # noqa: E402
    AnalysisRun,
    Base,
    ModelInvocation,
    WholeBookRunWindow,
)
from app.narrative_core.contracts.pro_native_overview_flags import FIXTURE_ENGINE_ID  # noqa: E402
from app.narrative_core.contracts.whole_book_overview_v1 import CreateRunRequest  # noqa: E402
from app.narrative_core.services.native_overview_provider_accounting import (  # noqa: E402
    RecordingFakeTransport,
)
from app.narrative_core.services.native_overview_seed import seed_short_book_v1  # noqa: E402
from app.narrative_core.services.native_overview_service import NativeOverviewService  # noqa: E402
from app.services.native_overview_background import (  # noqa: E402
    execute_native_overview_run_background,
)

engine = create_engine(
    os.environ["STORYLENS_DATABASE_URL"],
    connect_args={"check_same_thread": False},
)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class SlowFake(RecordingFakeTransport):
    def request(self, prompt, model_options=None):  # noqa: ANN001
        time.sleep(1.5)
        return super().request(prompt, model_options)


transport = SlowFake(default_input_tokens=10, default_output_tokens=5, default_cost=0.0)

with SessionLocal() as s:
    book = seed_short_book_v1(s)
    s.commit()
    book_id = int(book.id)

import app.narrative_core.services.native_overview_http_factory as fac  # noqa: E402


def build(session, provider_id=None, model_id=None):  # noqa: ANN001
    return NativeOverviewService(session, engine_id=FIXTURE_ENGINE_ID, transport=transport)


fac.build_native_overview_service = build

with SessionLocal() as s:
    svc = NativeOverviewService(s, engine_id=FIXTURE_ENGINE_ID, transport=transport)
    req = CreateRunRequest.model_validate(
        {
            "mode": "whole_book_native",
            "module_key": "book_overview",
            "provider_id": FIXTURE_ENGINE_ID,
            "model_id": "native-overview-1",
            "client_request_id": "forensic-progress-1",
            "consent": {
                "estimated_tokens": 10,
                "estimated_cost": 0.01,
                "currency": "CNY",
                "confirmed": True,
            },
        }
    )
    resp = svc.create_run(book_id, req, defer_execution=True)
    run_id = int(resp.run_id)
    print("CREATED", run_id, resp.status)

observations: list[dict] = []
stop = threading.Event()


def poller() -> None:
    while not stop.is_set():
        with SessionLocal() as ps:
            psvc = NativeOverviewService(
                ps, engine_id=FIXTURE_ENGINE_ID, transport=transport
            )
            st = psvc.get_run(run_id)
            wins = list(ps.query(WholeBookRunWindow).filter_by(run_id=run_id).all())
            invs = list(ps.query(ModelInvocation).filter_by(run_id=run_id).all())
            run = ps.get(AnalysisRun, run_id)
            observations.append(
                {
                    "status": st.status.value if hasattr(st.status, "value") else str(st.status),
                    "stage": st.current_stage.value if st.current_stage else None,
                    "completed": st.progress.completed_windows,
                    "total": st.progress.total_windows,
                    "db_run_status": run.status if run else None,
                    "win_rows": len(wins),
                    "win_completed": sum(1 for w in wins if w.status == "completed"),
                    "inv_rows": len(invs),
                }
            )
        time.sleep(0.5)


th = threading.Thread(target=poller, daemon=True)
th.start()
time.sleep(0.2)
execute_native_overview_run_background(
    SessionLocal,
    run_id,
    provider_id=FIXTURE_ENGINE_ID,
    model_id="native-overview-1",
)
time.sleep(0.5)
stop.set()
th.join(timeout=2)

prev = None
print("=== POLL VISIBILITY (other Session) ===")
for o in observations:
    sig = (
        o["status"],
        o["stage"],
        o["completed"],
        o["total"],
        o["win_rows"],
        o["win_completed"],
        o["inv_rows"],
    )
    if sig != prev:
        print(sig)
        prev = sig
print("transport_calls", transport.call_count)
print("REAL_PROVIDER_CALLS", 0)
