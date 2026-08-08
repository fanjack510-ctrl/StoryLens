#!/usr/bin/env python3
"""CHG-060/061/062 final DeepSeek small-book Whole-Book acceptance (5–10 chapters).

Isolated temp DB. Never prints API keys or full model payloads.
Does not use 我不是戏神 / full 42-chapter books — slices first N chapters only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\Dstorylens-wt-v120-deepseek")
sys.path.insert(0, str(ROOT / "apps" / "api"))
PRIVATE = Path(r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src")
if PRIVATE.is_dir():
    sys.path.insert(0, str(PRIVATE))

PROVIDER = "deepseek"
MODEL = "deepseek-v4-flash"
CHAPTER_TARGET = 6
L3_DIR = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-deepseek-small-accept")
EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260808-062" / "DEEPSEEK_SMALL_ACCEPTANCE"

# Capture cache usage from live ModelResponse without changing product code.
USAGE_CAPTURE: list[dict] = []


def _find_source_novel() -> tuple[Path, str]:
    docs = Path.home() / "Documents"
    roots = [p for p in docs.iterdir() if p.is_dir() and p.name.upper().startswith("TXT")]
    if not roots:
        raise FileNotFoundError("TXT novel folder not found under Documents")
    root = roots[0]
    candidates: list[tuple[int, Path, str]] = []
    for p in root.glob("*.txt"):
        raw = p.read_bytes()
        text = None
        for e in ("utf-8", "gbk", "gb18030"):
            try:
                text = raw.decode(e)
                break
            except Exception:
                continue
        if not text:
            continue
        # Exclude known long book names.
        if "戏神" in p.name or "我不是戏神" in text[:200]:
            continue
        marks = list(re.finditer(r"(?m)^第[一二三四五六七八九十百千0-9]+章", text))
        if 15 <= len(marks) <= 80:
            candidates.append((len(marks), p, text))
    if not candidates:
        raise FileNotFoundError("no suitable 15–80 chapter novel found for slicing")
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


def _slice_first_n_chapters(text: str, n: int) -> str:
    marks = list(re.finditer(r"(?m)^第[一二三四五六七八九十百千0-9]+章[^\n]*", text))
    if len(marks) < n:
        raise ValueError(f"need >= {n} chapters, found {len(marks)}")
    start = marks[0].start()
    end = marks[n].start() if len(marks) > n else len(text)
    return text[start:end].strip() + "\n"


def _install_usage_capture() -> None:
    from app.model_gateway.providers import openai_compatible as oc

    orig = oc.OpenAICompatibleProvider.generate

    async def wrapped(self, request):  # type: ignore[no-untyped-def]
        resp = await orig(self, request)
        USAGE_CAPTURE.append(
            {
                "provider": getattr(self, "name", None),
                "model": getattr(resp, "model", None),
                "prompt_tokens": getattr(resp, "input_tokens", None),
                "completion_tokens": getattr(resp, "output_tokens", None),
                "total_tokens": getattr(resp, "total_tokens", None),
                "cache_hit_tokens": getattr(resp, "cache_hit_tokens", None),
                "cache_miss_tokens": getattr(resp, "cache_miss_tokens", None),
                "cached_tokens": getattr(resp, "cached_tokens", None),
            }
        )
        return resp

    oc.OpenAICompatibleProvider.generate = wrapped  # type: ignore[method-assign]


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    L3_DIR.mkdir(parents=True, exist_ok=True)
    db = L3_DIR / "storylens_deepseek_small.db"
    if db.exists():
        db.unlink()

    os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + db.as_posix()
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "false"
    os.environ["STORYLENS_DEFAULT_MODEL_PROVIDER"] = PROVIDER

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
        WholeBookRunStageRow,
    )
    from app.db.session import SessionLocal, create_db
    from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
        get_run_chapter_functions_product_v1,
    )
    from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
    from app.narrative_core.services.whole_book_free_product_v1_service import (
        create_free_whole_book_analysis_v1,
        prepare_free_whole_book_analysis_v1,
    )
    from app.narrative_core.services.whole_book_minimal_read_v1_service import get_run_overview
    from app.narrative_core.services.whole_book_start_limits_v1 import suggest_limits_from_estimate
    from app.narrative_core.services.whole_book_structure_product_v1_service import (
        get_run_structure_product_v1,
    )
    from app.services.book_service import import_book
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.provider_bootstrap import ensure_deepseek_provider_configuration
    from app.services.provider_runtime import set_active_cloud_provider

    store = KeyringCredentialStore()
    key = store.get(PROVIDER) or os.environ.get("STORYLENS_DEEPSEEK_API_KEY", "").strip()
    if not key or len(key) < 8:
        print("API_KEY_CONFIGURED: NO")
        print("FINAL_RESULT: FAIL")
        return 2
    os.environ["STORYLENS_DEEPSEEK_API_KEY"] = key
    print("API_KEY_CONFIGURED: YES")
    print(f"KEY_LEN: {len(key)}")

    src_path, full_text = _find_source_novel()
    sliced = _slice_first_n_chapters(full_text, CHAPTER_TARGET)
    sample_path = L3_DIR / f"deepseek_small_{CHAPTER_TARGET}ch.txt"
    sample_path.write_text(sliced, encoding="utf-8")
    print(f"SAMPLE_SOURCE: {src_path.name}")
    print(f"SAMPLE_FILE: {sample_path}")
    print(f"CHAPTER_COUNT: {CHAPTER_TARGET}")

    _install_usage_capture()
    create_db()

    report: dict = {
        "sample_source_name": src_path.name,
        "chapter_count": CHAPTER_TARGET,
        "provider": PROVIDER,
        "model": MODEL,
        "db": str(db),
        "sidecar_sha256_expected": "6E049C483744ECCD69AEFF19904BF92797123B1BF19A77FE6AC20AC3DFB7C197",
        "product_code_modified": False,
    }

    t0 = time.perf_counter()
    with SessionLocal() as session:
        ensure_deepseek_provider_configuration(session, create_if_missing=True)
        row = session.scalar(
            select(ProviderConfiguration).where(ProviderConfiguration.provider_name == PROVIDER)
        )
        assert row is not None
        row.enabled = True
        row.disconnected = False
        row.plus_model = MODEL
        row.max_model = MODEL
        row.flash_model = MODEL
        row.credential_reference = f"keyring:{PROVIDER}"
        cloud = session.get(ApplicationSetting, "cloud_enabled")
        if cloud is None:
            session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
        else:
            cloud.value_json = "true"
        set_active_cloud_provider(session, PROVIDER)
        session.commit()

        book = import_book(session, sample_path.name, sliced.encode("utf-8"))
        book_id = int(book.id)
        print(f"BOOK_ID: {book_id}")

        prepare = prepare_free_whole_book_analysis_v1(session, book_id)
        session.commit()
        est = prepare.get("estimate") or {}
        print(f"PREPARE_PROVIDER: {prepare.get('active_provider_name')}")
        print(f"PREPARE_MODEL: {prepare.get('active_model_name')}")
        print(f"PREPARE_CHAPTER_COUNT: {prepare.get('chapter_count')}")
        print(f"PRE_RUN_ESTIMATED_CALLS: {est.get('estimated_provider_calls')}")
        print(f"PRE_RUN_INPUT_TOKENS: {est.get('estimated_input_tokens')}")
        print(f"PRE_RUN_OUTPUT_TOKENS: {est.get('estimated_output_tokens')}")
        print(
            "PRE_RUN_COST_RANGE: "
            f"{est.get('estimated_cost_min_cny')} ~ {est.get('estimated_cost_max_cny')}"
        )

        if prepare.get("active_provider_name") != PROVIDER:
            print("ACTIVE_PROVIDER_MISMATCH")
            report["prepare_provider"] = prepare.get("active_provider_name")
            (EVIDENCE / "ACCEPTANCE.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("FINAL_RESULT: FAIL")
            return 1
        if str(est.get("model_name") or "") != MODEL:
            print(f"MODEL_MISMATCH: {est.get('model_name')}")
            (EVIDENCE / "ACCEPTANCE.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("FINAL_RESULT: FAIL")
            return 1

        # Reload estimate ORM for suggested limits / consent.
        from app.db.models import WholeBookCostEstimate

        estimate = session.get(WholeBookCostEstimate, int(est["estimate_id"]))
        assert estimate is not None
        sug = suggest_limits_from_estimate(estimate)
        consent = create_whole_book_consent(
            session,
            book_id=book_id,
            estimate_id=estimate.id,
            user_budget_limit_cny=sug["max_cost_budget_cny"],
            max_provider_calls=int(sug["max_provider_calls"]),
            max_input_tokens=int(sug["max_input_tokens"]),
            max_output_tokens=int(sug["max_output_tokens"]),
            auto_retry_enabled=True,
            max_retries_per_unit=1,
        )
        session.commit()
        print(f"ESTIMATE_ID: {estimate.id}")
        print(f"CONSENT_ID: {consent.id}")
        print(f"CONSENT: PASS")

        report.update(
            {
                "pre_run_estimated_calls": est.get("estimated_provider_calls"),
                "pre_run_input_tokens": est.get("estimated_input_tokens"),
                "pre_run_output_tokens": est.get("estimated_output_tokens"),
                "pre_run_cost_min_cny": str(est.get("estimated_cost_min_cny")),
                "pre_run_cost_max_cny": str(est.get("estimated_cost_max_cny")),
                "consent": "PASS",
                "consent_id": consent.id,
                "estimate_id": estimate.id,
            }
        )

        print("CREATE_START")
        create_ok = False
        err = None
        result = None
        try:
            result = create_free_whole_book_analysis_v1(
                session,
                book_id,
                estimate_id=estimate.id,
                consent_id=consent.id,
                client_request_id=f"ds-small-{uuid.uuid4().hex[:12]}",
                execute_pipeline=True,
            )
            session.commit()
            create_ok = True
        except Exception as exc:  # noqa: BLE001
            try:
                session.commit()
            except Exception:
                session.rollback()
            err = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{str(exc)[:400]}"
            if key in err:
                err = err.replace(key, "***")
            print(f"CREATE_ERROR: {err}")
            run = session.scalar(select(WholeBookRun).order_by(WholeBookRun.id.desc()).limit(1))
            if run is not None:
                result = {"run_id": run.id, "run": {"run_id": run.id}}

        elapsed = round(time.perf_counter() - t0, 2)
        print(f"RUN_CREATED: {'PASS' if create_ok else 'FAIL'}")
        print(f"ELAPSED_SEC: {elapsed}")

        run_id = None
        if result:
            run_id = result.get("run_id") or (result.get("run") or {}).get("run_id")
            if run_id is None and result.get("run"):
                run_id = result["run"].get("id")

        report.update(
            {
                "run_created": "PASS" if create_ok else "FAIL",
                "create_error": err,
                "run_id": run_id,
                "elapsed_sec": elapsed,
            }
        )

        if run_id is None:
            (EVIDENCE / "ACCEPTANCE.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("FINAL_RESULT: FAIL")
            return 1

        run = session.get(WholeBookRun, int(run_id))
        attempts = list(
            session.scalars(
                select(WholeBookProviderAttempt)
                .join(WholeBookProviderUnit)
                .where(WholeBookProviderUnit.run_id == int(run_id))
            )
        )
        units = list(
            session.scalars(
                select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == int(run_id))
            )
        )
        real_calls = [a for a in attempts if a.provider_id == PROVIDER]
        failed_calls = [a for a in attempts if a.status == "failed"]
        succeeded_calls = [a for a in attempts if a.status == "succeeded"]
        retry_calls = [a for a in attempts if int(a.attempt_no or 1) > 1]
        repair_calls = [
            a
            for a in attempts
            if "repair" in str(a.error_code or "").lower()
            or "repair" in str(getattr(a, "model_name", "") or "").lower()
        ]
        # Prefer unit_type markers if present on units.
        repair_units = [u for u in units if "repair" in str(u.unit_type or "").lower()]

        overview_row = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == int(run_id))
        )
        overview_dto = get_run_overview(session, int(run_id))
        structure = get_run_structure_product_v1(session, int(run_id))
        chapter_fn = get_run_chapter_functions_product_v1(session, int(run_id), limit=50)
        entity_count = int(session.scalar(select(func.count()).select_from(NarrativeEntity)) or 0)
        asset_count = int(
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        )

        unit_keys = [u.unit_key for u in units if u.status == "completed"]
        dup_units = len(unit_keys) - len(set(unit_keys))
        call_hashes = [a.request_hash for a in succeeded_calls]
        dup_calls = len(call_hashes) - len(set(h for h in call_hashes if h))

        stages = {
            st.stage_code: st.status
            for st in session.scalars(
                select(WholeBookRunStageRow).where(WholeBookRunStageRow.run_id == int(run_id))
            )
        }
        overview_pass = overview_row is not None and overview_dto is not None
        chars_pass = entity_count > 0 and asset_count > 0
        structure_pass = structure is not None and str(
            (structure or {}).get("product_result_status")
            or (structure or {}).get("result_status")
            or ""
        ) in {"completed", "insufficient", "conflict"}
        structure_pass = structure_pass and stages.get("synthesize_structure_stages") == "completed"
        cf_pass = chapter_fn is not None and str(
            (chapter_fn or {}).get("product_result_status")
            or (chapter_fn or {}).get("result_status")
            or ""
        ) in {"completed", "insufficient", "conflict", "partial"}
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

        prompt_tokens = sum(int(a.input_tokens or 0) for a in real_calls)
        completion_tokens = sum(int(a.output_tokens or 0) for a in real_calls)
        total_tokens = prompt_tokens + completion_tokens
        cache_hit = sum(int(u.get("cache_hit_tokens") or 0) for u in USAGE_CAPTURE)
        cache_miss = sum(int(u.get("cache_miss_tokens") or 0) for u in USAGE_CAPTURE)
        if cache_hit == 0 and cache_miss == 0 and USAGE_CAPTURE:
            # Fall back: treat missing miss as prompt - hit.
            for u in USAGE_CAPTURE:
                pt = int(u.get("prompt_tokens") or 0)
                ht = int(u.get("cache_hit_tokens") or u.get("cached_tokens") or 0)
                if u.get("cache_miss_tokens") is None and pt:
                    cache_miss += max(pt - ht, 0)
                    cache_hit += ht

        attempt_cost = sum(Decimal(str(a.cost_cny or 0)) for a in real_calls)
        run_cost = getattr(run, "estimated_actual_cost_cny", None) if run else None
        post_cost = float(run_cost) if run_cost is not None else float(attempt_cost)

        pre_max = Decimal(str(est.get("estimated_cost_max_cny") or "0"))
        pre_min = Decimal(str(est.get("estimated_cost_min_cny") or "0"))
        cost_reasonable = True
        if pre_max > 0:
            # Actual should not wildly exceed pre-run max (allow 3x headroom for short sample).
            cost_reasonable = Decimal(str(post_cost)) <= (pre_max * Decimal("3") + Decimal("0.05"))
            if Decimal(str(post_cost)) < 0:
                cost_reasonable = False

        # Secret leak scan on evidence artifacts / error strings.
        secret_leak = "ABSENT"
        blob = json.dumps(
            {"err": err, "usage": USAGE_CAPTURE, "attempts": [
                {"ec": a.error_code, "em": a.error_message_safe} for a in attempts
            ]},
            ensure_ascii=False,
        )
        if key and key in blob:
            secret_leak = "PRESENT"

        report.update(
            {
                "run_status": run.status if run else None,
                "run_provider_name": getattr(run, "provider_name", None) if run else None,
                "run_model_name": getattr(run, "model_name", None) if run else None,
                "result_origin": run.result_origin if run else None,
                "real_deepseek_calls": len(real_calls),
                "failed_calls": len(failed_calls),
                "retry_calls": len(retry_calls),
                "repair_calls": max(len(repair_calls), len(repair_units)),
                "duplicate_provider_calls": dup_calls,
                "duplicate_assets": dup_units,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cache_hit_tokens": cache_hit,
                "cache_miss_tokens": cache_miss,
                "post_run_estimated_actual_cost_cny": post_cost,
                "pre_vs_post_cost_reasonable": "YES" if cost_reasonable else "NO",
                "overview": "PASS" if overview_pass else "FAIL",
                "characters_events": "PASS" if chars_pass else "FAIL",
                "structure": "PASS" if structure_pass else "FAIL",
                "chapter_functions": "PASS" if cf_pass else "FAIL",
                "project_result": "PASS" if project_pass else "FAIL",
                "evidence": "PASS" if evidence_pass else "FAIL",
                "secret_leak": secret_leak,
                "stages": stages,
                "entity_count": entity_count,
                "asset_version_count": asset_count,
                "usage_capture_count": len(USAGE_CAPTURE),
            }
        )

        print(f"OVERVIEW: {report['overview']}")
        print(f"CHARACTERS_EVENTS: {report['characters_events']}")
        print(f"STRUCTURE: {report['structure']}")
        print(f"CHAPTER_FUNCTIONS: {report['chapter_functions']}")
        print(f"PROJECT_RESULT: {report['project_result']}")
        print(f"EVIDENCE: {report['evidence']}")
        print(f"REAL_DEEPSEEK_CALLS: {len(real_calls)}")
        print(f"PROMPT_TOKENS: {prompt_tokens}")
        print(f"CACHE_HIT_TOKENS: {cache_hit}")
        print(f"CACHE_MISS_TOKENS: {cache_miss}")
        print(f"COMPLETION_TOKENS: {completion_tokens}")
        print(f"TOTAL_TOKENS: {total_tokens}")
        print(f"POST_RUN_ESTIMATED_ACTUAL_COST_CNY: {post_cost}")
        print(f"PRE_VS_POST_COST_REASONABLE: {report['pre_vs_post_cost_reasonable']}")
        print(f"FAILED_CALLS: {len(failed_calls)}")
        print(f"RETRY_CALLS: {len(retry_calls)}")
        print(f"REPAIR_CALLS: {report['repair_calls']}")
        print(f"DUPLICATE_PROVIDER_CALLS: {dup_calls}")
        print(f"DUPLICATE_ASSETS: {dup_units}")
        print(f"SECRET_LEAK: {secret_leak}")

        all_pass = all(
            [
                create_ok,
                len(real_calls) > 0,
                overview_pass,
                chars_pass,
                structure_pass,
                cf_pass,
                project_pass,
                evidence_pass,
                dup_units == 0,
                dup_calls == 0,
                secret_leak == "ABSENT",
                cost_reasonable,
                getattr(run, "provider_name", "") == PROVIDER,
                getattr(run, "model_name", "") == MODEL,
            ]
        )
        report["final_result"] = "PASS" if all_pass else "FAIL"
        report["ready_to_commit"] = bool(all_pass)

        (EVIDENCE / "ACCEPTANCE.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        call_summary = [
            {
                "attempt_id": a.id,
                "provider_id": a.provider_id,
                "model_name": a.model_name,
                "status": a.status,
                "attempt_no": a.attempt_no,
                "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens,
                "cost_cny": str(a.cost_cny) if a.cost_cny is not None else None,
                "error_code": a.error_code,
            }
            for a in attempts
        ]
        (EVIDENCE / "PROVIDER_CALLS.json").write_text(
            json.dumps(call_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (EVIDENCE / "USAGE_CAPTURE.json").write_text(
            json.dumps(USAGE_CAPTURE, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Markdown summary for humans.
        md = f"""# DeepSeek Small-Book Acceptance

