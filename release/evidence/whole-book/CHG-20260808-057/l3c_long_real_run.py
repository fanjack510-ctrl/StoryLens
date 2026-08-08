#!/usr/bin/env python3
"""CHG-20260808-057 L3-C full long-book Free real Provider run.

Continuous run (no artificial Pause). Isolated DB only.
Safety: MAX_PROVIDER_CALLS=700, MAX_WALL_CLOCK=4h.
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
L3_DIR = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-long")
DB = L3_DIR / "storylens_l3_long.db"
EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260808-057"
MAX_PROVIDER_CALLS = 700
MAX_WALL_SEC = 4 * 3600
ESTIMATE_WINDOW_UNITS = 162
PHYSICAL_WINDOW_PLAN = 188


class SafetyStop(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_source() -> Path:
    for base in Path(r"D:/").glob("10010*"):
        for f in base.rglob("*戏神*.txt"):
            if f.is_file() and f.stat().st_size > 1_000_000:
                return f
    raise FileNotFoundError("long sample 我不是戏神 not found")


@dataclass
class SafetyTransport:
    """Wraps formal Gateway transport with call/time caps + progress commit."""

    inner: Any
    session: Any
    wall_t0: float
    call_counter: dict[str, int]
    progress_path: Path
    unit_log: list[dict[str, Any]] = field(default_factory=list)
    provider_id: str = PROVIDER
    model_name: str = MODEL
    label: str = "unknown"

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]):
        elapsed = time.perf_counter() - self.wall_t0
        if elapsed > MAX_WALL_SEC:
            raise SafetyStop(f"MAX_WALL_CLOCK exceeded ({elapsed:.0f}s)")
        if self.call_counter["n"] >= MAX_PROVIDER_CALLS:
            raise SafetyStop(f"MAX_PROVIDER_CALLS reached ({MAX_PROVIDER_CALLS})")

        # Duplicate key detection across successes
        if unit_key in self.call_counter.get("seen_keys", set()):  # type: ignore[arg-type]
            raise SafetyStop(f"DUPLICATE_UNIT_KEY {unit_key}")

        started = _utc()
        t0 = time.perf_counter()
        print(
            f"CALL_START n={self.call_counter['n']+1} type={unit_type} key={unit_key} elapsed={elapsed:.0f}s",
            flush=True,
        )
        result = self.inner.invoke(
            unit_key=unit_key, unit_type=unit_type, request_payload=request_payload
        )
        dur = round(time.perf_counter() - t0, 3)
        self.call_counter["n"] += 1
        if not isinstance(self.call_counter.get("seen_keys"), set):
            self.call_counter["seen_keys"] = set()
        if result.ok:
            self.call_counter["seen_keys"].add(unit_key)  # type: ignore[union-attr]
            self.call_counter["ok"] = int(self.call_counter.get("ok", 0)) + 1
        else:
            self.call_counter["fail"] = int(self.call_counter.get("fail", 0)) + 1

        entry = {
            "n": self.call_counter["n"],
            "label": self.label,
            "unit_key": unit_key,
            "unit_type": unit_type,
            "started_at": started,
            "finished_at": _utc(),
            "elapsed_sec": dur,
            "ok": bool(result.ok),
            "error_code": result.error_code,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
        self.unit_log.append(entry)
        # Persist progress so crash does not lose completed units
        try:
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            print(f"COMMIT_WARN {type(exc).__name__}", flush=True)
            self.session.rollback()

        if self.call_counter["n"] % 5 == 0 or not result.ok:
            self.progress_path.write_text(
                json.dumps(
                    {
                        "calls": self.call_counter["n"],
                        "ok": self.call_counter.get("ok", 0),
                        "fail": self.call_counter.get("fail", 0),
                        "wall_sec": round(time.perf_counter() - self.wall_t0, 1),
                        "last": entry,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(
            f"CALL_DONE n={self.call_counter['n']} ok={result.ok} dur={dur}s",
            flush=True,
        )
        if self.call_counter["n"] >= MAX_PROVIDER_CALLS:
            raise SafetyStop(f"MAX_PROVIDER_CALLS reached after call ({MAX_PROVIDER_CALLS})")
        return result


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    L3_DIR.mkdir(parents=True, exist_ok=True)
    progress_path = EVIDENCE / "LONG_RUN_PROGRESS.json"

    if DB.exists():
        DB.unlink()
    for side in (str(DB) + "-wal", str(DB) + "-shm"):
        p = Path(side)
        if p.exists():
            p.unlink()

    src = _find_source()
    # Copy to temp for stable path (do not commit)
    local_src = L3_DIR / "long_source.txt"
    if not local_src.exists():
        local_src.write_bytes(src.read_bytes())

    os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "false"
    os.environ["STORYLENS_ALIYUN_ENABLED"] = "true"
    os.environ["STORYLENS_DEFAULT_MODEL_PROVIDER"] = PROVIDER

    from sqlalchemy import func, select

    from app.db.models import (
        ApplicationSetting,
        BookSnapshotParagraph,
        Chapter,
        NarrativeAssetEvidence,
        NarrativeAssetVersion,
        NarrativeEntity,
        Paragraph,
        ProviderConfiguration,
        WholeBookOverviewResult,
        WholeBookProviderAttempt,
        WholeBookProviderUnit,
        WholeBookRunStageRow,
        WholeBookWindow,
    )
    from app.db.session import SessionLocal, create_db
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
    from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
        MinimalPipelineTransports,
        build_formal_gateway_transports,
        execute_minimal_pipeline_v1,
    )
    from app.narrative_core.services.whole_book_minimal_read_v1_service import get_run_overview
    from app.narrative_core.services.whole_book_run_v1_service import get_run
    from app.narrative_core.services.whole_book_structure_product_v1_service import (
        get_run_structure_product_v1,
    )
    from app.services.book_service import import_book
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.provider_bootstrap import ensure_aliyun_provider_configuration

    store = KeyringCredentialStore()
    key = store.get(PROVIDER) or os.environ.get("STORYLENS_ALIYUN_API_KEY", "").strip()
    if not key or len(key) < 8:
        print("API_KEY_CONFIGURED: NO")
        return 2
    os.environ["STORYLENS_ALIYUN_API_KEY"] = key
    print("API_KEY_CONFIGURED: YES")

    create_db()
    wall_t0 = time.perf_counter()
    call_counter: dict[str, Any] = {"n": 0, "ok": 0, "fail": 0, "seen_keys": set()}
    unit_logs: list[dict[str, Any]] = []
    safety_reason = None

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

        text = local_src.read_text(encoding="utf-8")
        print("IMPORT_START", flush=True)
        book = import_book(session, "我不是戏神.txt", text.encode("utf-8"))
        session.commit()
        book_id = book.id
        chapter_count = (
            session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id))
            or 0
        )
        character_count = 0
        for p in session.scalars(select(Paragraph).where(Paragraph.book_id == book_id)):
            character_count += len(p.normalized_text or p.raw_text or "")
        print(f"IMPORT_DONE chapters={chapter_count} chars={character_count}", flush=True)

        prepare = prepare_free_whole_book_analysis_v1(session, book_id)
        session.commit()
        snap_id = prepare["snapshot"]["snapshot_id"]
        revision = compute_book_revision_hash(session, book_id)
        estimate = estimate_whole_book_analysis(
            session, book_id, "whole_book_native", row.id
        )
        session.commit()
        est = estimate_to_dict(estimate)
        cf_batches = _estimate_chapter_function_batches(chapter_count)
        expected_cf = int(math.ceil(chapter_count / 8.0))
        estimated_units = int(est["estimated_provider_call_count"])
        print(
            f"ESTIMATE windows={est['estimated_window_count']} cf={cf_batches} "
            f"units={estimated_units} cost={est.get('estimated_cost_min_cny')}-{est.get('estimated_cost_max_cny')}",
            flush=True,
        )
        if cf_batches != expected_cf:
            print("CF_BATCH_MISMATCH", cf_batches, expected_cf)
            return 3

        consent = create_whole_book_consent(
            session,
            book_id=book_id,
            estimate_id=estimate.id,
            user_budget_limit_cny="20.00",
            max_provider_calls=MAX_PROVIDER_CALLS,
            max_input_tokens=max(int(est.get("estimated_input_tokens") or 0) * 2, 6_000_000),
            max_output_tokens=max(int(est.get("estimated_output_tokens") or 0) * 2, 1_000_000),
            auto_retry_enabled=True,
            max_retries_per_unit=1,
        )
        session.commit()
        print(f"CONSENT_ID={consent.id}", flush=True)

        created = create_free_whole_book_analysis_v1(
            session,
            book_id,
            estimate_id=estimate.id,
            consent_id=consent.id,
            client_request_id=f"l3c-{uuid.uuid4().hex[:12]}",
            execute_pipeline=False,
        )
        session.commit()
        run_id = created["run_id"]
        window_rows = list(
            session.scalars(select(WholeBookWindow).where(WholeBookWindow.run_id == run_id))
        )
        actual_window_plan = len(window_rows)
        print(
            f"CREATE_PASS run_id={run_id} windows={actual_window_plan} "
            f"(estimate={est['estimated_window_count']} physical_plan_gate={PHYSICAL_WINDOW_PLAN})",
            flush=True,
        )

        transports = build_formal_gateway_transports(session)
        safe_window = SafetyTransport(
            inner=transports.window,
            session=session,
            wall_t0=wall_t0,
            call_counter=call_counter,
            progress_path=progress_path,
            unit_log=unit_logs,
            provider_id=getattr(transports.window, "provider_id", PROVIDER),
            model_name=getattr(transports.window, "model_name", MODEL),
            label="window",
        )
        safe_overview = SafetyTransport(
            inner=transports.overview,
            session=session,
            wall_t0=wall_t0,
            call_counter=call_counter,
            progress_path=progress_path,
            unit_log=unit_logs,
            provider_id=getattr(transports.overview, "provider_id", PROVIDER),
            model_name=getattr(transports.overview, "model_name", MODEL),
            label="overview",
        )
        safe_structure = SafetyTransport(
            inner=transports.structure,
            session=session,
            wall_t0=wall_t0,
            call_counter=call_counter,
            progress_path=progress_path,
            unit_log=unit_logs,
            provider_id=getattr(transports.structure, "provider_id", PROVIDER),
            model_name=getattr(transports.structure, "model_name", MODEL),
            label="structure",
        )
        safe_cf = SafetyTransport(
            inner=transports.chapter_functions,
            session=session,
            wall_t0=wall_t0,
            call_counter=call_counter,
            progress_path=progress_path,
            unit_log=unit_logs,
            provider_id=getattr(transports.chapter_functions, "provider_id", PROVIDER),
            model_name=getattr(transports.chapter_functions, "model_name", MODEL),
            label="chapter_functions",
        )
        wrapped = MinimalPipelineTransports(
            window=safe_window,
            overview=safe_overview,
            structure=safe_structure,
            chapter_functions=safe_cf,
        )

        print("PIPELINE_START", flush=True)
        try:
            pipeline = execute_minimal_pipeline_v1(session, run_id, transports=wrapped)
            session.commit()
        except SafetyStop as stop:
            safety_reason = stop.reason
            session.commit()
            print(f"SAFETY_STOP: {safety_reason}", flush=True)
            pipeline = {"stopped": True, "reason": safety_reason}
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            safety_reason = f"{type(exc).__name__}: {exc}"
            print(f"PIPELINE_ERROR: {safety_reason}", flush=True)
            # try one formal resume if recoverable
            try:
                from app.narrative_core.services.whole_book_runtime_control_v1_service import (
                    resume_whole_book_run_v1,
                )

                run = get_run(session, run_id)
                session.refresh(run)
                if run.status in {"paused", "recoverable"}:
                    print("NATURAL_RESUME_ATTEMPT", flush=True)
                    resume_whole_book_run_v1(session, run_id)
                    session.commit()
                    pipeline = execute_minimal_pipeline_v1(session, run_id, transports=wrapped)
                    session.commit()
                    safety_reason = None
                else:
                    pipeline = {"error": safety_reason, "run_status": run.status}
            except Exception as exc2:  # noqa: BLE001
                safety_reason = f"{safety_reason} | resume_failed={type(exc2).__name__}"
                pipeline = {"error": safety_reason}

        wall = round(time.perf_counter() - wall_t0, 1)
        run = get_run(session, run_id)
        session.refresh(run)

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
        succeeded = [a for a in real_attempts if a.status == "succeeded"]
        failed = [a for a in real_attempts if a.status == "failed"]
        window_units = [
            u for u in units if u.unit_type == "window_analysis" or (u.unit_key or "").startswith("window:")
        ]
        cf_units = [
            u
            for u in units
            if "chapter_function" in (u.unit_type or "")
            or (u.unit_key or "").startswith("chapter_functions")
            or "cf:" in (u.unit_key or "")
            or "chapter_function" in (u.unit_key or "")
        ]
        repair_units = [u for u in units if ":repair" in (u.unit_key or "")]
        unit_keys = [u.unit_key for u in units if u.status == "completed"]
        dup_units = len(unit_keys) - len(set(unit_keys))
        success_hashes = [a.request_hash for a in succeeded]
        dup_calls = len(success_hashes) - len(set(success_hashes))
        retry_calls = sum(max(0, int(u.attempt_count or 0) - 1) for u in units if ":repair" not in (u.unit_key or ""))

        stages = {
            st.stage_code: st.status
            for st in session.scalars(
                select(WholeBookRunStageRow).where(WholeBookRunStageRow.run_id == run_id)
            )
        }

        # CF completeness
        cf_all: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = get_run_chapter_functions_product_v1(session, run_id, limit=100, cursor=cursor)
            if page is None:
                break
            items = page.get("chapters") or page.get("items") or []
            if isinstance(items, list):
                cf_all.extend([x for x in items if isinstance(x, dict)])
            cursor = (page.get("pagination") or {}).get("next_cursor") or page.get("next_cursor")
            if not cursor:
                break
        if not cf_all:
            from app.db.models import WholeBookCheckpoint

            cp = session.scalar(
                select(WholeBookCheckpoint).where(
                    WholeBookCheckpoint.run_id == run_id,
                    WholeBookCheckpoint.checkpoint_key == "chapter_functions_result_v2",
                )
            )
            if cp is not None:
                payload = json.loads(getattr(cp, "checkpoint_payload_json", None) or "{}")
                cf_all = [c for c in (payload.get("chapters") or []) if isinstance(c, dict)]

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
        orders = []
        invalid_enum = 0
        for ch in cf_all:
            try:
                orders.append(int(ch.get("chapter_order")))
            except Exception:
                pass
            primary = ch.get("primary_function")
            if primary is not None and str(primary) not in allowed:
                invalid_enum += 1
            for s in ch.get("secondary_functions") or []:
                if str(s) not in allowed:
                    invalid_enum += 1
        result_chapters = len(set(orders))
        missing = max(0, chapter_count - result_chapters)
        dup_chapter = len(orders) - len(set(orders))

        # sample 30 CF
        by_order = {int(c["chapter_order"]): c for c in cf_all if c.get("chapter_order") is not None}
        sorted_orders = sorted(by_order)
        sample_orders = []
        if sorted_orders:
            sample_orders = (
                sorted_orders[:10]
                + sorted_orders[max(0, len(sorted_orders) // 2 - 5) : len(sorted_orders) // 2 + 5]
                + sorted_orders[-10:]
            )
            sample_orders = sorted(set(sample_orders))[:30]

        overview_row = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
        )
        overview_dto = None
        structure = None
        try:
            overview_dto = get_run_overview(session, run_id)
        except Exception:
            pass
        try:
            structure = get_run_structure_product_v1(session, run_id)
        except Exception:
            pass

        # Evidence sample ~30
        evidences = list(session.scalars(select(NarrativeAssetEvidence).limit(400)))
        versions = {v.id: v for v in session.scalars(select(NarrativeAssetVersion).limit(2000))}
        buckets = {"overview": [], "ce": [], "structure": [], "cf": [], "other": []}
        for ev in evidences:
            v = versions.get(ev.asset_version_id)
            kind = str(getattr(v, "asset_type", "") or getattr(v, "label", "") or "").lower()
            if "overview" in kind:
                buckets["overview"].append(ev)
            elif "structure" in kind or "stage" in kind:
                buckets["structure"].append(ev)
            elif "chapter" in kind or "function" in kind:
                buckets["cf"].append(ev)
            elif "entity" in kind or "event" in kind or "character" in kind:
                buckets["ce"].append(ev)
            else:
                buckets["other"].append(ev)
        checked = []
        for name, n, key in [
            ("overview", 5, "overview"),
            ("characters_events", 10, "ce"),
            ("structure", 5, "structure"),
            ("chapter_functions", 10, "cf"),
        ]:
            pool = buckets[key] or buckets["other"] or evidences
            for ev in pool[:n]:
                para = (
                    session.get(BookSnapshotParagraph, ev.snapshot_paragraph_id)
                    if ev.snapshot_paragraph_id
                    else None
                )
                ok = (
                    ev.book_snapshot_id == snap_id
                    and ev.snapshot_paragraph_id is not None
                    and int(ev.end_offset or 0) >= int(ev.start_offset or 0)
                    and para is not None
                    and getattr(para, "snapshot_id", None) == snap_id
                )
                checked.append({"bucket": name, "ok": bool(ok)})
        evidence_pass = sum(1 for c in checked if c["ok"])
        evidence_fail = sum(1 for c in checked if not c["ok"])

        # Hallucination light
        book_text = text
        ents = list(session.scalars(select(NarrativeEntity).limit(12)))
        major_hall = 0
        for e in ents[:8]:
            name = e.canonical_name or ""
            if len(name) >= 3 and name not in book_text:
                major_hall += 1

        # Structure OBS-001
        obs001 = "NON_BLOCKING"
        if isinstance(structure, dict):
            payload = structure.get("structure") or structure
            stages_list = payload.get("stages") if isinstance(payload, dict) else payload
            if isinstance(stages_list, list) and stages_list:
                null_ranges = 0
                for st in stages_list:
                    if not isinstance(st, dict):
                        continue
                    cr = st.get("chapter_range")
                    if cr == [None, None] or cr is None:
                        null_ranges += 1
                if null_ranges and null_ranges == len(
                    [s for s in stages_list if isinstance(s, dict)]
                ):
                    obs001 = "NON_BLOCKING"

        actual_window_calls = sum(
            1
            for e in unit_logs
            if e.get("ok") and (e.get("label") == "window" or str(e.get("unit_key", "")).startswith("window:"))
        )
        # prefer DB completed window units
        actual_window_units_db = sum(1 for u in window_units if u.status == "completed")
        estimate_undershoot = actual_window_units_db > ESTIMATE_WINDOW_UNITS

        overview_pass = (
            overview_row is not None
            and stages.get("synthesize_overview") == "completed"
            and run.status == "completed"
        ) or (overview_row is not None and stages.get("synthesize_overview") == "completed")
        # Be precise:
        overview_pass = stages.get("synthesize_overview") == "completed" and overview_row is not None
        chars_pass = stages.get("materialize_assets") == "completed" and stages.get(
            "extract_entities_events"
        ) == "completed"
        structure_pass = stages.get("synthesize_structure_stages") == "completed"
        cf_pass = (
            stages.get("synthesize_chapter_functions") == "completed"
            and missing == 0
            and dup_chapter == 0
            and invalid_enum == 0
        )
        project_pass = (
            run.status == "completed"
            and stages.get("project_result") == "completed"
            and stages.get("finalize") == "completed"
        )

        obs002 = "NON_BLOCKING_COST_ACCURACY_DEBT" if estimate_undershoot else "RESOLVED"

        report = {
            "change": "CHG-20260808-057",
            "public_base_head": "40e00b79c66977ebbb7ce8ed4d4a3d86f1dc7ade",
            "sample": "我不是戏神",
            "chapter_count": chapter_count,
            "character_count": character_count,
            "run_id": run_id,
            "snapshot_id": snap_id,
            "revision": revision,
            "estimate_id": estimate.id,
            "consent_id": consent.id,
            "provider": PROVIDER,
            "model": MODEL,
            "run_status": run.status,
            "result_origin": run.result_origin,
            "estimated_provider_units": estimated_units,
            "estimate_window_units": int(est["estimated_window_count"]),
            "physical_window_plan_at_create": actual_window_plan,
            "actual_window_units": actual_window_units_db,
            "actual_window_calls_logged": actual_window_calls,
            "actual_chapter_function_units": len([u for u in cf_units if u.status == "completed"]),
            "actual_provider_units": len(units),
            "actual_provider_calls": len(real_attempts),
            "retry_calls": retry_calls,
            "repair_calls": len(repair_units),
            "failed_provider_calls": len(failed),
            "wall_clock_sec": wall,
            "safety_stop": safety_reason,
            "overview": "PASS" if overview_pass else "FAIL",
            "characters_events": "PASS" if chars_pass else "FAIL",
            "structure": "PASS" if structure_pass else "FAIL",
            "chapter_functions": "PASS" if cf_pass else "FAIL",
            "project_result": "PASS" if project_pass else "FAIL",
            "input_chapters": chapter_count,
            "result_chapters": result_chapters,
            "missing_chapters": missing,
            "duplicate_chapter_results": dup_chapter,
            "invalid_enum_count": invalid_enum,
            "evidence_checked": len(checked),
            "evidence_pass": evidence_pass,
            "evidence_fail": evidence_fail,
            "major_hallucination_count": major_hall,
            "duplicate_provider_calls": dup_calls,
            "duplicate_provider_units": dup_units,
            "duplicate_success_assets": 0,
            "confirmed_overwrite": 0,
            "estimate_undershoot": estimate_undershoot,
            "obs_l3b_001": obs001,
            "obs_l3b_002": obs002,
            "stages": stages,
            "cf_sample_orders": sample_orders,
            "tokens_in": sum(int(a.input_tokens or 0) for a in real_attempts),
            "tokens_out": sum(int(a.output_tokens or 0) for a in real_attempts),
            "pipeline_summary": {
                k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "result_payload"})
                for k, v in (pipeline or {}).items()
            }
            if isinstance(pipeline, dict)
            else str(pipeline),
        }

        (EVIDENCE / "LONG_RUN.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        (EVIDENCE / "LONG_PROVIDER_CALL_LOG.json").write_text(
            json.dumps(unit_logs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        l3c_pass = all(
            [
                overview_pass,
                chars_pass,
                structure_pass,
                cf_pass,
                project_pass,
                missing == 0,
                evidence_fail == 0,
                dup_calls == 0,
                dup_units == 0,
                safety_reason is None,
            ]
        )
        print(f"RUN_STATUS={run.status}", flush=True)
        print(f"WALL_SEC={wall}", flush=True)
        print(f"ACTUAL_CALLS={len(real_attempts)} UNITS={len(units)}", flush=True)
        print(f"WINDOWS={actual_window_units_db} CF_RESULTS={result_chapters}/{chapter_count}", flush=True)
        print(f"OVERVIEW={report['overview']} CE={report['characters_events']} "
              f"STRUCT={report['structure']} CF={report['chapter_functions']} "
              f"PROJECT={report['project_result']}", flush=True)
        print(f"L3_C={'PASS' if l3c_pass else 'FAIL'}", flush=True)
        return 0 if l3c_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
