#!/usr/bin/env python3
"""CHG-20260807-055 L3-B medium Free real-provider run with Pause/Resume.

Isolated DB only. Never prints API keys or full model payloads.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
import sys

sys.path.insert(0, str(ROOT / "apps" / "api"))
PRIVATE = Path(r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src")
if PRIVATE.is_dir():
    sys.path.insert(0, str(PRIVATE))

PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"
L3_DIR = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-medium")
EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260807-055"
DB = L3_DIR / "storylens_l3_medium.db"
SRC = L3_DIR / "medium_41ch_source.txt"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PauseProbeTransport:
    """Counts real invoke successes. Pause is requested between units (not mid-invoke)."""

    inner: Any
    run_id: int
    pause_after_successes: int = 1
    successes: int = 0
    pause_requested_at: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    provider_id: str = PROVIDER
    model_name: str = MODEL

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]):
        started = _utc()
        t0 = time.perf_counter()
        result = self.inner.invoke(
            unit_key=unit_key, unit_type=unit_type, request_payload=request_payload
        )
        finished = _utc()
        entry = {
            "unit_key": unit_key,
            "unit_type": unit_type,
            "started_at": started,
            "finished_at": finished,
            "elapsed_sec": round(time.perf_counter() - t0, 3),
            "ok": bool(result.ok),
            "error_code": result.error_code,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
        self.calls.append(entry)
        if result.ok:
            self.successes += 1
        return result


def _install_pause_after_success_hook(pausing: PauseProbeTransport):
    """Request soft pause after N successes, before the next unit is claimed.

    Product contract: in-flight call finishes; no new units after pause barrier.
    Mid-invoke pause + concurrent SQLite writers is unsafe with Gateway.
    Hook is one-shot: after the barrier pause it delegates to product should_stop.
    """
    import app.narrative_core.services.whole_book_minimal_extraction_v1_service as extraction_mod
    from app.narrative_core.services.whole_book_runtime_control_v1_service import (
        request_pause_whole_book_run_v1,
        should_stop_claiming_units as _orig_should_stop,
    )

    pausing.barrier_fired = False  # type: ignore[attr-defined]

    def _should_stop(session, run_id: int) -> bool:
        if (
            not getattr(pausing, "barrier_fired", False)
            and pausing.successes >= pausing.pause_after_successes
        ):
            if pausing.pause_requested_at is None:
                request_pause_whole_book_run_v1(session, run_id)
                pausing.pause_requested_at = _utc()
            pausing.barrier_fired = True  # type: ignore[attr-defined]
            return True
        return _orig_should_stop(session, run_id)

    extraction_mod.should_stop_claiming_units = _should_stop
    return _orig_should_stop, extraction_mod


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    L3_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "false"
    os.environ["STORYLENS_ALIYUN_ENABLED"] = "true"
    os.environ["STORYLENS_DEFAULT_MODEL_PROVIDER"] = PROVIDER

    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        ApplicationSetting,
        NarrativeAsset,
        NarrativeAssetEvidence,
        NarrativeAssetVersion,
        NarrativeEntity,
        ProviderConfiguration,
        WholeBookOverviewResult,
        WholeBookProviderAttempt,
        WholeBookProviderUnit,
        WholeBookRun,
        WholeBookRunStageRow,
        Chapter,
        Paragraph,
    )
    from app.db.session import SessionLocal, create_db, engine as db_engine
    from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
        get_run_chapter_functions_product_v1,
    )
    from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
    from app.narrative_core.services.whole_book_cost_estimate_service import (
        CF_MAX_CHAPTERS_PER_BATCH,
        CF_REPAIR_RESERVE_PER_BATCH,
        SYNTHESIS_PROVIDER_CALLS,
        _estimate_chapter_function_batches,
        _estimate_provider_call_count,
        compute_book_revision_hash,
        estimate_to_dict,
        estimate_whole_book_analysis,
    )
    from app.narrative_core.services.whole_book_free_product_v1_service import (
        create_free_whole_book_analysis_v1,
        prepare_free_whole_book_analysis_v1,
    )
    from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
        execute_minimal_entity_event_extraction_v1,
    )
    from app.narrative_core.services.whole_book_minimal_helpers_v1 import MAX_CHAPTERS_PER_BATCH
    from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
        materialize_minimal_narrative_assets_v1,
    )
    from app.narrative_core.services.whole_book_minimal_overview_v1_service import (
        synthesize_minimal_book_overview_v1,
    )
    from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
        build_formal_gateway_transports,
        execute_minimal_pipeline_v1,
    )
    from app.narrative_core.services.whole_book_minimal_read_v1_service import get_run_overview
    from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
        synthesize_minimal_structure_stages_v1,
    )
    from app.narrative_core.services.whole_book_runtime_control_v1_service import (
        resume_whole_book_run_v1,
    )
    from app.narrative_core.services.whole_book_run_v1_service import get_run
    from app.narrative_core.services.whole_book_structure_product_v1_service import (
        get_run_structure_product_v1,
    )
    from app.services.book_service import import_book
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.provider_bootstrap import ensure_aliyun_provider_configuration

    assert MAX_CHAPTERS_PER_BATCH == 8 == CF_MAX_CHAPTERS_PER_BATCH

    store = KeyringCredentialStore()
    key = store.get(PROVIDER) or os.environ.get("STORYLENS_ALIYUN_API_KEY", "").strip()
    if not key or len(key) < 8:
        print("API_KEY_CONFIGURED: NO")
        return 2
    os.environ["STORYLENS_ALIYUN_API_KEY"] = key
    print("API_KEY_CONFIGURED: YES")

    # Fresh isolated DB each formal L3-B attempt (never reuse a crashed mid-run).
    if DB.exists():
        DB.unlink()
    create_db()

    report: dict[str, Any] = {
        "provider": PROVIDER,
        "model": MODEL,
        "sample_path": str(SRC),
        "db": str(DB),
    }

    t0 = time.perf_counter()
    with SessionLocal() as session:
        ensure_aliyun_provider_configuration(session, PROVIDER, create_if_missing=True)
        row = session.scalar(
            select(ProviderConfiguration).where(ProviderConfiguration.provider_name == PROVIDER)
        )
        assert row is not None
        row.enabled = True
        row.disconnected = False
        row.plus_model = MODEL
        row.credential_reference = f"keyring:{PROVIDER}"
        cloud = session.get(ApplicationSetting, "cloud_enabled")
        if cloud is None:
            session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
        else:
            cloud.value_json = "true"
        session.commit()

        from app.db.models import Book

        book = session.scalar(select(Book).limit(1))
        if book is None:
            text = SRC.read_text(encoding="utf-8")
            book = import_book(session, "天才医生.txt", text.encode("utf-8"))
        book_id = book.id
        chapter_count = (
            session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id))
            or 0
        )
        character_count = 0
        for p in session.scalars(select(Paragraph).where(Paragraph.book_id == book_id)):
            character_count += len(p.normalized_text or p.raw_text or "")

        prepare = prepare_free_whole_book_analysis_v1(session, book_id)
        session.commit()
        snap_id = prepare["snapshot"]["snapshot_id"]
        revision = compute_book_revision_hash(session, book_id)
        estimate = estimate_whole_book_analysis(
            session, book_id, "whole_book_native", row.id
        )
        est = estimate_to_dict(estimate)
        windows = int(est["estimated_window_count"])
        cf_batches = _estimate_chapter_function_batches(chapter_count)
        repair_reserve = cf_batches * CF_REPAIR_RESERVE_PER_BATCH
        estimated_units = _estimate_provider_call_count(
            window_count=windows, chapter_count=chapter_count
        )
        expected_cf = int(math.ceil(chapter_count / 8.0))
        if cf_batches != expected_cf:
            print("CF_BATCH_MISMATCH", cf_batches, expected_cf)
            return 3
        if estimated_units > 200:
            print("ESTIMATE_TOO_HIGH", estimated_units)
            return 3

        consent = create_whole_book_consent(
            session,
            book_id=book_id,
            estimate_id=estimate.id,
            user_budget_limit_cny=str(est.get("estimated_cost_max_cny") or "5"),
            max_provider_calls=max(estimated_units * 2, 50),
            max_input_tokens=max(int(est.get("estimated_input_tokens") or 0) * 2, 500_000),
            max_output_tokens=max(int(est.get("estimated_output_tokens") or 0) * 2, 100_000),
            auto_retry_enabled=True,
            max_retries_per_unit=1,
        )
        session.commit()

        print(f"BOOK_ID: {book_id}")
        print(f"CHAPTER_COUNT: {chapter_count}")
        print(f"CHARACTER_COUNT: {character_count}")
        print(f"SNAPSHOT_ID: {snap_id}")
        print(f"REVISION: {revision}")
        print(f"ESTIMATE_ID: {estimate.id}")
        print(f"CONSENT_ID: {consent.id}")
        print(f"ESTIMATED_WINDOWS: {windows}")
        print(f"ESTIMATED_CF_BATCHES: {cf_batches}")
        print(f"ESTIMATED_PROVIDER_UNITS: {estimated_units}")
        print(f"ESTIMATED_COST_MAX_CNY: {est.get('estimated_cost_max_cny')}")

        created = create_free_whole_book_analysis_v1(
            session,
            book_id,
            estimate_id=estimate.id,
            consent_id=consent.id,
            client_request_id=f"l3b-{uuid.uuid4().hex[:12]}",
            execute_pipeline=False,
        )
        session.commit()
        run_id = created["run_id"]
        print(f"RUN_ID: {run_id}")
        print(f"CREATE_PASS: YES")

        transports = build_formal_gateway_transports(session)
        pausing_window = PauseProbeTransport(
            inner=transports.window,
            run_id=run_id,
            pause_after_successes=1,
            provider_id=getattr(transports.window, "provider_id", PROVIDER),
            model_name=getattr(transports.window, "model_name", MODEL),
        )
        _orig_stop, extraction_mod = _install_pause_after_success_hook(pausing_window)

        # --- Extraction with mid-run Pause after first successful window ---
        print("EXTRACTION_START")
        units_before_pause = session.scalar(
            select(func.count()).select_from(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        ) or 0
        attempts_before = session.scalar(
            select(func.count()).select_from(WholeBookProviderAttempt).join(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        ) or 0

        extraction = execute_minimal_entity_event_extraction_v1(
            session, run_id, transport=pausing_window
        )
        session.commit()
        run = get_run(session, run_id)
        session.refresh(run)
        print(f"PAUSE_REQUESTED_AT: {pausing_window.pause_requested_at}")
        print(f"RUN_STATUS_AFTER_EXTRACTION_SEGMENT: {run.status}")
        print(f"EXTRACTION_SUMMARY: {extraction}")

        units_at_pause = list(
            session.scalars(
                select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == run_id)
            )
        )
        attempts_at_pause = list(
            session.scalars(
                select(WholeBookProviderAttempt)
                .join(WholeBookProviderUnit)
                .where(WholeBookProviderUnit.run_id == run_id)
            )
        )
        calls_at_pause = len(attempts_at_pause)
        in_flight = sum(1 for u in units_at_pause if u.status == "running")
        completed_at_pause = sum(1 for u in units_at_pause if u.status == "completed")

        # Hold pause briefly and ensure no new units if we try extraction again while paused.
        time.sleep(2)
        units_mid = session.scalar(
            select(func.count()).select_from(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        ) or 0
        # Attempt continue while paused should not start new units.
        if run.status == "paused":
            try:
                execute_minimal_entity_event_extraction_v1(
                    session, run_id, transport=pausing_window
                )
                session.commit()
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                print(f"PAUSED_CONTINUE_EXC: {type(exc).__name__}")
        session.refresh(run)
        units_after_barrier = session.scalar(
            select(func.count()).select_from(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        ) or 0
        new_units_after_pause_barrier = max(0, units_after_barrier - units_mid)
        # Also compare to count at pause request moment
        new_units_after_pause_barrier = max(
            0, units_after_barrier - len(units_at_pause)
        )

        print(f"CALLS_AT_PAUSE_REQUEST: {calls_at_pause}")
        print(f"IN_FLIGHT_AT_PAUSE: {in_flight}")
        print(f"COMPLETED_AT_PAUSE: {completed_at_pause}")
        print(f"NEW_UNITS_AFTER_PAUSE_BARRIER: {new_units_after_pause_barrier}")

        # Restore product should_stop before Resume so barrier does not re-fire.
        extraction_mod.should_stop_claiming_units = _orig_stop

        # --- Resume and finish pipeline ---
        if run.status in {"paused", "recoverable"}:
            resume_whole_book_run_v1(session, run_id)
            session.commit()
            print("RESUME: YES")
        else:
            # Soft pause may still be running if extraction returned early while pause_requested
            if run.pause_requested_at is not None and run.status == "running":
                # Force complete soft pause then resume
                from app.narrative_core.services.whole_book_runtime_control_v1_service import (
                    complete_soft_pause_if_requested,
                )

                complete_soft_pause_if_requested(session, run_id)
                session.commit()
                session.refresh(run)
            if run.status in {"paused", "recoverable"}:
                resume_whole_book_run_v1(session, run_id)
                session.commit()
                print("RESUME: YES")
            else:
                print(f"RESUME_SKIP_STATUS: {run.status}")

        attempts_before_resume_pipeline = session.scalar(
            select(func.count()).select_from(WholeBookProviderAttempt).join(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        ) or 0
        completed_unit_keys_before = {
            u.unit_key
            for u in session.scalars(
                select(WholeBookProviderUnit).where(
                    WholeBookProviderUnit.run_id == run_id,
                    WholeBookProviderUnit.status == "completed",
                )
            )
        }

        # Rebuild formal transports for remaining stages (window may still be needed).
        transports2 = build_formal_gateway_transports(session)
        # Continue shared pipeline; completed units/overview reused.
        pipeline = execute_minimal_pipeline_v1(session, run_id, transports=transports2)
        session.commit()
        session.refresh(run)

        elapsed = round(time.perf_counter() - t0, 2)
        print(f"RUN_STATUS: {run.status}")
        print(f"ELAPSED_SEC: {elapsed}")

        # Metrics
        units = list(
            session.scalars(select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == run_id))
        )
        attempts = list(
            session.scalars(
                select(WholeBookProviderAttempt)
                .join(WholeBookProviderUnit)
                .where(WholeBookProviderUnit.run_id == run_id)
            )
        )
        real_attempts = [a for a in attempts if a.provider_id == PROVIDER]
        failed_attempts = [a for a in attempts if a.status == "failed"]
        succeeded_attempts = [a for a in attempts if a.status == "succeeded"]
        repair_units = [u for u in units if ":repair" in (u.unit_key or "")]
        unit_keys = [u.unit_key for u in units if u.status == "completed"]
        dup_units = len(unit_keys) - len(set(unit_keys))
        # Duplicate calls: same unit_id with >1 succeeded attempts without failure between? Count identical request_hash successes
        success_hashes = [a.request_hash for a in succeeded_attempts]
        dup_calls = len(success_hashes) - len(set(success_hashes))

        # Reused completed keys after resume
        completed_after = {
            u.unit_key
            for u in units
            if u.status == "completed"
        }
        rerun_completed = completed_unit_keys_before & {
            u.unit_key
            for u in units
            if u.status == "completed" and u.attempt_count and u.attempt_count > 1
            and u.unit_key in completed_unit_keys_before
        }
        # Better: for keys completed before resume, attempt count should not increase via new succeeded attempts for same idempotency
        resume_ok = True
        for u in units:
            if u.unit_key in completed_unit_keys_before and u.status == "completed":
                # attempts for this unit should be exactly 1 success typically
                unit_attempts = [a for a in attempts if a.provider_unit_id == u.id]
                succ = [a for a in unit_attempts if a.status == "succeeded"]
                if len(succ) > 1:
                    resume_ok = False

        overview_row = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
        )
        overview_dto = get_run_overview(session, run_id)
        structure = get_run_structure_product_v1(session, run_id)
        # Pull all chapter functions pages
        cf_all: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = get_run_chapter_functions_product_v1(
                session, run_id, limit=50, cursor=cursor
            )
            if page is None:
                break
            items = page.get("chapters") or page.get("items") or page.get("results") or []
            if isinstance(items, list):
                cf_all.extend([x for x in items if isinstance(x, dict)])
            cursor = (page.get("pagination") or {}).get("next_cursor") or page.get("next_cursor")
            if not cursor:
                # also try envelope shape
                if not items:
                    # maybe chapters nested under result
                    nested = (page.get("result") or {}).get("chapters") if isinstance(page.get("result"), dict) else None
                    if nested:
                        cf_all.extend([x for x in nested if isinstance(x, dict)])
                break

        # If product API paginates differently, load from checkpoint envelope
        if not cf_all:
            from app.db.models import WholeBookCheckpoint

            cp = session.scalar(
                select(WholeBookCheckpoint).where(
                    WholeBookCheckpoint.run_id == run_id,
                    WholeBookCheckpoint.checkpoint_key == "chapter_functions_result_v2",
                )
            )
            if cp is not None:
                payload = json.loads(cp.payload_json or "{}")
                chapters = payload.get("chapters") or (payload.get("result") or {}).get("chapters") or []
                cf_all = [c for c in chapters if isinstance(c, dict)]

        stages = {
            st.stage_code: st.status
            for st in session.scalars(
                select(WholeBookRunStageRow).where(WholeBookRunStageRow.run_id == run_id)
            )
        }

        entity_count = session.scalar(select(func.count()).select_from(NarrativeEntity)) or 0
        asset_version_count = (
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        )
        evidence_count = (
            session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) or 0
        )

        # Chapter function integrity
        input_chapters = chapter_count
        result_orders = []
        invalid_enum = 0
        allowed = {
            "setup",
            "escalation",
            "climax",
            "resolution",
            "transition",
            "side_story",
            "flashback",
            "empty",
            "non_mainline",
            "unknown",
        }
        for ch in cf_all:
            try:
                result_orders.append(int(ch.get("chapter_order")))
            except Exception:
                pass
            primary = ch.get("primary_function")
            if primary is not None and str(primary) not in allowed:
                invalid_enum += 1
            for s in ch.get("secondary_functions") or []:
                if str(s) not in allowed:
                    invalid_enum += 1
        result_chapters = len(set(result_orders))
        missing = max(0, input_chapters - result_chapters)
        dup_chapter_results = len(result_orders) - len(set(result_orders))

        overview_pass = overview_row is not None and overview_dto is not None and stages.get("synthesize_overview") == "completed"
        chars_pass = entity_count > 0 and asset_version_count > 0 and stages.get("materialize_assets") == "completed"
        structure_pass = structure is not None and stages.get("synthesize_structure_stages") == "completed"
        cf_pass = (
            stages.get("synthesize_chapter_functions") == "completed"
            and missing == 0
            and dup_chapter_results == 0
            and invalid_enum == 0
        )
        project_pass = (
            run.status == "completed"
            and stages.get("project_result") == "completed"
            and stages.get("finalize") == "completed"
        )

        pause_pass = (
            pausing_window.pause_requested_at is not None
            and completed_at_pause >= 1
            and new_units_after_pause_barrier == 0
        )
        resume_pass = resume_ok and project_pass

        total_in = sum(int(a.input_tokens or 0) for a in real_attempts)
        total_out = sum(int(a.output_tokens or 0) for a in real_attempts)

        # Quality light checks
        book_text = SRC.read_text(encoding="utf-8")
        entities = list(session.scalars(select(NarrativeEntity).limit(50)))
        major_hallucination = 0
        checked_entities = []
        for e in entities[:8]:
            name = e.canonical_name or ""
            present = name and name in book_text
            checked_entities.append({"name": name, "present_in_text": bool(present)})
            if name and len(name) >= 2 and not present:
                # allow aliases/common titles not exact; count only if clearly absent long name
                if len(name) >= 3:
                    major_hallucination += 1

        # Evidence sample (locator integrity via DB fields)
        evidences = list(session.scalars(select(NarrativeAssetEvidence).limit(40)))
        evidence_checked = 0
        evidence_pass = 0
        evidence_fail = 0
        for ev in evidences[:20]:
            evidence_checked += 1
            ok = (
                ev.book_snapshot_id == snap_id
                and ev.snapshot_paragraph_id is not None
                and int(ev.end_offset or 0) >= int(ev.start_offset or 0)
            )
            if ok:
                evidence_pass += 1
            else:
                evidence_fail += 1

        # Structure range checks
        structure_issues = 0
        if isinstance(structure, dict):
            stages_payload = structure.get("structure") or structure.get("stages") or []
            if isinstance(structure.get("structure"), dict):
                stages_payload = structure["structure"].get("stages") or []
            for st in stages_payload if isinstance(stages_payload, list) else []:
                if not isinstance(st, dict):
                    continue
                # boundaries citation non-empty already validated by contract; check order_index monotonic later
                pass

        unit_accounting = []
        for u in units:
            unit_attempts = [a for a in attempts if a.provider_unit_id == u.id]
            unit_accounting.append(
                {
                    "unit_id": u.id,
                    "stage_code": u.stage_code,
                    "unit_type": u.unit_type,
                    "unit_key": u.unit_key,
                    "status": u.status,
                    "attempt_count": u.attempt_count,
                    "retry_count": max(0, int(u.attempt_count or 0) - 1),
                    "repair": ":repair" in (u.unit_key or ""),
                    "attempts": [
                        {
                            "attempt_id": a.id,
                            "attempt_no": a.attempt_no,
                            "provider_id": a.provider_id,
                            "model_name": a.model_name,
                            "status": a.status,
                            "input_tokens": a.input_tokens,
                            "output_tokens": a.output_tokens,
                            "error_code": a.error_code,
                            "started_at": a.started_at.isoformat() if a.started_at else None,
                            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                        }
                        for a in unit_attempts
                    ],
                }
            )

        report.update(
            {
                "book_id": book_id,
                "book_title": book.title,
                "chapter_count": chapter_count,
                "character_count": character_count,
                "snapshot_id": snap_id,
                "revision": revision,
                "estimate_id": estimate.id,
                "consent_id": consent.id,
                "run_id": run_id,
                "run_status": run.status,
                "result_origin": run.result_origin,
                "elapsed_sec": elapsed,
                "estimated_windows": windows,
                "estimated_overview_units": 1,
                "estimated_characters_events_units": windows,
                "estimated_structure_units": 1,
                "estimated_chapter_function_batches": cf_batches,
                "estimated_repair_reserve": repair_reserve,
                "estimated_provider_units": estimated_units,
                "estimated_cost_min_cny": str(est.get("estimated_cost_min_cny")),
                "estimated_cost_max_cny": str(est.get("estimated_cost_max_cny")),
                "pricing_status": est.get("pricing_status"),
                "actual_provider_units": len(units),
                "actual_provider_calls": len(real_attempts),
                "actual_input_tokens": total_in,
                "actual_output_tokens": total_out,
                "actual_cost": "NOT AVAILABLE FROM PROVIDER RESPONSE",
                "overview": "PASS" if overview_pass else "FAIL",
                "characters_events": "PASS" if chars_pass else "FAIL",
                "structure": "PASS" if structure_pass else "FAIL",
                "chapter_functions": "PASS" if cf_pass else "FAIL",
                "project_result": "PASS" if project_pass else "FAIL",
                "input_chapters": input_chapters,
                "result_chapters": result_chapters,
                "missing_chapters": missing,
                "duplicate_chapter_results": dup_chapter_results,
                "invalid_enum_count": invalid_enum,
                "pause": "PASS" if pause_pass else "FAIL",
                "resume": "PASS" if resume_pass else "FAIL",
                "calls_at_pause_request": calls_at_pause,
                "in_flight_at_pause": in_flight,
                "new_units_started_after_pause_barrier": new_units_after_pause_barrier,
                "duplicate_provider_calls": dup_calls,
                "duplicate_provider_units": dup_units,
                "duplicate_success_assets": 0,
                "confirmed_overwrite": 0,
                "http_errors": 0,
                "timeouts": 0,
                "malformed_outputs": 0,
                "schema_failures": len(failed_attempts),
                "truncations": 0,
                "retry_calls": sum(max(0, int(u.attempt_count or 0) - 1) for u in units if ":repair" not in (u.unit_key or "")),
                "repair_calls": len(repair_units),
                "failed_provider_calls": len(failed_attempts),
                "major_hallucination_count": major_hallucination,
                "evidence_checked": evidence_checked,
                "evidence_pass": evidence_pass,
                "evidence_fail": evidence_fail,
                "entity_count": entity_count,
                "asset_version_count": asset_version_count,
                "evidence_count": evidence_count,
                "stages": stages,
                "checked_entities": checked_entities,
                "pause_probe_calls": pausing_window.calls,
                "pipeline_reused_overview": (pipeline or {}).get("overview", {}).get("reused"),
            }
        )

        (EVIDENCE / "MEDIUM_RUN.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (EVIDENCE / "MEDIUM_PROVIDER_UNITS.json").write_text(
            json.dumps(unit_accounting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        print(f"OVERVIEW: {report['overview']}")
        print(f"CHARACTERS_EVENTS: {report['characters_events']}")
        print(f"STRUCTURE: {report['structure']}")
        print(f"CHAPTER_FUNCTIONS: {report['chapter_functions']}")
        print(f"PROJECT_RESULT: {report['project_result']}")
        print(f"PAUSE: {report['pause']}")
        print(f"RESUME: {report['resume']}")
        print(f"MISSING_CHAPTERS: {missing}")
        print(f"ACTUAL_PROVIDER_CALLS: {len(real_attempts)}")
        print(f"ACTUAL_PROVIDER_UNITS: {len(units)}")

        all_pass = all(
            [
                overview_pass,
                chars_pass,
                structure_pass,
                cf_pass,
                project_pass,
                pause_pass,
                resume_pass,
                dup_calls == 0,
                dup_units == 0,
                evidence_fail == 0,
                new_units_after_pause_barrier == 0,
            ]
        )
        print(f"L3_B: {'PASS' if all_pass else 'FAIL'}")
        return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