SAMPLE: {src_path.name} (sliced)
CHAPTER COUNT: {CHAPTER_TARGET}
PROVIDER: {PROVIDER}
MODEL: {MODEL}

PRE-RUN ESTIMATED CALLS: {est.get('estimated_provider_calls')}
PRE-RUN INPUT TOKENS: {est.get('estimated_input_tokens')}
PRE-RUN OUTPUT TOKENS: {est.get('estimated_output_tokens')}
PRE-RUN COST RANGE: {est.get('estimated_cost_min_cny')} ～ {est.get('estimated_cost_max_cny')}

RUN CREATED: {report['run_created']}
CONSENT: PASS
OVERVIEW: {report['overview']}
CHARACTERS EVENTS: {report['characters_events']}
STRUCTURE: {report['structure']}
CHAPTER FUNCTIONS: {report['chapter_functions']}
PROJECT RESULT: {report['project_result']}

REAL DEEPSEEK CALLS: {len(real_calls)}
PROMPT TOKENS: {prompt_tokens}
CACHE HIT TOKENS: {cache_hit}
CACHE MISS TOKENS: {cache_miss}
COMPLETION TOKENS: {completion_tokens}
TOTAL TOKENS: {total_tokens}
POST-RUN ESTIMATED ACTUAL COST CNY: {post_cost}
PRE VS POST COST REASONABLE: {report['pre_vs_post_cost_reasonable']}

EVIDENCE: {report['evidence']}
FAILED CALLS: {len(failed_calls)}
RETRY CALLS: {len(retry_calls)}
REPAIR CALLS: {report['repair_calls']}
DUPLICATE PROVIDER CALLS: {dup_calls}
DUPLICATE ASSETS: {dup_units}
SECRET LEAK: {secret_leak}
PRODUCT CODE MODIFIED: NO
FINAL RESULT: {report['final_result']}
READY TO COMMIT CHG-060/061/062: {'YES' if all_pass else 'NO'}
"""
        (EVIDENCE / "ACCEPTANCE.md").write_text(md, encoding="utf-8")
        print(f"FINAL_RESULT: {report['final_result']}")
        print(f"READY_TO_COMMIT: {'YES' if all_pass else 'NO'}")
        return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
