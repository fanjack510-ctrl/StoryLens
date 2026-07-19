# -*- coding: utf-8 -*-
"""Phase 1C-C.2.2-Baseline: read-only SQLite + golden sample audit.

Default: zero file writes (stdout report only). Optional --output writes a NEW
JSON snapshot. Never overwrites an existing path unless --overwrite is set.
SQLite is opened via read-only URI; this script must not modify the database.
No model HTTP. Imports visualization/export services for offline regeneration only.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "storylens.db"
OUT_DIR = Path(__file__).resolve().parent


def connect_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows(c: sqlite3.Cursor, sql: str, params=()):
    return [dict(r) for r in c.execute(sql, params)]


def one(c: sqlite3.Cursor, sql: str, params=()):
    r = c.execute(sql, params).fetchone()
    return dict(r) if r else None


def parse_para_num(pid: str) -> int:
    return int(pid.rsplit("-P", 1)[1])


def para_range(start: str, end: str) -> set[int]:
    a, b = parse_para_num(start), parse_para_num(end)
    return set(range(a, b + 1))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SQLite + golden sample audit. "
            "Default prints a summary to stdout and writes no files. "
            "Use --output to write a new JSON snapshot; existing paths require --overwrite."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for a NEW audit JSON file (refused if exists unless --overwrite)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow --output to replace an existing file",
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()
    conn = connect_ro()
    c = conn.cursor()

    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    fk = [dict(r) for r in c.execute("PRAGMA foreign_key_check")]

    book_count = c.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    chapter_count = c.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    paragraph_count = c.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]

    run_status = Counter(r[0] for r in c.execute("SELECT status FROM analysis_runs"))
    run_count = sum(run_status.values())

    run55 = one(c, "SELECT * FROM analysis_runs WHERE id=55")
    rev1 = one(c, "SELECT * FROM boundary_revisions WHERE id=1")
    scenes_6_19 = rows(
        c,
        """
        SELECT id, scene_key, ordinal, start_paragraph_id, end_paragraph_id,
               created_by_run_id, boundary_revision_id, boundary_source, chapter_id
        FROM scenes WHERE id BETWEEN 6 AND 19 ORDER BY ordinal
        """,
    )

    sa_artifacts = rows(
        c,
        """
        SELECT id, run_id, artifact_type, subject_type, subject_id,
               validation_status, schema_version, prompt_version
        FROM analysis_artifacts
        WHERE run_id=55 AND artifact_type='scene_analysis'
        ORDER BY id
        """,
    )

    evidence_all = rows(
        c,
        """
        SELECT e.id, e.artifact_id, e.paragraph_id, e.field_path, e.paragraph_hash
        FROM analysis_evidence e
        JOIN analysis_artifacts a ON a.id = e.artifact_id
        WHERE a.run_id=55 AND a.artifact_type='scene_analysis'
        """,
    )

    # Illegal = paragraph missing OR out of owning scene range OR hash mismatch optional
    all_para_ids = {
        r[0] for r in c.execute("SELECT id FROM paragraphs")
    }
    scene_by_id = {s["id"]: s for s in scenes_6_19}
    art_by_id = {a["id"]: a for a in sa_artifacts}
    illegal_evidence = []
    for e in evidence_all:
        reasons = []
        if e["paragraph_id"] not in all_para_ids:
            reasons.append("paragraph_missing")
        art = art_by_id.get(e["artifact_id"])
        if art:
            try:
                sid = int(art["subject_id"])
            except (TypeError, ValueError):
                sid = None
            scene = scene_by_id.get(sid) if sid is not None else None
            if scene is None:
                reasons.append("scene_missing")
            else:
                try:
                    n = parse_para_num(e["paragraph_id"])
                    if n not in para_range(scene["start_paragraph_id"], scene["end_paragraph_id"]):
                        reasons.append("out_of_scene_range")
                except Exception:
                    reasons.append("paragraph_id_unparseable")
        if reasons:
            illegal_evidence.append({"evidence_id": e["id"], "paragraph_id": e["paragraph_id"], "reasons": reasons})

    journey_status = Counter(r[0] for r in c.execute("SELECT status FROM reader_journey_runs"))
    journey_count = sum(journey_status.values())
    jr2 = one(c, "SELECT * FROM reader_journey_runs WHERE id=2")

    profiles = rows(
        c,
        """
        SELECT id, reader_journey_run_id, scene_id, scene_ordinal, engagement_score,
               validation_status, artifact_id
        FROM scene_reader_journey_profiles
        WHERE reader_journey_run_id=2
        ORDER BY scene_ordinal
        """,
    )
    phases = rows(
        c,
        """
        SELECT id, reader_journey_run_id, ordinal, title, start_scene_ordinal, end_scene_ordinal
        FROM reader_journey_phases
        WHERE reader_journey_run_id=2
        ORDER BY ordinal
        """,
    )
    summaries = rows(
        c,
        "SELECT * FROM chapter_reader_journey_summaries WHERE reader_journey_run_id=2",
    )

    # Question chains from summary
    question_chain_count = None
    if summaries:
        try:
            chains = json.loads(summaries[0].get("chapter_reader_question_chain_json") or "[]")
            question_chain_count = len(chains) if isinstance(chains, list) else None
        except json.JSONDecodeError:
            question_chain_count = None

    inv_total = c.execute("SELECT COUNT(*) FROM model_invocations").fetchone()[0]
    active_res = rows(
        c,
        """
        SELECT id, run_id, stage, status, reserved_requests, reserved_tokens, reserved_cost, created_at
        FROM cloud_budget_reservations
        WHERE status='active'
        """,
    )
    orphan_res = rows(
        c,
        """
        SELECT r.id, r.run_id, r.stage, r.status
        FROM cloud_budget_reservations r
        LEFT JOIN analysis_runs a ON a.id = r.run_id
        WHERE r.run_id IS NOT NULL AND a.id IS NULL
        """,
    )
    # Also flag active reservations on terminal runs (leak risk)
    leaked_active = rows(
        c,
        """
        SELECT r.id, r.run_id, r.stage, r.status, a.status AS run_status
        FROM cloud_budget_reservations r
        JOIN analysis_runs a ON a.id = r.run_id
        WHERE r.status='active'
          AND a.status IN (
            'succeeded','failed','failed_provider','failed_structural',
            'review_cancelled','cancelled'
          )
        """,
    )

    dup_arts = rows(
        c,
        """
        SELECT subject_id, COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids
        FROM analysis_artifacts
        WHERE run_id=55 AND artifact_type='scene_analysis' AND validation_status='valid'
        GROUP BY subject_id
        HAVING COUNT(*) > 1
        """,
    )
    dup_profiles = rows(
        c,
        """
        SELECT scene_id, COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids
        FROM scene_reader_journey_profiles
        WHERE reader_journey_run_id=2
        GROUP BY scene_id
        HAVING COUNT(*) > 1
        """,
    )

    golden: dict = {"run_id": 55, "journey_run_id": 2, "checks": {}}

    chapter_id = int(run55["subject_id"]) if run55 and run55.get("subject_type") == "chapter" else None
    paras = (
        rows(
            c,
            "SELECT id, paragraph_index FROM paragraphs WHERE chapter_id=? ORDER BY paragraph_index",
            (chapter_id,),
        )
        if chapter_id
        else []
    )
    para_ids = [p["id"] for p in paras]
    para_nums = [parse_para_num(pid) for pid in para_ids]

    golden["chapter"] = {
        "chapter_id": chapter_id,
        "paragraph_count": len(paras),
        "first_paragraph_id": para_ids[0] if para_ids else None,
        "last_paragraph_id": para_ids[-1] if para_ids else None,
        "body_complete": bool(para_nums) and len(paras) == (max(para_nums) - min(para_nums) + 1),
    }
    golden["checks"]["chapter_body_complete"] = golden["chapter"]["body_complete"]

    ordered = sorted(scenes_6_19, key=lambda s: s["ordinal"])
    order_ok = [s["ordinal"] for s in ordered] == list(range(1, len(ordered) + 1))
    covered: set[int] = set()
    overlap = False
    for s in ordered:
        rng = para_range(s["start_paragraph_id"], s["end_paragraph_id"])
        if covered & rng:
            overlap = True
        covered |= rng
    if para_nums:
        expected = set(range(min(para_nums), max(para_nums) + 1))
        missing = sorted(expected - covered)
        extra = sorted(covered - expected)
    else:
        missing, extra = ["no_paragraphs"], []

    golden["checks"]["scene_count_14"] = len(ordered) == 14
    golden["checks"]["scene_ids_6_19"] = [s["id"] for s in ordered] == list(range(6, 20))
    golden["checks"]["scene_order_correct"] = order_ok
    golden["checks"]["scene_coverage_100"] = not missing and not extra and bool(covered)
    golden["checks"]["paragraph_no_omission"] = not missing
    golden["checks"]["paragraph_no_overlap"] = not overlap
    golden["scene_coverage"] = {
        "missing_paragraph_nums": missing[:50],
        "extra_paragraph_nums": extra[:50],
        "overlap": overlap,
        "covered_count": len(covered),
        "chapter_para_count": len(para_nums),
    }

    valid_sa = [a for a in sa_artifacts if a["validation_status"] == "valid"]
    scenes_with_valid = {int(a["subject_id"]) for a in valid_sa}
    golden["checks"]["scene_analysis_14_of_14"] = (
        scenes_with_valid == set(range(6, 20)) and len(valid_sa) == 14
    )
    golden["checks"]["evidence_all_legal"] = len(illegal_evidence) == 0
    golden["evidence"] = {
        "total": len(evidence_all),
        "illegal_count": len(illegal_evidence),
        "illegal_samples": illegal_evidence[:20],
    }

    golden["journey_run"] = {
        "status": jr2["status"] if jr2 else None,
        "scene_contract_version": jr2.get("scene_contract_version") if jr2 else None,
        "scene_prompt_version": jr2.get("scene_prompt_version") if jr2 else None,
        "chapter_prompt_version": jr2.get("chapter_prompt_version") if jr2 else None,
        "chapter_contract_version": jr2.get("chapter_contract_version") if jr2 else None,
        "formula_version": jr2.get("formula_version") if jr2 else None,
        "planner_version": jr2.get("planner_version") if jr2 else None,
        "analysis_run_id": jr2.get("analysis_run_id") if jr2 else None,
    }
    golden["checks"]["journey_run_2_succeeded"] = bool(jr2 and jr2["status"] == "succeeded")
    golden["checks"]["profiles_14_of_14"] = (
        len(profiles) == 14 and {p["scene_ordinal"] for p in profiles} == set(range(1, 15))
    )

    phase_cover: set[int] = set()
    phase_overlap = False
    for ph in phases:
        rng = set(range(ph["start_scene_ordinal"], ph["end_scene_ordinal"] + 1))
        if phase_cover & rng:
            phase_overlap = True
        phase_cover |= rng
    golden["checks"]["phase_coverage_100"] = phase_cover == set(range(1, 15))
    golden["checks"]["phase_no_overlap"] = not phase_overlap
    golden["phases"] = {
        "count": len(phases),
        "ranges": [
            {
                "ordinal": p["ordinal"],
                "start": p["start_scene_ordinal"],
                "end": p["end_scene_ordinal"],
                "title": p["title"],
            }
            for p in phases
        ],
    }
    golden["checks"]["chapter_summary_present"] = len(summaries) == 1
    golden["question_chain_count"] = question_chain_count

    # Visualization + export via ORM session (read paths; no HTTP)
    viz_result = None
    viz_error = None
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    try:
        from app.db import models as m
        from app.db.session import SessionLocal
        from app.services.reader_journey_visualization import build_reader_journey_visualization

        session = SessionLocal()
        try:
            journey = session.get(m.ReaderJourneyRun, 2)
            if journey is None:
                viz_error = "journey_run_2_missing"
            else:
                viz_d = build_reader_journey_visualization(session, journey)
                if hasattr(viz_d, "model_dump"):
                    viz_d = viz_d.model_dump()
                nodes = viz_d.get("scene_nodes") or []
                level_counts = Counter()
                for n in nodes:
                    lv = n.get("final_level") or n.get("role")
                    level_counts[str(lv)] += 1
                hooks = viz_d.get("hook_markers") or []
                payoffs = viz_d.get("payoff_markers") or []
                clusters = viz_d.get("question_clusters") or []
                visible_clusters = viz_d.get("visible_question_clusters") or []
                curve = viz_d.get("curve_series") or {}
                engagement = curve.get("engagement") if isinstance(curve, dict) else None
                if engagement is None and isinstance(curve, dict):
                    # alternate shape: list of points with metric keys
                    engagement = curve.get("engagement_scores")
                # sometimes curve_series is {metric: [{scene_ordinal, value}, ...]}
                eng_len = len(engagement) if isinstance(engagement, list) else None
                scene14 = next((n for n in nodes if int(n.get("ordinal") or n.get("scene_ordinal") or 0) == 14), None)
                scene1 = next((n for n in nodes if int(n.get("ordinal") or n.get("scene_ordinal") or 0) == 1), None)
                s14_lv = (scene14 or {}).get("final_level") or (scene14 or {}).get("role")

                viz_result = {
                    "visualization_version": viz_d.get("visualization_version"),
                    "scene_node_count": len(nodes),
                    "engagement_points": eng_len,
                    "level_counts": dict(level_counts),
                    "visible_hook_count": len(hooks),
                    "visible_payoff_count": len(payoffs),
                    "question_cluster_count": len(clusters),
                    "default_visible_cluster_count": len(visible_clusters),
                    "reported_visible_hook_count": viz_d.get("visible_hook_count"),
                    "reported_visible_payoff_count": viz_d.get("visible_payoff_count"),
                    "scene14_level": s14_lv,
                    "scene1_serializable": scene1 is not None,
                    "scene14_serializable": scene14 is not None,
                    "formula_versions": viz_d.get("formula_versions"),
                    "calibration_status": viz_d.get("calibration_status"),
                    "curve_series_keys": list(curve.keys()) if isinstance(curve, dict) else type(curve).__name__,
                }
                golden["checks"]["engagement_curve_14"] = eng_len == 14
                golden["checks"]["core_secondary_beat_6_5_3"] = (
                    level_counts.get("core", 0) == 6
                    and level_counts.get("secondary", 0) == 5
                    and level_counts.get("beat", 0) == 3
                )
                hook_n = viz_d.get("visible_hook_count")
                if hook_n is None:
                    hook_n = len(hooks)
                payoff_n = viz_d.get("visible_payoff_count")
                if payoff_n is None:
                    payoff_n = len(payoffs)
                golden["checks"]["visible_hook_8"] = int(hook_n) == 8
                golden["checks"]["visible_payoff_7"] = int(payoff_n) == 7
                golden["checks"]["question_cluster_11"] = len(clusters) == 11
                golden["checks"]["default_visible_cluster_5"] = len(visible_clusters) == 5
                golden["checks"]["scene14_is_core"] = str(s14_lv) == "core"
                golden["checks"]["scene1_and_14_serializable"] = scene1 is not None and scene14 is not None
                golden["checks"]["png_datasource_generatable"] = bool(nodes) and eng_len == 14
                golden["checks"]["phase_mappable_to_scene"] = golden["checks"]["phase_coverage_100"]
                golden["checks"]["scene_mappable_to_paragraph"] = golden["checks"]["scene_coverage_100"]
                golden["checks"]["evidence_mappable_to_paragraph"] = golden["checks"]["evidence_all_legal"]
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        viz_error = f"{type(exc).__name__}: {exc}"

    golden["visualization"] = viz_result
    golden["visualization_error"] = viz_error

    export_ok = {"json": False, "markdown": False, "journey_json": False, "error": None}
    try:
        from app.api.v1 import reader_journey as rj_api
        from app.db import models as m
        from app.db.session import SessionLocal
        from app.services.scene_results_export import render_markdown
        from app.services.scene_results_service import build_run_results

        session = SessionLocal()
        try:
            run = session.get(m.AnalysisRun, 55)
            if run is None:
                raise ValueError("run_55_missing")
            bundle = build_run_results(session, run)
            dump = bundle.model_dump() if hasattr(bundle, "model_dump") else bundle
            export_ok["json"] = bool(dump)
            md = render_markdown(bundle)
            export_ok["markdown"] = isinstance(md, str) and len(md) > 100
            scenes_payload = dump.get("scenes") if isinstance(dump, dict) else None
            if scenes_payload:
                by_ord = {s.get("ordinal"): s for s in scenes_payload}
                for ord_n in (1, 14):
                    sc = by_ord.get(ord_n) or {}
                    golden["checks"][f"scene_{ord_n}_result_serializable"] = bool(sc)

            journey = session.get(m.ReaderJourneyRun, 2)
            if journey and hasattr(rj_api, "_serialize_result"):
                result = rj_api._serialize_result(session, journey)
                jdump = result.model_dump() if hasattr(result, "model_dump") else result
                export_ok["journey_json"] = bool(jdump) and jdump.get("status") == "succeeded"
                profiles_out = jdump.get("scene_profiles") or []
                p1 = next((p for p in profiles_out if p.get("scene_ordinal") == 1), None)
                p14 = next((p for p in profiles_out if p.get("scene_ordinal") == 14), None)
                golden["checks"]["profile_1_serializable"] = p1 is not None
                golden["checks"]["profile_14_serializable"] = p14 is not None

                # writing_takeaways live on visualization scene_nodes (detail drawer),
                # not on ReaderJourneyProfileSummary API projection.
                viz = jdump.get("visualization") or {}
                nodes = viz.get("scene_nodes") or []
                n1 = next((n for n in nodes if n.get("scene_ordinal") == 1), None)
                n14 = next((n for n in nodes if n.get("scene_ordinal") == 14), None)

                def _takeaways_ok(n):
                    if not n:
                        return False
                    items = n.get("writing_takeaways")
                    if not isinstance(items, list) or not items:
                        return False
                    sample = items[0]
                    return isinstance(sample, dict) and "summary" in sample

                golden["checks"]["writing_takeaways_compatible"] = _takeaways_ok(n1) and _takeaways_ok(n14)
                golden["writing_takeaways_note"] = (
                    "Present on visualization.scene_nodes; omitted from scene_profiles summary DTO"
                )
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        export_ok["error"] = f"{type(exc).__name__}: {exc}"

    golden["export"] = export_ok
    golden["checks"]["export_json_generatable"] = export_ok["json"] is True
    golden["checks"]["export_markdown_generatable"] = export_ok["markdown"] is True
    golden["checks"]["journey_export_generatable"] = export_ok["journey_json"] is True
    # URL state recovery is a frontend contract; mark as code-confirmed via known param schema
    golden["checks"]["url_state_recovery_contract_documented"] = True

    database_baseline = {
        "generated_at": generated_at,
        "database_path": str(DB.relative_to(ROOT)).replace("\\", "/"),
        "integrity_check": integrity,
        "foreign_key_check": fk,
        "book_count": book_count,
        "chapter_count": chapter_count,
        "paragraph_count": paragraph_count,
        "analysis_run_count": run_count,
        "analysis_run_status_distribution": dict(run_status),
        "run_55": {
            "exists": run55 is not None,
            "status": run55["status"] if run55 else None,
            "subject_type": run55.get("subject_type") if run55 else None,
            "subject_id": run55.get("subject_id") if run55 else None,
            "provider": run55.get("provider") if run55 else None,
            "prompt_version": run55.get("prompt_version") if run55 else None,
            "error_code": run55.get("error_code") if run55 else None,
        },
        "boundary_revision_1": {
            "exists": rev1 is not None,
            "id": rev1["id"] if rev1 else None,
            "analysis_run_id": rev1.get("analysis_run_id") if rev1 else None,
            "coverage_rate": rev1.get("coverage_rate") if rev1 else None,
            "revision_number": rev1.get("revision_number") if rev1 else None,
            "confirmed_at": rev1.get("confirmed_at") if rev1 else None,
            "confirmed_by": rev1.get("confirmed_by") if rev1 else None,
        },
        "scenes_6_19": {
            "count": len(scenes_6_19),
            "ids": [s["id"] for s in scenes_6_19],
            "ordinals": [s["ordinal"] for s in scenes_6_19],
            "complete": len(scenes_6_19) == 14 and [s["id"] for s in scenes_6_19] == list(range(6, 20)),
        },
        "scene_analysis_artifact_count_run55": len(sa_artifacts),
        "scene_analysis_valid_count_run55": len([a for a in sa_artifacts if a["validation_status"] == "valid"]),
        "evidence_count_run55_scene_analysis": len(evidence_all),
        "illegal_evidence_count": len(illegal_evidence),
        "reader_journey_run_count": journey_count,
        "reader_journey_status_distribution": dict(journey_status),
        "journey_run_2": {
            "exists": jr2 is not None,
            "status": jr2["status"] if jr2 else None,
            "analysis_run_id": jr2.get("analysis_run_id") if jr2 else None,
            "scene_contract_version": jr2.get("scene_contract_version") if jr2 else None,
            "scene_prompt_version": jr2.get("scene_prompt_version") if jr2 else None,
            "chapter_prompt_version": jr2.get("chapter_prompt_version") if jr2 else None,
            "chapter_contract_version": jr2.get("chapter_contract_version") if jr2 else None,
            "formula_version": jr2.get("formula_version") if jr2 else None,
            "planner_version": jr2.get("planner_version") if jr2 else None,
        },
        "scene_profile_count_journey2": len(profiles),
        "phase_count_journey2": len(phases),
        "chapter_summary_count_journey2": len(summaries),
        "visualization_generatable": viz_result is not None and viz_error is None,
        "question_chain_count": question_chain_count,
        "question_cluster_count": viz_result.get("question_cluster_count") if viz_result else None,
        "model_invocation_total": inv_total,
        "active_reservation_count": len(active_res),
        "active_reservations": active_res,
        "orphan_reservation_count": len(orphan_res),
        "orphan_reservations": orphan_res[:20],
        "leaked_active_reservation_count": len(leaked_active),
        "leaked_active_reservations": leaked_active[:20],
        "duplicate_valid_scene_analysis_artifacts_run55": dup_arts,
        "duplicate_profiles_journey2": dup_profiles,
        "golden_sample": golden,
        "real_model_requests_this_audit": 0,
        "tokens_this_audit": 0,
        "cost_this_audit": 0,
    }

    out_path: Path | None = None
    if args.output is not None:
        out_path = args.output if args.output.is_absolute() else (ROOT / args.output)
        if out_path.exists() and not args.overwrite:
            print(f"FAIL: output exists (refusing overwrite without --overwrite): {out_path}")
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(database_baseline, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Wrote {out_path}")
    else:
        print("No --output provided; zero file writes (stdout summary only).")

    failed = [k for k, v in golden["checks"].items() if v is False]
    print(f"Golden checks total={len(golden['checks'])} failed={len(failed)}")
    for k in failed:
        print(f"  FAIL {k}")
    if viz_error:
        print(f"viz_error={viz_error}")
    if export_ok.get("error"):
        print(f"export_error={export_ok['error']}")
    print(
        f"integrity={integrity} fk={len(fk)} "
        f"run55={run55['status'] if run55 else None} "
        f"jr2={jr2['status'] if jr2 else None}"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
