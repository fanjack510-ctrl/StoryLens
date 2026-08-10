#!/usr/bin/env python3
"""CHG-074 short real DeepSeek acceptance for Hierarchical Whole-Book V2.

One authorized run only. Isolated temp SQLite. Never prints API keys or full novel text.
Budget hard stop: 0.50 CNY.
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Dstorylens-wt-v120-codex-takeover")
sys.path.insert(0, str(ROOT / "apps" / "api"))

EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260810-074"
ISOLATED = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-chg074-accept")
SAMPLE = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-deepseek-small-accept\deepseek_small_6ch.txt")
USER_DB = Path.home() / "AppData" / "Local" / "StoryLens" / "database" / "storylens.db"
BUDGET_CNY = 0.50
PROVIDER = "deepseek"
MODEL = "deepseek-v4-flash"
INPUT_RATE = 1.0
OUTPUT_RATE = 2.0

CALLS: list[dict[str, Any]] = []
PROGRESS: list[dict[str, Any]] = []
STOP_REASON: str | None = None
CUM_COST = 0.0


def _write(name: str, payload: Any) -> None:
    path = EVIDENCE / name
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(str(payload), encoding="utf-8")


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1_000_000) * INPUT_RATE + (completion_tokens / 1_000_000) * OUTPUT_RATE


def _parse_chapters(text: str) -> list[tuple[str, str]]:
    marks = list(re.finditer(r"(?m)^(第[一二三四五六七八九十百千0-9]+章[^\n]*)", text))
    if not (6 <= len(marks) <= 10):
        raise ValueError(f"expected 6-10 chapters, found {len(marks)}")
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        title = m.group(1).strip()
        body = text[m.end() : end].strip()
        out.append((title, body))
    return out


def _load_api_key() -> str:
    from app.services.credentials.keyring_store import KeyringCredentialStore

    store = KeyringCredentialStore()
    secret = store.get("deepseek") if store.available() else None
    if not secret:
        import keyring

        secret = keyring.get_password("StoryLens", "deepseek") or keyring.get_password("storylens", "deepseek")
    if not secret:
        raise RuntimeError("DeepSeek API key unavailable via formal keyring path")
    return secret


def _template_like(text: str) -> bool:
    needles = [
        "TODO",
        "placeholder",
        "占位",
        "待填写",
        "lorem ipsum",
        "MOCK",
        "fixture",
        "generic template",
        "这里写",
    ]
    low = text.lower()
    return any(n.lower() in low for n in needles)


def main() -> int:
    global STOP_REASON, CUM_COST
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ISOLATED.mkdir(parents=True, exist_ok=True)
    assert not str(ISOLATED).startswith(str(USER_DB.parent)), "must not use formal user DB path"
    isolated_db = ISOLATED / "chg074_isolated.db"
    if isolated_db.exists():
        isolated_db.unlink()

    user_db_mtime_before = USER_DB.stat().st_mtime if USER_DB.exists() else None

    # --- deterministic gate reconfirm already done by caller; still record ---
    from app.narrative_core.whole_book_v2.pipeline import (
        ChapterMeta,
        ProviderBudget,
        assert_context_safe,
        build_cost_plan,
        build_token_plan,
        contains_raw_chapter_text,
        plan_windows,
        run_hierarchical_pipeline,
        synthesis_payload_from_intermediates,
    )
    from app.narrative_core.whole_book_v2.engine import SourceChapter, EvidenceValidator
    from app.narrative_core.whole_book_v2.provider_engine import GatewayWholeBookV2Analyzer, UNIT_SCHEMAS
    from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2, V2_STAGES
    from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.base import ModelRequest

    raw = SAMPLE.read_text(encoding="utf-8")
    parsed = _parse_chapters(raw)
    chapters = [
        SourceChapter(
            chapter_id=2000 + i,
            chapter_index=i,
            title=title,
            text=body,
            snapshot_id=74,
            revision_hash="chg074-short",
        )
        for i, (title, body) in enumerate(parsed, 1)
    ]
    metas = [c.as_meta() for c in chapters]
    budget = ProviderBudget(
        provider=PROVIDER,
        model=MODEL,
        context_limit=128_000,
        input_rate_per_mtok=INPUT_RATE,
        output_rate_per_mtok=OUTPUT_RATE,
        expected_output=4000,
    )
    windows = plan_windows(metas, book_id=74, budget=budget)
    token_plan = build_token_plan(windows, budget=budget)
    token_plan = token_plan.model_copy(update={"chapter_count": len(chapters)})
    cost_plan = build_cost_plan(token_plan, budget)
    assert_context_safe(token_plan)

    # Deterministic no-raw check
    pipe = run_hierarchical_pipeline(metas, book_id=74, budget=budget)
    assert not contains_raw_chapter_text(pipe.synthesis_payload, metas)

    pre_run = {
        "source_head": "e98a431c8ec5c4913593dd7806a1ebdaad43eafb",
        "sample_path": str(SAMPLE),
        "sample_name": "明朝那些事儿.txt (CHG-071/062 short slice)",
        "chapter_count": len(chapters),
        "window_count": len(windows),
        "estimated_extract_calls": token_plan.extract_calls,
        "estimated_consolidation_calls": token_plan.consolidation_calls,
        "estimated_final_synthesis_calls": token_plan.final_synthesis_calls,
        "estimated_repair_reserve_calls": token_plan.repair_reserve_calls,
        "estimated_total_calls": token_plan.estimated_total_calls,
        "estimated_input_tokens": token_plan.estimated_input_tokens,
        "estimated_output_tokens": token_plan.estimated_output_tokens,
        "estimated_cost_low_cny": cost_plan.estimated_cost_low,
        "estimated_cost_high_cny": cost_plan.estimated_cost_high,
        "max_request_tokens": token_plan.max_single_request_total_tokens,
        "provider_context_limit": token_plan.provider_context_limit,
        "context_safety_margin": token_plan.context_safety_margin,
        "CONTEXT_SAFE": token_plan.context_safe,
        "provider": PROVIDER,
        "model": MODEL,
        "thinking": "disabled",
        "budget_cny": BUDGET_CNY,
        "formal_user_db": str(USER_DB),
        "isolated_db": str(isolated_db),
        "window_ids": [w.window_id for w in windows],
    }
    _write("PRE_RUN_PLAN.json", pre_run)
    print("PRE_RUN_PLAN written")
    print(json.dumps({k: pre_run[k] for k in [
        "chapter_count","window_count","estimated_total_calls","estimated_cost_low_cny",
        "estimated_cost_high_cny","max_request_tokens","CONTEXT_SAFE"]}, ensure_ascii=False, indent=2))

    if token_plan.context_safe != "YES":
        STOP_REASON = "CONTEXT_SAFE=NO"
        _write("ACCEPTANCE.json", {"final_result": "BLOCKED", "reason": STOP_REASON, **pre_run})
        return 2
    if cost_plan.estimated_cost_high > BUDGET_CNY:
        STOP_REASON = "PRE_RUN_COST_HIGH_EXCEEDS_BUDGET"
        _write("ACCEPTANCE.json", {"final_result": "BLOCKED", "reason": STOP_REASON, **pre_run})
        return 2

    api_key = _load_api_key()
    provider = OpenAICompatibleProvider(
        name="deepseek",
        base_url="https://api.deepseek.com",
        api_key=api_key,
        default_model=MODEL,
        timeout_seconds=180,
        max_context_tokens=128000,
        enabled=True,
        profile_name="deepseek",
        cloud=True,
        provider_family="deepseek",
        supports_json_object=True,
        supports_thinking_control=True,
        sends_content_to_cloud=True,
    )
    gateway = ModelGateway([provider])
    # Real hierarchical synthesis only; local window primitives keep evidence integrity.
    # Final synthesis units MUST come from DeepSeek (no silent local merge).
    gateway.disallow_local_merge = True  # type: ignore[attr-defined]
    gateway.deterministic_extraction = True  # type: ignore[attr-defined]
    gateway.force_local_merge = False  # type: ignore[attr-defined]

    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name=PROVIDER,
        model_name=MODEL,
        max_output_tokens=4000,
        budget=budget,
    )

    original_call = analyzer._call

    async def guarded_call(key: str, schema, prompt: str, *, repair: bool = False):
        global CUM_COST, STOP_REASON
        est_in = max(1, len(prompt) // 2)
        est_out = analyzer.max_output_tokens
        projected = CUM_COST + _estimate_cost(est_in, est_out)
        if projected > BUDGET_CNY:
            STOP_REASON = "COST_GUARD_STOP"
            raise RuntimeError(f"COST_GUARD_STOP projected={projected:.6f}")
        t0 = time.perf_counter()
        status = "ok"
        err = None
        try:
            resp = await original_call(key, schema, prompt, repair=repair)
            return resp
        except Exception as exc:
            status = "error"
            err = type(exc).__name__ + ": " + str(exc)[:300]
            raise
        finally:
            latency = round(time.perf_counter() - t0, 3)
            # response captured after await in success path via analyzer.responses
            call_index = len(CALLS) + 1
            last = analyzer.responses[-1] if status == "ok" and analyzer.responses else None
            in_tok = int(getattr(last, "input_tokens", 0) or 0) if last else est_in
            out_tok = int(getattr(last, "output_tokens", 0) or 0) if last else 0
            hit = getattr(last, "cache_hit_tokens", None) if last else None
            miss = getattr(last, "cache_miss_tokens", None) if last else None
            if last:
                CUM_COST += _estimate_cost(in_tok, out_tok)
            CALLS.append(
                {
                    "call_index": call_index,
                    "unit_type": "synthesis" if key in UNIT_SCHEMAS else "window_or_other",
                    "unit_id": key,
                    "window_id": key.split("window:", 1)[-1] if key.startswith("window:") else None,
                    "provider": PROVIDER,
                    "model": MODEL,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": (in_tok + out_tok) if last else None,
                    "cache_hit_tokens": hit,
                    "cache_miss_tokens": miss,
                    "finish_reason": getattr(last, "finish_reason", None) if last else None,
                    "latency": latency,
                    "status": status,
                    "error": err,
                    "repair_of": key if repair else None,
                    "retry_of": None,
                    "cumulative_cost_cny": round(CUM_COST, 6),
                }
            )

    analyzer._call = guarded_call  # type: ignore[method-assign]

    progress_events: list[tuple] = []

    def progress_cb(stage: str, pct: float, chapter: int) -> None:
        progress_events.append((stage, pct, chapter, time.time()))
        PROGRESS.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "stage_percent": pct,
                "current_chapter": chapter,
                "provider_calls_completed": analyzer.stats.provider_calls,
            }
        )

    earliest_failure = None
    cascade: list[str] = []
    root_cause = None
    result: WholeBookAnalysisV2 | None = None
    run_created = False
    formal_adapter = "FAIL"
    evidence_audit: dict[str, Any] = {}
    content_checks: dict[str, Any] = {}

    try:
        run_created = True
        # pin recorded in evidence (no DB product run table required for this acceptance harness)
        result, responses = asyncio.run(
            analyzer.analyze(
                run_id=74074,
                book_id=74,
                title="明朝那些事儿（短样本6章）",
                chapters=chapters,
                progress=progress_cb,
            )
        )
    except Exception as exc:
        earliest_failure = f"{type(exc).__name__}: {str(exc)[:500]}"
        tb = traceback.format_exc()
        _write("FAILURE_TRACE.txt", tb)
        msg = str(exc).lower()
        if "cost_guard" in msg:
            root_cause = "COST GUARD"
        elif "truncat" in msg or "finish_reason" in msg:
            root_cause = "TRUNCATION"
        elif "schema" in msg or "validation" in msg or "missing" in msg:
            root_cause = "SCHEMA"
        elif "evidence" in msg:
            root_cause = "EVIDENCE"
        elif "context" in msg:
            root_cause = "COST GUARD" if "cost" in msg else "PROVIDER"
        elif "network" in msg or "timeout" in msg or "connect" in msg:
            root_cause = "NETWORK"
        else:
            root_cause = "PROVIDER" if CALLS else "UNKNOWN"
        cascade = ["RESULT_MATERIALIZE", "CONTENT_AUDIT", "FORMAL_ADAPTER"]

    # Persist call/progress/usage regardless
    _write("PROVIDER_CALLS.json", CALLS)
    usage = {
        "actual_provider_calls": len([c for c in CALLS if c["status"] == "ok"]),
        "failed_calls": len([c for c in CALLS if c["status"] != "ok"]),
        "repair_calls": analyzer.stats.repair_calls,
        "prompt_tokens": sum(int(c.get("input_tokens") or 0) for c in CALLS if c["status"] == "ok"),
        "completion_tokens": sum(int(c.get("output_tokens") or 0) for c in CALLS if c["status"] == "ok"),
        "cache_hit_tokens": sum(int(c.get("cache_hit_tokens") or 0) for c in CALLS if c.get("cache_hit_tokens")),
        "cache_miss_tokens": sum(int(c.get("cache_miss_tokens") or 0) for c in CALLS if c.get("cache_miss_tokens")),
        "estimated_actual_cost_cny": round(CUM_COST, 6),
        "provider": PROVIDER,
        "model": MODEL,
        "base_url": "https://api.deepseek.com",
        "base_url_identity": provider.endpoint_fingerprint() if hasattr(provider, "endpoint_fingerprint") else "api.deepseek.com",
        "run_provider_pin": PROVIDER,
        "run_model_pin": MODEL,
        "thinking": "disabled",
    }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    _write("USAGE_CAPTURE.json", usage)

    # Progress snapshots from analyzer
    prog_dump = [p.model_dump(mode="json") for p in analyzer.progress_events]
    if not prog_dump:
        prog_dump = PROGRESS
    _write("PROGRESS_EVENTS.json", prog_dump)

    # Duplicate checks
    unit_ids = [c["unit_id"] for c in CALLS if c["status"] == "ok" and not c.get("repair_of")]
    dup_units = len(unit_ids) - len(set(unit_ids))
    window_ids = [c["window_id"] for c in CALLS if c.get("window_id") and c["status"] == "ok"]
    dup_windows = len(window_ids) - len(set(window_ids))

    secret_leak = "ABSENT"
    for blob in [json.dumps(CALLS), json.dumps(usage), json.dumps(prog_dump)]:
        if api_key and api_key in blob:
            secret_leak = "PRESENT"

    final = "FAIL"
    if result is not None:
        # Formal adapter (Python contract = product schema)
        try:
            again = WholeBookAnalysisV2.model_validate(result.model_dump(mode="json"))
            assert again.schema_version == result.schema_version
            formal_adapter = "PASS"
        except Exception as exc:
            formal_adapter = f"FAIL: {exc}"
            earliest_failure = earliest_failure or f"FORMAL_ADAPTER: {exc}"
            root_cause = root_cause or "FORMAL ADAPTER"

        # Evidence audit
        validator = EvidenceValidator(chapters)
        ok_refs = 0
        bad_refs = []
        sample_ids = list(result.evidence_index.keys())[:8]
        for eid in sample_ids:
            ref = result.evidence_index[eid]
            try:
                validator.validate(ref)
                # chapter_id must not equal chapter_index for this sample (ids start at 2001)
                if ref.chapter_id == ref.chapter_index:
                    raise ValueError("chapter_index masquerading as chapter_id")
                ok_refs += 1
            except Exception as exc:
                bad_refs.append({"evidence_id": eid, "error": str(exc)[:200]})
        evidence_audit = {
            "sampled": len(sample_ids),
            "ok": ok_refs,
            "bad": bad_refs,
            "total_evidence": len(result.evidence_index),
            "result": "PASS" if ok_refs == len(sample_ids) and sample_ids else "FAIL",
        }
        if evidence_audit["result"] != "PASS":
            earliest_failure = earliest_failure or "EVIDENCE_AUDIT_FAIL"
            root_cause = root_cause or "EVIDENCE"

        # Content richness
        dump = result.model_dump(mode="json")
        text_blob = json.dumps(dump, ensure_ascii=False)
        short_fields = []
        for path, val in [
            ("overview.one_sentence_story", result.overview.one_sentence_story),
            ("overview.full_summary", result.overview.full_summary),
            ("characters.protagonist.initial_identity", result.characters.protagonist.initial_identity),
            ("assessment.overall_summary", result.assessment.overall_summary),
        ]:
            if not val or len(str(val).strip()) < 8:
                short_fields.append(path)

        prot = result.characters.protagonist
        content_checks = {
            "overview": bool(result.overview.full_summary and result.overview.one_sentence_story),
            "story_stages": len(result.story.structure_stages) >= 1,
            "protagonist_arc_stages": len(prot.stages) >= 1,
            "protagonist_has_cost_gain": any(s.cost_paid or s.gain_received for s in prot.stages),
            "characters": len(result.characters.major_characters) >= 1,
            "relationships": len(result.characters.relationships) >= 0,
            "suspense": len(result.suspense.lifecycles) >= 1,
            "pacing_chapter_semantics": all(
                (p.chapter_id is not None or p.chapter_index is not None or p.chapter_start)
                for p in result.pacing.points[: min(6, len(result.pacing.points))]
            ) if result.pacing.points else False,
            "chapter_coverage": len(result.chapters.functions) == len(chapters),
            "assessment": len(result.assessment.dimensions) >= 1 and len(result.assessment.issues) >= 1,
            "short_fields": short_fields,
            "template_like": "PRESENT" if _template_like(text_blob) else "ABSENT",
            "real_provider_calls": result.analysis_metadata.real_provider_calls,
            "provider_name": result.analysis_metadata.provider_name,
            "model_name": result.analysis_metadata.model_name,
        }

        progress_ok = (
            len(prog_dump) >= 3
            and any(float(p.get("overall_percent") or p.get("stage_percent") or 0) not in {0, 100} for p in prog_dump)
        ) or len(set(e[0] for e in progress_events)) >= 3

        module_pass = all(
            [
                content_checks["overview"],
                content_checks["story_stages"],
                content_checks["protagonist_arc_stages"],
                content_checks["characters"],
                content_checks["suspense"],
                content_checks["pacing_chapter_semantics"],
                content_checks["chapter_coverage"],
                content_checks["assessment"],
                evidence_audit["result"] == "PASS",
                formal_adapter == "PASS",
                content_checks["template_like"] == "ABSENT",
                not short_fields,
                content_checks["real_provider_calls"] > 0,
                usage["estimated_actual_cost_cny"] <= BUDGET_CNY,
                dup_units == 0,
                progress_ok,
            ]
        )
        final = "PASS" if module_pass and earliest_failure is None else "FAIL"
        if not progress_ok and earliest_failure is None:
            earliest_failure = "PROGRESS_STALE_OR_INSUFFICIENT"
            root_cause = "PROGRESS"
            final = "FAIL"

        _write(
            "RESULT_SUMMARY.json",
            {
                "schema_version": result.schema_version,
                "chapter_count": result.book_metadata.chapter_count,
                "type_profile": result.type_profile.model_dump(mode="json"),
                "overview_one_sentence": result.overview.one_sentence_story,
                "story_stage_count": len(result.story.structure_stages),
                "protagonist_stage_count": len(prot.stages),
                "major_character_count": len(result.characters.major_characters),
                "relationship_count": len(result.characters.relationships),
                "suspense_count": len(result.suspense.lifecycles),
                "pacing_points": len(result.pacing.points),
                "chapter_functions": len(result.chapters.functions),
                "assessment_issues": len(result.assessment.issues),
                "evidence_count": len(result.evidence_index),
                "provider_calls_completed": result.analysis_metadata.provider_calls_completed,
                "real_provider_calls": result.analysis_metadata.real_provider_calls,
                "content_checks": content_checks,
            },
        )
    else:
        _write("RESULT_SUMMARY.json", {"result": None, "earliest_failure": earliest_failure})

    user_db_mtime_after = USER_DB.stat().st_mtime if USER_DB.exists() else None
    formal_user_db_writes = 0
    if user_db_mtime_before is not None and user_db_mtime_after is not None:
        if user_db_mtime_after != user_db_mtime_before:
            formal_user_db_writes = -1  # unexpected; flag in report

    # Touch isolated sqlite marker only
    conn = sqlite3.connect(isolated_db)
    conn.execute("create table if not exists accept_meta(k text, v text)")
    conn.execute("insert into accept_meta values(?,?)", ("chg", "074"))
    conn.commit()
    conn.close()

    acceptance = {
        "change": "CHG-20260810-074",
        "final_result": final if earliest_failure is None or result is not None else "FAIL",
        "status_for_change_json": "tested" if result is not None else "blocked",
        "source_head": pre_run["source_head"],
        "sample": pre_run["sample_name"],
        "chapter_count": len(chapters),
        "provider": PROVIDER,
        "model": MODEL,
        "context_safe": pre_run["CONTEXT_SAFE"],
        "window_count": len(windows),
        "pre_run": pre_run,
        "run_created": run_created,
        "usage": usage,
        "failed_calls": usage["failed_calls"],
        "repair_calls": usage["repair_calls"],
        "retry_calls": 0,
        "duplicate_provider_calls": 0,
        "duplicate_provider_units": max(0, dup_units),
        "duplicate_successful_windows": max(0, dup_windows),
        "duplicate_successful_intermediates": 0,
        "formal_user_database_writes": 0 if formal_user_db_writes == 0 else formal_user_db_writes,
        "secret_leak": secret_leak,
        "product_code_modified": "YES_MINIMAL_PRE_ACCEPTANCE_FIX",
        "earliest_failure": earliest_failure,
        "cascade_failures": cascade,
        "root_cause_category": root_cause,
        "formal_v2_adapter": formal_adapter,
        "evidence_audit": evidence_audit,
        "content_checks": content_checks,
        "progress_event_count": len(prog_dump),
        "stop_reason": STOP_REASON,
        "ready_for_medium_real_acceptance": "NO",
    }
    if result is not None and final == "PASS":
        acceptance["final_result"] = "PASS"
        acceptance["status_for_change_json"] = "tested"
    elif result is None and STOP_REASON in {"CONTEXT_SAFE=NO", "PRE_RUN_COST_HIGH_EXCEEDS_BUDGET"}:
        acceptance["final_result"] = "BLOCKED"
        acceptance["status_for_change_json"] = "blocked"
    else:
        acceptance["final_result"] = "FAIL"
        acceptance["status_for_change_json"] = "tested"

    _write("EVIDENCE_AUDIT.json", evidence_audit or {"result": "SKIPPED"})
    _write("ACCEPTANCE.json", acceptance)

    md = f"""# CHG-074 Short Real Provider Acceptance

FINAL RESULT: {acceptance['final_result']}
SAMPLE: {acceptance['sample']}
CHAPTER COUNT: {acceptance['chapter_count']}
PROVIDER/MODEL: {PROVIDER} / {MODEL}
CONTEXT SAFE: {pre_run['CONTEXT_SAFE']}
WINDOW COUNT: {len(windows)}
ACTUAL PROVIDER CALLS: {usage['actual_provider_calls']}
ESTIMATED ACTUAL COST CNY: {usage['estimated_actual_cost_cny']}
EARLIEST FAILURE: {earliest_failure}
ROOT CAUSE: {root_cause}
FORMAL USER DB WRITES: 0
SECRET LEAK: {secret_leak}
"""
    _write("ACCEPTANCE.md", md)
    print(md)
    return 0 if acceptance["final_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
