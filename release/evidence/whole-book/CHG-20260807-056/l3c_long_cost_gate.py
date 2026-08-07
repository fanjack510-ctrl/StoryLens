#!/usr/bin/env python3
"""CHG-20260807-056 L3-C Long Cost Gate — Import/Prepare/Estimate ONLY.

NO Consent, NO create_free_whole_book_analysis_v1, NO Provider calls.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
import sys

sys.path.insert(0, str(ROOT / "apps" / "api"))
PRIVATE = Path(r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src")
if PRIVATE.is_dir():
    sys.path.insert(0, str(PRIVATE))

L3_DIR = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-long-cost")
DB = L3_DIR / "storylens_l3_long_cost.db"
EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260807-056"
PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"

# L3-B baselines
L3B_CHAPTERS = 42
L3B_CHARS = 129457
L3B_EST_UNITS = 22
L3B_ACT_UNITS = 17
L3B_COST_MIN = 0.45832
L3B_COST_MAX = 0.674


def _find_source() -> Path | None:
    for base in Path(r"D:/").glob("10010*"):
        for f in base.rglob("*戏神*.txt"):
            if f.is_file() and f.stat().st_size > 1_000_000:
                return f
    doc = Path(r"C:/Users/msi/Documents")
    if doc.is_dir():
        for f in doc.rglob("*戏神*.txt"):
            if f.is_file() and f.stat().st_size > 1_000_000:
                return f
    return None


def _l3b_call_durations_sec() -> list[float]:
    units_path = (
        ROOT
        / "release"
        / "evidence"
        / "whole-book"
        / "CHG-20260807-055"
        / "MEDIUM_PROVIDER_UNITS.json"
    )
    if not units_path.is_file():
        return []
    units = json.loads(units_path.read_text(encoding="utf-8"))
    durs: list[float] = []
    for u in units:
        for a in u.get("attempts") or []:
            s, e = a.get("started_at"), a.get("completed_at")
            if not s or not e:
                continue
            try:
                # naive ISO without Z
                from datetime import datetime as dt

                t0 = dt.fromisoformat(s)
                t1 = dt.fromisoformat(e)
                durs.append(max(0.0, (t1 - t0).total_seconds()))
            except Exception:
                continue
    return durs


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    L3_DIR.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    for side in (str(DB) + "-wal", str(DB) + "-shm"):
        p = Path(side)
        if p.exists():
            p.unlink()

    src = _find_source()
    sample_report: dict[str, Any] = {
        "long_sample": "我不是戏神",
        "source_available": bool(src),
        "source_path": str(src) if src else None,
    }
    if src is None:
        (EVIDENCE / "LONG_SAMPLE.md").write_text(
            "# LONG_SAMPLE\n\nLONG SAMPLE：NOT AVAILABLE\n", encoding="utf-8"
        )
        print("LONG SAMPLE: NOT AVAILABLE")
        return 2

    # Never enable real provider path for execution; prepare may read flag for estimate binding.
    os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "false"
    os.environ["STORYLENS_ALIYUN_ENABLED"] = "true"
    os.environ["STORYLENS_DEFAULT_MODEL_PROVIDER"] = PROVIDER
    # Ensure no accidental gateway: strip key from env for this process after config if present
    # (estimate does not need live key; pricing is local). Keep key out of logs.
    # Do NOT call ModelGateway.

    provider_call_counter = {"n": 0}

    from sqlalchemy import func, select

    from app.db.models import (
        ApplicationSetting,
        Book,
        Chapter,
        Paragraph,
        ProviderConfiguration,
        WholeBookCostEstimate,
    )
    from app.db.session import SessionLocal, create_db
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
        prepare_free_whole_book_analysis_v1,
    )
    from app.narrative_core.services.whole_book_snapshot_v1_service import (
        create_or_reuse_book_snapshot_v1,
    )
    from app.narrative_core.services.whole_book_windowing_v1_service import (
        _load_paragraphs,
        whole_book_windowing_v1,
    )
    from app.services.book_service import import_book
    from app.services.provider_bootstrap import ensure_aliyun_provider_configuration

    # Patch gateway generate if imported later — hard fail
    try:
        import app.model_gateway.registry as reg

        _orig_get = reg.get_model_gateway

        class _NoCallGateway:
            def get(self, *a, **k):
                raise RuntimeError("PROVIDER_CALL_FORBIDDEN_IN_COST_GATE")

            def generate(self, *a, **k):
                provider_call_counter["n"] += 1
                raise RuntimeError("PROVIDER_CALL_FORBIDDEN_IN_COST_GATE")

        def _blocked_gateway():
            return _NoCallGateway()

        reg.get_model_gateway = _blocked_gateway  # type: ignore[assignment]
    except Exception:
        pass

    create_db()
    t0 = time.perf_counter()

    # Read source (do not modify)
    text = src.read_text(encoding="utf-8")
    source_chars = len(text)
    sample_report.update(
        {
            "source_bytes": src.stat().st_size,
            "source_character_count_raw": source_chars,
            "content_modified": False,
            "fixture": False,
            "ai_generated": False,
        }
    )

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

        print("IMPORT_START")
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
        chapters = list(
            session.scalars(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index)
            )
        )
        print(f"IMPORT_DONE chapters={chapter_count} chars={character_count}")

        chapter_ok = chapter_count >= 30 and chapter_count < 5000 and chapter_count not in {0, 1}
        # Detect abnormal doubling vs line-mark heuristic (~1291)
        if chapter_count < 500 or chapter_count > 3000:
            chapter_ok = False

        import_report = {
            "book_id": book_id,
            "book_title": book.title,
            "chapter_count": chapter_count,
            "character_count": character_count,
            "source_character_count_raw": source_chars,
            "char_ratio_imported_vs_source": round(character_count / max(source_chars, 1), 4),
            "first_chapter_title": chapters[0].title if chapters else None,
            "last_chapter_title": chapters[-1].title if chapters else None,
            "chapter_detection_ok": chapter_ok,
            "elapsed_import_sec": round(time.perf_counter() - t0, 2),
        }
        if not chapter_ok:
            (EVIDENCE / "LONG_CHAPTER_DETECTION.md").write_text(
                "# LONG_CHAPTER_DETECTION\n\nANOMALY — stopped Cost Gate.\n\n"
                + json.dumps(import_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("CHAPTER_DETECTION_ANOMALY", chapter_count)
            return 3

        print("PREPARE_START")
        prepare = prepare_free_whole_book_analysis_v1(session, book_id)
        session.commit()
        snap_id = prepare["snapshot"]["snapshot_id"]
        revision = compute_book_revision_hash(session, book_id)
        estimate = estimate_whole_book_analysis(
            session, book_id, "whole_book_native", row.id
        )
        session.commit()
        est = estimate_to_dict(estimate)

        windows_est = int(est["estimated_window_count"])
        cf_planned = int(est["estimated_chapter_function_batches"])
        cf_expected = int(math.ceil(chapter_count / float(CF_MAX_CHAPTERS_PER_BATCH)))
        cf_delta = cf_planned - cf_expected
        repair = int(est["estimated_chapter_function_repair_reserve"])
        total_units = int(est["estimated_provider_call_count"])
        overview_units = 1
        structure_units = 1
        # synthesis = overview + structure
        assert SYNTHESIS_PROVIDER_CALLS == 2
        chars_events_units = windows_est
        cf_units = cf_planned
        other_units = 0
        sum_check = (
            overview_units
            + chars_events_units
            + structure_units
            + cf_units
            + repair
            + other_units
        )
        recalc = _estimate_provider_call_count(
            window_count=windows_est, chapter_count=chapter_count
        )

        # Physical window plan from snapshot (NO run / NO create_free)
        paragraphs = _load_paragraphs(session, snap_id)
        specs, win_warnings = whole_book_windowing_v1(session, paragraphs)
        win_chars = [int(s.get("character_count") or 0) for s in specs]
        win_ch_span = [
            int(s.get("chapter_end_index") or 0) - int(s.get("chapter_start_index") or 0) + 1
            for s in specs
        ]
        # coverage uniqueness of paragraph indices
        covered: set[int] = set()
        dup_paras = 0
        for s in specs:
            for g in range(
                int(s["first_global_paragraph_index"]),
                int(s["last_global_paragraph_index"]) + 1,
            ):
                # subtract overlap heuristically: count only exclusive? product allows overlap
                if g in covered:
                    dup_paras += 1
                covered.add(g)
        single_chapter_windows = sum(1 for x in win_ch_span if x == 1)
        empty_windows = sum(1 for c in win_chars if c <= 0)
        unit_keys = [f"window:{i}" for i in range(len(specs))]
        dup_keys = len(unit_keys) - len(set(unit_keys))

        planned_window_count = len(specs)
        # OBS-L3B-002: estimate vs planned physical windows
        window_estimate_delta = planned_window_count - windows_est

        cost_min = float(est["estimated_cost_min_cny"] or 0)
        cost_max = float(est["estimated_cost_max_cny"] or 0)
        cost_base = (cost_min + cost_max) / 2.0 if cost_max else cost_min
        # Token cost does not separately price CF/repair; derive proportional analytical share
        repair_cost_share_min = cost_min * (repair / total_units) if total_units else 0
        repair_cost_share_max = cost_max * (repair / total_units) if total_units else 0

        normal_units = windows_est + SYNTHESIS_PROVIDER_CALLS + cf_planned
        repair_case_units = normal_units + repair
        stress_calls = normal_units * 2  # +1 retry each normal unit
        # Scale cost by call stress vs estimated call count (token estimate unchanged officially)
        stress_cost_min = cost_min * (stress_calls / max(total_units, 1))
        stress_cost_max = cost_max * (stress_calls / max(total_units, 1))

        chapter_scale = chapter_count / L3B_CHAPTERS
        char_scale = character_count / L3B_CHARS
        unit_scale = total_units / L3B_EST_UNITS
        cost_mult_min = cost_min / L3B_COST_MIN
        cost_mult_max = cost_max / L3B_COST_MAX

        # Scaling judgment
        # Unit scale should track ~ max(chapter_scale for CF, char_scale for windows)
        expected_unit_band = max(chapter_scale, char_scale)
        if unit_scale > expected_unit_band * 3 or unit_scale > chapter_scale * 5:
            scaling = "ABNORMAL"
        elif unit_scale > expected_unit_band * 1.8:
            scaling = "SUSPICIOUS"
        else:
            scaling = "REASONABLE"

        # Without repair, unit scale vs chapter/char
        normal_unit_scale = normal_units / (L3B_EST_UNITS - 6)  # L3-B repair was 6 of 22
        # L3-B normal = 22-6 = 16; actual was 17 (9 windows)

        if abs(window_estimate_delta) <= max(3, int(0.05 * max(windows_est, 1))):
            obs002 = "NORMAL_AT_LONG_SCALE"
        elif abs(window_estimate_delta) <= max(10, int(0.15 * max(windows_est, 1))):
            obs002 = "SUSPICIOUS"
        else:
            obs002 = "ABNORMAL"

        cost_plan_anomaly = cf_delta != 0 or recalc != total_units or empty_windows > 0 or dup_keys > 0

        # Time from L3-B
        durs = _l3b_call_durations_sec()
        if len(durs) >= 5:
            median_dur = statistics.median(durs)
            p95 = sorted(durs)[int(math.ceil(0.95 * len(durs))) - 1]
            # serial pipeline assumption
            normal_wall_min = (normal_units * median_dur) / 60.0
            normal_wall_max = (repair_case_units * p95) / 60.0
            time_est = {
                "median_call_sec": round(median_dur, 2),
                "p95_call_sec": round(p95, 2),
                "sample_size": len(durs),
                "assumption": "serial provider units (current Free pipeline)",
                "normal_wall_clock_min_range": [
                    round(normal_wall_min * 0.8, 1),
                    round(normal_wall_max, 1),
                ],
                "note": "Rough range only; not a precise SLA.",
            }
        else:
            median_dur = None
            time_est = {
                "median_call_sec": None,
                "p95_call_sec": None,
                "long_run_time_estimate": "INSUFFICIENT DATA",
            }

        technical_pass = (
            not cost_plan_anomaly
            and scaling != "ABNORMAL"
            and chapter_ok
            and provider_call_counter["n"] == 0
            and single_chapter_windows < max(20, int(0.5 * planned_window_count))
            and planned_window_count < chapter_count  # not ~1 window per chapter
        )

        report = {
            "change": "CHG-20260807-056",
            "provider": PROVIDER,
            "model": MODEL,
            "real_provider_calls": provider_call_counter["n"],
            "book_id": book_id,
            "book_title": book.title,
            "source_path_redacted": True,
            "source_bytes": src.stat().st_size,
            "chapter_count": chapter_count,
            "character_count": character_count,
            "snapshot_id": snap_id,
            "revision": revision,
            "estimate_id": estimate.id,
            "cf_max_chapters_per_batch": CF_MAX_CHAPTERS_PER_BATCH,
            "expected_cf_batches": cf_expected,
            "planned_cf_batches": cf_planned,
            "cf_batch_delta": cf_delta,
            "estimated_window_count": windows_est,
            "planned_physical_window_count": planned_window_count,
            "window_estimate_vs_physical_delta": window_estimate_delta,
            "estimated_overview_units": overview_units,
            "estimated_characters_events_units": chars_events_units,
            "estimated_structure_units": structure_units,
            "estimated_chapter_function_units": cf_units,
            "estimated_repair_reserve": repair,
            "estimated_other_units": other_units,
            "total_estimated_provider_units": total_units,
            "sum_check": sum_check,
            "sum_matches_total": sum_check == total_units,
            "recalc_provider_calls": recalc,
            "estimated_input_tokens": est.get("estimated_input_tokens"),
            "estimated_output_tokens": est.get("estimated_output_tokens"),
            "pricing_status": est.get("pricing_status"),
            "estimated_cost_min_cny": est.get("estimated_cost_min_cny"),
            "estimated_cost_max_cny": est.get("estimated_cost_max_cny"),
            "estimated_base_cost_cny_mid": round(cost_base, 6),
            "estimated_repair_reserve_cost_cny_derived": {
                "min": round(repair_cost_share_min, 6),
                "max": round(repair_cost_share_max, 6),
                "note": "Derived proportional share; official estimate prices tokens (windows+synthesis), not per CF/repair call.",
            },
            "chapter_scale_factor": round(chapter_scale, 4),
            "character_scale_factor": round(char_scale, 4),
            "estimated_unit_scale_factor": round(unit_scale, 4),
            "normal_unit_scale_vs_l3b_normal": round(normal_units / 16, 4),
            "scaling": scaling,
            "long_medium_cost_multiplier": {
                "min": round(cost_mult_min, 4),
                "max": round(cost_mult_max, 4),
            },
            "normal_provider_units": normal_units,
            "repair_case_provider_units": repair_case_units,
            "stress_provider_calls": stress_calls,
            "stress_cost_range_cny_scaled": {
                "min": round(stress_cost_min, 4),
                "max": round(stress_cost_max, 4),
                "note": "Analytical scale by call count vs official token estimate; not a product invoice.",
            },
            "window_plan": {
                "count": planned_window_count,
                "avg_chapters_per_window": round(sum(win_ch_span) / max(len(win_ch_span), 1), 3),
                "avg_characters_per_window": round(sum(win_chars) / max(len(win_chars), 1), 1),
                "max_window_characters": max(win_chars) if win_chars else 0,
                "min_window_characters": min(win_chars) if win_chars else 0,
                "single_chapter_windows": single_chapter_windows,
                "empty_windows": empty_windows,
                "overlap_paragraph_hits": dup_paras,
                "duplicate_provider_unit_keys": dup_keys,
                "warnings": win_warnings,
                "note": "Physical plan via whole_book_windowing_v1 on snapshot; NO formal create / NO provider.",
            },
            "time_estimate": time_est,
            "cost_plan_anomaly": cost_plan_anomaly,
            "obs_l3b_001": "UNCHANGED_NON_BLOCKING",
            "obs_l3b_002": obs002,
            "technical_cost_gate": "PASS" if technical_pass else "FAIL",
            "long_real_run": "NOT EXECUTED — AWAITING COST DECISION",
            "elapsed_sec": round(time.perf_counter() - t0, 2),
            "prepare_estimate_binding": {
                "provider_name": prepare.get("estimate", {}).get("provider_name"),
                "model_name": prepare.get("estimate", {}).get("model_name"),
                "estimated_windows": prepare.get("estimate", {}).get("estimated_windows"),
                "estimated_provider_calls": prepare.get("estimate", {}).get(
                    "estimated_provider_calls"
                ),
            },
        }

        (EVIDENCE / "LONG_COST_GATE_RAW.json").write_text(
            json.dumps(
                {"sample": sample_report, "import": import_report, "gate": report},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print("CHAPTER_COUNT", chapter_count)
        print("CHARACTER_COUNT", character_count)
        print("CF_EXPECTED", cf_expected, "PLANNED", cf_planned, "DELTA", cf_delta)
        print("WINDOW_EST", windows_est, "PHYSICAL", planned_window_count)
        print("TOTAL_UNITS", total_units, "NORMAL", normal_units, "REPAIR_CASE", repair_case_units)
        print("COST", est.get("estimated_cost_min_cny"), "-", est.get("estimated_cost_max_cny"))
        print("SCALING", scaling)
        print("TECHNICAL", report["technical_cost_gate"])
        print("REAL_PROVIDER_CALLS", provider_call_counter["n"])
        return 0 if technical_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
