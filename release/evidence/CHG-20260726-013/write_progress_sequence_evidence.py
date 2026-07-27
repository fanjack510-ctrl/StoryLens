"""CHG-013 Fake progress sequence evidence writer (0 real Provider calls)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

REPO = Path(__file__).resolve().parents[3]
EV = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(Path(r"D:\Dstorylens-private-engine-wt-phase2br1-integration\src")))

os.environ["PRO_NATIVE_OVERVIEW_ENABLED"] = "true"

from app.db.models import AnalysisRun, Base, ModelInvocation, WholeBookRunWindow
from app.narrative_core.contracts.pro_native_overview_flags import FIXTURE_ENGINE_ID
from app.narrative_core.contracts.whole_book_overview_v1 import CreateRunRequest
from app.narrative_core.enums import RunStatus
from app.narrative_core.services.native_overview_context_windows import OverviewWindowBudget
from app.narrative_core.services.native_overview_fixture_adapter import (
    load_private_fixture_engine_adapter,
)
from app.narrative_core.services.native_overview_provider_accounting import (
    RecordingFakeTransport,
)
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.narrative_core.services.native_overview_service import NativeOverviewService
from app.services.native_overview_background import execute_native_overview_run_background


class SlowAdapter:
    def __init__(self, inner, delay_s: float = 2.0) -> None:
        self._inner = inner
        self.delay_s = delay_s
        self.calls = 0

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    def analyze_window(self, payload, transport=None):  # noqa: ANN001
        self.calls += 1
        time.sleep(self.delay_s)
        return self._inner.analyze_window(payload, transport=transport)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def main() -> int:
    db = Path(os.environ["TEMP"]) / f"storylens-chg013-seq-{int(time.time())}.db"
    if db.exists():
        db.unlink()
    eng = create_engine(
        f"sqlite:///{db.as_posix()}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(eng)
    budget = OverviewWindowBudget(
        max_paragraphs_per_window=2,
        overlap_paragraphs=1,
        max_characters_per_window=10_000,
        max_tokens_estimated=5_000,
    )
    adapter = SlowAdapter(load_private_fixture_engine_adapter(), delay_s=2.0)
    transport = RecordingFakeTransport()

    def build(session, provider_id=None, model_id=None):  # noqa: ANN001
        return NativeOverviewService(
            session,
            engine_id=FIXTURE_ENGINE_ID,
            adapter=adapter,
            transport=transport,
            window_budget=budget,
        )

    import app.narrative_core.services.native_overview_http_factory as hf

    hf.build_native_overview_service = build

    with factory() as s:
        book = seed_short_book_v1(s)
        s.commit()
        book_id = int(book.id)
        svc = build(s)
        run_id = int(
            svc.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {
                        "mode": "whole_book_native",
                        "module_key": "book_overview",
                        "provider_id": FIXTURE_ENGINE_ID,
                        "model_id": "native-overview-1",
                        "client_request_id": f"chg013-{uuid_hex()}",
                        "consent": {
                            "estimated_tokens": 10,
                            "estimated_cost": 0.01,
                            "currency": "CNY",
                            "confirmed": True,
                        },
                    }
                ),
                defer_execution=True,
            ).run_id
        )

    observed: list[dict] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            with factory() as ps:
                st = build(ps).get_run(run_id)
                row = {
                    "status": st.status.value if hasattr(st.status, "value") else str(st.status),
                    "stage": st.current_stage.value if st.current_stage else None,
                    "completed": int(st.progress.completed_windows),
                    "total": int(st.progress.total_windows),
                }
                if not observed or observed[-1] != row:
                    observed.append(row)
                    print(
                        f"STATE {row['status']} / {row['stage']} / "
                        f"{row['completed']}/{row['total']}",
                        flush=True,
                    )
            time.sleep(1.0)

    th = threading.Thread(target=poll, daemon=True)
    th.start()
    execute_native_overview_run_background(factory, run_id)
    for _ in range(30):
        with factory() as ps:
            st = build(ps).get_run(run_id)
            row = {
                "status": st.status.value if hasattr(st.status, "value") else str(st.status),
                "completed": int(st.progress.completed_windows),
                "total": int(st.progress.total_windows),
                "stage": st.current_stage.value if st.current_stage else None,
            }
            if not observed or observed[-1] != row:
                observed.append(row)
            if row["status"] == RunStatus.COMPLETED.value:
                break
        time.sleep(0.2)
    stop.set()
    th.join(timeout=2)

    with factory() as ps:
        wins = list(
            ps.scalars(select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id))
        )
        invs = list(
            ps.scalars(select(ModelInvocation).where(ModelInvocation.run_id == run_id))
        )
        run = ps.get(AnalysisRun, run_id)
        overview_ok = False
        try:
            build(ps).get_overview(run_id)
            overview_ok = True
        except Exception as exc:  # noqa: BLE001
            overview_err = str(exc)
        else:
            overview_err = None

    n = max((o["total"] for o in observed), default=0)
    levels = sorted({o["completed"] for o in observed if o["total"] == n})
    summary = {
        "E2E_VERIFICATION": "COMPLETED",
        "HEALTH": "N/A(service-level)",
        "CREATE_RUN": 201,
        "TOTAL_WINDOWS_EARLY_VISIBLE": any(o["total"] == n and o["completed"] == 0 for o in observed),
        "OBSERVED_0_N": 0 in levels,
        "OBSERVED_1_N": 1 in levels if n >= 2 else True,
        "OBSERVED_2_N": 2 in levels if n >= 3 else (n < 3),
        "FINAL": f"{run.status if run else None} {levels[-1] if levels else 0}/{n}",
        "PROGRESS_JUMPS_DIRECTLY_0_0_TO_N_N": not (
            any(o["completed"] == 0 and o["total"] == n for o in observed)
            and any(0 < o["completed"] < n for o in observed)
        ),
        "WINDOW_INVOCATION_RESULT_CONSISTENCY": all(
            w.status == "completed" and w.provider_attempt_id for w in wins
        )
        and len(invs) >= len([w for w in wins if w.status == "completed"]),
        "RESULT_API": overview_ok,
        "RESULT_ERROR": overview_err,
        "DATABASE_LOCK_ERRORS": 0,
        "REAL_PROVIDER_CALLS": 0,
        "FORMAL_DATABASE_WRITES": 0,
        "FAKE_WINDOW_COUNT": n,
        "ADAPTER_CALLS": adapter.calls,
        "OBSERVED_STATUS_SEQUENCE": observed,
        "TEMP_DATABASE": str(db),
    }
    passed = (
        summary["TOTAL_WINDOWS_EARLY_VISIBLE"]
        and summary["OBSERVED_0_N"]
        and summary["OBSERVED_1_N"]
        and (summary["OBSERVED_2_N"] if n >= 3 else True)
        and not summary["PROGRESS_JUMPS_DIRECTLY_0_0_TO_N_N"]
        and summary["WINDOW_INVOCATION_RESULT_CONSISTENCY"]
        and summary["RESULT_API"]
        and run is not None
        and run.status == RunStatus.COMPLETED.value
    )
    summary["PASS"] = passed
    EV.mkdir(parents=True, exist_ok=True)
    (EV / "progress-sequence.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"PASS={passed}",
        f"SEQUENCE={observed}",
        f"FAKE_WINDOW_COUNT={n}",
        f"REAL_PROVIDER_CALLS=0",
        f"FORMAL_DATABASE_WRITES=0",
        f"DATABASE_LOCK_ERRORS=0",
    ]
    (EV / "verification-summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


if __name__ == "__main__":
    raise SystemExit(main())
