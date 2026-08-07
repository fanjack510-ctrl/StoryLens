#!/usr/bin/env python3
"""CHG-20260807-054 L3-A short formal Free real-provider run (5–10 chapters).

Isolated DB only. Never prints API keys or full model payloads.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
sys.path.insert(0, str(ROOT / "apps" / "api"))
PRIVATE = Path(r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src")
if PRIVATE.is_dir():
    sys.path.insert(0, str(PRIVATE))

PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"
CHAPTER_TARGET = 6
L3_DIR = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-provider-fix")
EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260807-054"


def _find_short_novel() -> tuple[Path, str]:
    docs = Path.home() / "Documents"
    roots = [p for p in docs.iterdir() if p.is_dir() and p.name.upper().startswith("TXT")]
    if not roots:
        raise FileNotFoundError("TXT novel folder not found under Documents")
    root = roots[0]
    candidates: list[tuple[int, Path, str, str]] = []
    for p in root.glob("*.txt"):
        raw = p.read_bytes()
        text = None
        enc = "utf-8"
        for e in ("utf-8", "gbk", "gb18030"):
            try:
                text = raw.decode(e)
                enc = e
                break
            except Exception:
                continue
        if not text:
            continue
        marks = list(re.finditer(r"(?m)^第[一二三四五六七八九十百千0-9]+章", text))
        if 15 <= len(marks) <= 50:
            candidates.append((len(marks), p, text, enc))
    if not candidates:
        raise FileNotFoundError("no 15–50 chapter novel found")
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


def _slice_first_n_chapters(text: str, n: int) -> str:
    marks = list(re.finditer(r"(?m)^第[一二三四五六七八九十百千0-9]+章[^\n]*", text))
    if len(marks) < n:
        raise ValueError(f"need >= {n} chapters, found {len(marks)}")
    start = marks[0].start()
    # include up to start of chapter n+1 (exclusive)
    end = marks[n].start() if len(marks) > n else len(text)
    body = text[start:end].strip() + "\n"
    return body


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    L3_DIR.mkdir(parents=True, exist_ok=True)
    db = L3_DIR / "storylens_l3_fix.db"
    if db.exists():
        db.unlink()

    os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + db.as_posix()
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "false"
    os.environ["STORYLENS_ALIYUN_ENABLED"] = "true"
    os.environ["STORYLENS_DEFAULT_MODEL_PROVIDER"] = PROVIDER
    os.environ["STORYLENS_RUN_ALIYUN_TESTS"] = "1"

    from sqlalchemy import func, select

    from app.db.models import (
        ApplicationSetting,
        NarrativeAssetVersion,
        NarrativeEntity,
        ProviderConfiguration,
        WholeBookOverviewResult,
        WholeBookProviderAttempt,
        WholeBookProviderUnit,
        WholeBookRun,
    )
    from app.db.session import SessionLocal, create_db
    from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
        get_run_chapter_functions_product_v1,
    )
    from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
    from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
    from app.narrative_core.services.whole_book_free_product_v1_service import (
        create_free_whole_book_analysis_v1,
        prepare_free_whole_book_analysis_v1,
    )
    from app.narrative_core.services.whole_book_minimal_read_v1_service import get_run_overview
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
        print("REAL_SHORT_RUN: FAIL")
        return 2
    os.environ["STORYLENS_ALIYUN_API_KEY"] = key
    print("API_KEY_CONFIGURED: YES")

    src_path, full_text = _find_short_novel()
    sliced = _slice_first_n_chapters(full_text, CHAPTER_TARGET)
    sample_path = L3_DIR / f"l3a_short_{CHAPTER_TARGET}ch.txt"
    sample_path.write_text(sliced, encoding="utf-8")
    print(f"SAMPLE_SOURCE: {src_path.name}")
    print(f"SAMPLE_FILE: {sample_path}")
    print(f"CHAPTER_COUNT_TARGET: {CHAPTER_TARGET}")

    create_db()
    report: dict = {
        "provider": PROVIDER,
        "model": MODEL,
        "chapter_count": CHAPTER_TARGET,
        "sample_source_name": src_path.name,
        "db": str(db),
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

        book = import_book(session, sample_path.name, sliced.encode("utf-8"))
        book_id = book.id
        print(f"BOOK_ID: {book_id}")

        prepare = prepare_free_whole_book_analysis_v1(session, book_id)
        session.commit()
        print(f"PREPARE_REAL_ENABLED: {prepare.get('real_provider_enabled')}")
        print(f"PREPARE_CHAPTER_COUNT: {prepare.get('chapter_count')}")

        estimate = estimate_whole_book_analysis(
            session, book_id, "whole_book_native", row.id
        )
        # Prefer unavailable pricing so consent uses explicit call/token caps
        # (avoids needing live CNY pricing for L3 wiring).
        if estimate.pricing_status == "available":
            pass
        else:
            estimate.pricing_status = "unavailable"
        session.flush()
        consent = create_whole_book_consent(
            session,
            book_id=book_id,
            estimate_id=estimate.id,
            user_budget_limit_cny="50",
            max_provider_calls=200,
            max_input_tokens=2_000_000,
            max_output_tokens=500_000,
            auto_retry_enabled=True,
            max_retries_per_unit=1,
        )
        session.commit()
        print(f"ESTIMATE_ID: {estimate.id}")
        print(f"CONSENT_ID: {consent.id}")

        print("CREATE_START")
        try:
            result = create_free_whole_book_analysis_v1(
                session,
                book_id,
                estimate_id=estimate.id,
                consent_id=consent.id,
                client_request_id=f"l3a-{uuid.uuid4().hex[:12]}",
                execute_pipeline=True,
            )
            session.commit()
            create_ok = True
            err = None
        except Exception as exc:  # noqa: BLE001
            # Keep partial run/units for evidence inspection (isolated temp DB only).
            try:
                session.commit()
            except Exception:
                session.rollback()
            create_ok = False
            result = None
            err = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(exc)[:300]}"
            if key in err:
                err = err.replace(key, "***")
            print(f"CREATE_ERROR: {err}")
            # Recover latest formal run if create partially persisted.
            run = session.scalar(
                select(WholeBookRun).order_by(WholeBookRun.id.desc()).limit(1)
            )
            if run is not None:
                result = {"run_id": run.id}

        elapsed = round(time.perf_counter() - t0, 2)
        print(f"CREATE_PASS: {'YES' if create_ok else 'NO'}")
        print(f"ELAPSED_SEC: {elapsed}")

        run_id = result["run_id"] if result else None
        report.update(
            {
                "create_pass": create_ok,
                "create_error": err,
                "run_id": run_id,
                "elapsed_sec": elapsed,
            }
        )

        if not create_ok or run_id is None:
            (EVIDENCE / "REAL_SHORT_RUN.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("REAL_SHORT_RUN: FAIL")
            return 1

        run = session.get(WholeBookRun, run_id)
        attempts = list(
            session.scalars(
                select(WholeBookProviderAttempt)
                .join(WholeBookProviderUnit)
                .where(WholeBookProviderUnit.run_id == run_id)
            )
        )
        units = list(
            session.scalars(
                select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == run_id)
            )
        )
        real_calls = [a for a in attempts if a.provider_id == PROVIDER]
        failed_calls = [a for a in attempts if a.status == "failed"]
        succeeded_calls = [a for a in attempts if a.status == "succeeded"]

        overview_row = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
        )
        overview_dto = get_run_overview(session, run_id)
        structure = get_run_structure_product_v1(session, run_id)
        chapter_fn = get_run_chapter_functions_product_v1(session, run_id, limit=50)
        entity_count = session.scalar(select(func.count()).select_from(NarrativeEntity)) or 0
        asset_count = (
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        )

        # Duplicate metrics
        unit_keys = [u.unit_key for u in units if u.status == "completed"]
        dup_units = len(unit_keys) - len(set(unit_keys))
        call_hashes = [a.request_hash for a in succeeded_calls]
        dup_calls = len(call_hashes) - len(set(call_hashes))

        overview_pass = overview_row is not None and overview_dto is not None
        chars_pass = entity_count > 0 and asset_count > 0
        structure_pass = structure is not None and str(
            (structure or {}).get("product_result_status")
            or (structure or {}).get("result_status")
            or ""
        ) in {"completed", "insufficient", "conflict"}
        cf_pass = chapter_fn is not None and str(
            (chapter_fn or {}).get("product_result_status")
            or (chapter_fn or {}).get("result_status")
            or ""
        ) in {"completed", "insufficient", "conflict", "partial"}
        # Prefer stage rows as source of truth for project/finalize.
        from app.db.models import WholeBookRunStageRow

        stages = {
            st.stage_code: st.status
            for st in session.scalars(
                select(WholeBookRunStageRow).where(WholeBookRunStageRow.run_id == run_id)
            )
        }
        structure_pass = structure_pass and stages.get("synthesize_structure_stages") == "completed"
        cf_pass = cf_pass and stages.get("synthesize_chapter_functions") == "completed"
        project_pass = (
            run is not None
            and run.status == "completed"
            and stages.get("project_result") == "completed"
            and stages.get("finalize") == "completed"
        )
        evidence_pass = any(
            (a.input_tokens or 0) + (a.output_tokens or 0) > 0 for a in real_calls
        )

        report.update(
            {
                "run_status": run.status if run else None,
                "result_origin": run.result_origin if run else None,
                "snapshot_id": run.snapshot_id if run else None,
                "real_provider_called": len(real_calls) > 0,
                "provider_attempt_count": len(attempts),
                "real_provider_attempt_count": len(real_calls),
                "failed_provider_calls": len(failed_calls),
                "succeeded_provider_calls": len(succeeded_calls),
                "provider_unit_count": len(units),
                "duplicate_provider_units": dup_units,
                "duplicate_provider_calls": dup_calls,
                "entity_count": entity_count,
                "asset_version_count": asset_count,
                "overview": "PASS" if overview_pass else "FAIL",
                "characters_events": "PASS" if chars_pass else "FAIL",
                "structure": "PASS" if structure_pass else "FAIL",
                "chapter_functions": "PASS" if cf_pass else "FAIL",
                "project_result": "PASS" if project_pass else "FAIL",
                "evidence": "PASS" if evidence_pass else "FAIL",
                "sample_overview_claim_count": (
                    len((overview_dto or {}).get("claims") or [])
                    if isinstance(overview_dto, dict)
                    else None
                ),
            }
        )

        print(f"RUN_ID: {run_id}")
        print(f"RUN_STATUS: {run.status}")
        print(f"RESULT_ORIGIN: {run.result_origin}")
        print(f"REAL_PROVIDER_CALLED: {'YES' if report['real_provider_called'] else 'NO'}")
        print(f"REAL_PROVIDER_ATTEMPTS: {len(real_calls)}")
        print(f"FAILED_PROVIDER_CALLS: {len(failed_calls)}")
        print(f"OVERVIEW: {report['overview']}")
        print(f"CHARACTERS_EVENTS: {report['characters_events']}")
        print(f"STRUCTURE: {report['structure']}")
        print(f"CHAPTER_FUNCTIONS: {report['chapter_functions']}")
        print(f"PROJECT_RESULT: {report['project_result']}")
        print(f"EVIDENCE: {report['evidence']}")

        (EVIDENCE / "REAL_SHORT_RUN.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Redacted call summary (no payloads / keys)
        call_summary = [
            {
                "attempt_id": a.id,
                "provider_id": a.provider_id,
                "model_name": a.model_name,
                "status": a.status,
                "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens,
                "error_code": a.error_code,
            }
            for a in attempts
        ]
        (EVIDENCE / "REAL_PROVIDER_CALLS.json").write_text(
            json.dumps(call_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        all_pass = all(
            [
                create_ok,
                report["real_provider_called"],
                overview_pass,
                chars_pass,
                structure_pass,
                cf_pass,
                project_pass,
                evidence_pass,
                dup_units == 0,
                dup_calls == 0,
            ]
        )
        print(f"REAL_SHORT_RUN: {'PASS' if all_pass else 'FAIL'}")
        return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
