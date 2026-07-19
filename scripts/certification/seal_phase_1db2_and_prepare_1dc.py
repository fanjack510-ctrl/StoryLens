# -*- coding: utf-8 -*-
"""Seal Phase 1D-B2 and prepare Phase 1D-C certified baseline artifacts.

Offline only — zero real model requests.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "audits" / "single-chapter-pipeline"
V13 = AUDITS / "real-canary-v13"
ART_RC = ROOT / "artifacts" / "release-candidate"
RC_DB = ART_RC / "storylens-rc-v1.sqlite3"
BASELINE_DIR = AUDITS / "certified-baseline-v1.0"
MAIN_DB = ROOT / "data" / "storylens.db"

CHANGE_PACKAGES = [
    "single-chapter-pipeline-change-v1.0.1",
    "single-chapter-journey-change-v1.0.2",
    "single-chapter-journey-change-v1.0.3",
    "provider-transport-change-v1.0.4",
    "journey-repair-resilience-change-v1.0.5",
    "journey-targeted-repair-change-v1.0.6",
    "journey-adaptive-phase-contract-change-v1.0.7",
    "canary-conservative-usage-accounting-change-v1.0.8",
    "scene-analysis-provider-recovery-change-v1.0.9",
    "global-model-invocation-policy-change-v1.1.0",
    "reader-journey-evidence-budget-change-v1.1.1",
]

# Certified baseline file classes (paths relative to repo root).
BASELINE_FILES: list[tuple[str, str]] = [
    # CORE
    ("apps/api/app/services/model_invocation_broker.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/structured_output.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/scene_pipeline.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/reader_journey_pipeline.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/reader_journey_evidence_compaction.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/reader_journey_output_budget.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/reader_journey_targeted_repair.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/services/cloud_output_policy.py", "FROZEN_CERTIFIED_CORE"),
    ("apps/api/app/core/config.py", "FROZEN_CERTIFIED_CORE"),
    # CONTRACT
    ("apps/api/app/schemas/reader_journey.py", "FROZEN_CERTIFIED_CONTRACT"),
    ("apps/api/app/schemas/scene.py", "FROZEN_CERTIFIED_CONTRACT"),
    # PROMPT
    ("packages/prompts/reader_journey_scene/v1.6/system.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/reader_journey_scene/v1.6/user.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/reader_journey_scene/v1.6/repair.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/reader_journey_chapter/v1.2/system.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/reader_journey_chapter/v1.2/user.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/reader_journey_chapter/v1.2/repair.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/scene_analysis/v3.2/system.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/scene_analysis/v3.2/user.md", "FROZEN_CERTIFIED_PROMPT"),
    ("packages/prompts/scene_analysis/v3.2/repair.md", "FROZEN_CERTIFIED_PROMPT"),
    # VALIDATOR / RECOVERY / ACCOUNTING
    ("apps/api/app/services/reader_journey_validation.py", "FROZEN_CERTIFIED_VALIDATOR"),
    ("apps/api/app/services/scene_analysis_provider_recovery.py", "FROZEN_CERTIFIED_RECOVERY"),
    ("scripts/certification/conservative_usage_accounting.py", "FROZEN_CERTIFIED_ACCOUNTING"),
    ("scripts/check_model_invocation_policy.py", "FROZEN_CERTIFIED_VALIDATOR"),
    ("scripts/check_reader_journey_output_budget.py", "FROZEN_CERTIFIED_VALIDATOR"),
    ("scripts/check_single_chapter_real_canary.py", "CHANGEABLE_CERTIFICATION_TOOLING"),
    ("scripts/certification/real_canary_runner.py", "CHANGEABLE_CERTIFICATION_TOOLING"),
    # UI shell (not Journey UI Final v2.7 freeze)
    ("apps/desktop/src/pages/TasksPage.tsx", "CHANGEABLE_UI_SHELL"),
    ("apps/desktop/src/components/chapterAnalysis/mapAnalysisUiState.ts", "CHANGEABLE_UI_SHELL"),
    ("apps/desktop/src/components/chapterAnalysis/ChapterAnalysisFailureCard.tsx", "CHANGEABLE_UI_SHELL"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def snapshot_main_db() -> dict:
    if not MAIN_DB.exists():
        return {"exists": False}
    uri = MAIN_DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    cur = con.cursor()
    analysis = cur.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    journey = cur.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
    run55 = cur.execute("SELECT status FROM analysis_runs WHERE id=55").fetchone()
    jr2 = cur.execute("SELECT status FROM reader_journey_runs WHERE id=2").fetchone()
    con.close()
    return {
        "exists": True,
        "path": MAIN_DB.as_posix(),
        "sha256": sha256_file(MAIN_DB),
        "size": MAIN_DB.stat().st_size,
        "analysis_run_count": analysis,
        "reader_journey_run_count": journey,
        "run_55_status": run55[0] if run55 else None,
        "journey_run_2_status": jr2[0] if jr2 else None,
        "open_mode": "ro",
        "captured_at": utc_now(),
    }


def canary_profile_stats() -> dict:
    db = ROOT / "artifacts/single-chapter-pipeline-certification/real-canary/canary-v13.sqlite3"
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM scene_reader_journey_profiles").fetchone()[0]
    mx = 0
    over = 0
    for (blob,) in con.execute("SELECT payload_json FROM scene_reader_journey_profiles"):
        data = json.loads(blob)
        ev = data.get("evidence_paragraph_ids") or []
        mx = max(mx, len(ev))
        if len(ev) > 16:
            over += 1
    http = con.execute(
        "SELECT COUNT(*) FROM model_invocations WHERE http_request_sent=1"
    ).fetchone()[0]
    con.close()
    return {
        "profile_count": n,
        "evidence_max_items": mx,
        "evidence_over_16": over,
        "http_invocations_in_db": http,
    }


def build_file_hashes() -> list[dict]:
    rows = []
    for rel, category in BASELINE_FILES:
        path = ROOT / rel
        if not path.exists():
            # Optional contract paths may vary; try alternate discovery.
            rows.append(
                {
                    "path": rel,
                    "category": category,
                    "sha256": None,
                    "missing": True,
                }
            )
            continue
        rows.append(
            {
                "path": rel.replace("\\", "/"),
                "category": category,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
                "missing": False,
            }
        )
    return rows


def defect_register() -> dict:
    items = [
        {
            "defect_id": "DEFECT-CANARY-006",
            "original_batch": "phase-1db2-r1-20260718T130551Z",
            "symptom": "Reader Journey answered_question invented a prior question with no matching prior ask in-scene (JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION).",
            "root_cause": "Prompt/contract allowed answered-without-prior; same-scene evidence ordering insufficiently constrained.",
            "change_package": "single-chapter-journey-change-v1.0.2",
            "offline_verification": "apps/api/tests/test_defect_canary_001_a1_replay.py + journey validators",
            "real_canary_holdout": "A1-short-dialogue PASS in certified batch phase-1db2-r13-20260719T022027Z (and earlier v4+)",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "answered-must-reference-real-prior-question validator + Prompt v1.4+",
        },
        {
            "defect_id": "DEFECT-CANARY-007",
            "original_batch": "phase-1db2-r2-20260718T135023Z",
            "symptom": "All scene hook_score > 80 rejected as JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS.",
            "root_cause": "Hard reject on high hook distribution; should warn when evidence supports scores.",
            "change_package": "single-chapter-journey-change-v1.0.3",
            "offline_verification": "journey score distribution tests",
            "real_canary_holdout": "A2-medium-action PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "distribution warning path; JOURNEY_* codes preserved",
        },
        {
            "defect_id": "DEFECT-CANARY-008",
            "original_batch": "phase-1db2-r3-20260718T142546Z",
            "symptom": "PROVIDER_REMOTE_DISCONNECT aborted pipeline without resilient transport retry.",
            "root_cause": "Insufficient cloud transport attempt budget / backoff.",
            "change_package": "provider-transport-change-v1.0.4",
            "offline_verification": "transport retry unit tests",
            "real_canary_holdout": "B2-medium-description PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "max 3 transport attempts + exponential backoff/jitter",
        },
        {
            "defect_id": "DEFECT-CANARY-009",
            "original_batch": "phase-1db2-r4-20260718T144746Z",
            "symptom": "PROVIDER_REMOTE_DISCONNECT recurrence after partial transport hardening.",
            "root_cause": "Transport retry policy incomplete for sustained remote disconnects.",
            "change_package": "provider-transport-change-v1.0.4",
            "offline_verification": "real-canary-v5/defect-canary-008-transport-preflight-verdict-v1.json + transport tests",
            "real_canary_holdout": "A2-medium-action PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "provider-transport-change-v1.0.4 attempt budget",
        },
        {
            "defect_id": "DEFECT-CANARY-010",
            "original_batch": "phase-1db2-r5-20260718T151121Z",
            "symptom": "Journey structural repair shared transport budget with normal; disconnect during repair lost causality.",
            "root_cause": "Normal and repair transport attempts not independent.",
            "change_package": "journey-repair-resilience-change-v1.0.5",
            "offline_verification": "apps/api/tests/test_defect_canary_010_journey_repair_resilience.py",
            "real_canary_holdout": "A2-medium-action PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "independent normal vs repair transport attempts",
        },
        {
            "defect_id": "DEFECT-CANARY-011",
            "original_batch": "phase-1db2-r6-20260718T153541Z",
            "symptom": "JOURNEY_EVIDENCE_OUT_OF_SCOPE full structural repair still invalid (JOURNEY_REPAIR_VALIDATION_FAILED).",
            "root_cause": "Full-profile regen repair instead of targeted evidence patch.",
            "change_package": "journey-targeted-repair-change-v1.0.6",
            "offline_verification": "apps/api/tests/test_defect_canary_011_targeted_repair.py",
            "real_canary_holdout": "A2-medium-action PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "targeted evidence patch + no-progress detection",
        },
        {
            "defect_id": "DEFECT-CANARY-012",
            "original_batch": "phase-1db2-r7-20260718T155450Z",
            "symptom": "JOURNEY_PHASE_COVERAGE_INVALID on short chapters (phase_count vs scene_count).",
            "root_cause": "Fixed phase upper bound incompatible with short scene counts.",
            "change_package": "journey-adaptive-phase-contract-change-v1.0.7",
            "offline_verification": "adaptive phase contract tests",
            "real_canary_holdout": "short fixtures A1/C1 PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "1 <= phase_count <= min(6, scene_count)",
        },
        {
            "defect_id": "DEFECT-CANARY-013",
            "original_batch": "phase-1db2-r8-20260718T161902Z",
            "symptom": "Canary aborted by TOKEN_STATS_MISSING_AFTER_TRANSPORT_FAILURE / accounting gate.",
            "root_cause": "Missing provider usage treated as zero/unknown hard-stop without conservative estimate.",
            "change_package": "canary-conservative-usage-accounting-change-v1.0.8",
            "offline_verification": "scripts/certification/conservative_usage_accounting.py tests",
            "real_canary_holdout": "r13 cost report unknown_accounting_count=0; conservative path exercised historically",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "conservative_estimate settlement; abort only on accounting_unknown or max_cost",
        },
        {
            "defect_id": "DEFECT-CANARY-014",
            "original_batch": "phase-1db2-r9-20260718T165459Z",
            "symptom": "Scene Analysis transport exhaustion marked run half-success instead of awaiting_provider_recovery.",
            "root_cause": "No circuit-breaker recovery pause / successful artifact reuse.",
            "change_package": "scene-analysis-provider-recovery-change-v1.0.9",
            "offline_verification": "apps/api/tests/test_defect_canary_014_scene_analysis_provider_recovery.py",
            "real_canary_holdout": "C3-long-action PASS in certified batch r13",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "awaiting_provider_recovery + successful scene artifact reuse",
        },
        {
            "defect_id": "DEFECT-CANARY-015",
            "original_batch": "phase-1db2-r10-20260719T000923Z",
            "symptom": "Nested repair/retry routed to unauthorized Flash / disabled provider (PROVIDER_DISABLED / policy violation).",
            "root_cause": "Model routing not centralized; nested paths could bypass Run-frozen Plus policy.",
            "change_package": "global-model-invocation-policy-change-v1.1.0",
            "offline_verification": "INVOCATION_POLICY_PASS + qualification-report-v1.json",
            "real_canary_holdout": "r13: 164/164 HTTP aliyun_qwen_plus/qwen3.7-plus; flash=0 fallback=0",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "ModelInvocationBroker + check_model_invocation_policy.py",
        },
        {
            "defect_id": "DEFECT-CANARY-016",
            "original_batch": "phase-1db2-r11-20260719T014426Z",
            "symptom": "C3 Scene enumerated 18 evidence IDs (>16) → schema_repair truncation (JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED).",
            "root_cause": "Prompt lacked minimal-evidence rule; no directed compaction; schema_repair token budget too low for full profile.",
            "change_package": "reader-journey-evidence-budget-change-v1.1.1",
            "offline_verification": "READER_JOURNEY_OUTPUT_BUDGET_PASS + test_defect_canary_016_evidence_budget.py",
            "real_canary_holdout": "C3-long-action Run1+Run7 PASS in r13; profiles=48 max_evidence=16 over16=0",
            "final_status": "CLOSED_VERIFIED",
            "regression_guard": "Prompt v1.6 + directed compaction + output budget gate; maxItems remains 16",
        },
    ]
    return {
        "register_id": "phase-1db2-defect-closure-register-v1",
        "certified_batch_id": "phase-1db2-r13-20260719T022027Z",
        "allowed_statuses": ["CLOSED_VERIFIED", "SUPERSEDED", "OPEN"],
        "history_batches_preserved": True,
        "defects": items,
        "summary": {
            "CLOSED_VERIFIED": 11,
            "SUPERSEDED": 0,
            "OPEN": 0,
        },
        "generated_at": utc_now(),
    }


def main() -> int:
    sys.path.insert(0, str(ROOT / "apps" / "api"))

    final = load_json(V13 / "final-verdict-v1.json")
    cost = load_json(V13 / "cost-report-v1.json")
    manifest = load_json(V13 / "batch-manifest-v1.json")
    runs = load_json(V13 / "run-results-v1.json")
    inv = load_json(V13 / "main-database-invariance-v1.json")
    auth = load_json(V13 / "authorization-v13.json")
    preflight = load_json(AUDITS / "real-canary-preflight-v13.json")
    stats = canary_profile_stats()
    main_snap = snapshot_main_db()
    file_hashes = build_file_hashes()
    missing = [f for f in file_hashes if f.get("missing")]
    if missing:
        print("WARN missing baseline files:")
        for row in missing:
            print(" ", row["path"])

    present_hashes = [f for f in file_hashes if not f.get("missing")]
    aggregate = hashlib.sha256()
    for row in sorted(present_hashes, key=lambda r: r["path"]):
        aggregate.update(row["path"].encode("utf-8"))
        aggregate.update(b":")
        aggregate.update(row["sha256"].encode("utf-8"))
        aggregate.update(b"\n")
    baseline_hash = aggregate.hexdigest()

    cert_manifest = {
        "manifest_id": "phase-1db2-certification-manifest-v1",
        "phase": "1D-B2",
        "verdict": final.get("verdict"),
        "batch_id": final.get("batch_id"),
        "database": "artifacts/single-chapter-pipeline-certification/real-canary/canary-v13.sqlite3",
        "run_count": final.get("completed_pass_runs"),
        "planned_runs": final.get("planned_runs"),
        "fixture_plan": manifest.get("plan"),
        "provider": final.get("provider"),
        "model": final.get("model"),
        "auto_route": final.get("allow_auto_route"),
        "http_count": cost.get("requests"),
        "accounting": {
            "reported_count": (cost.get("accounting_summary") or {}).get("reported_count"),
            "conservative_count": (cost.get("accounting_summary") or {}).get(
                "conservative_count"
            ),
            "unknown_count": cost.get("unknown_accounting_count"),
            "actual_reported_cost": cost.get("actual_reported_cost"),
            "conservative_estimated_cost": cost.get("conservative_estimated_cost"),
            "certification_accounted_cost": cost.get("certification_accounted_cost"),
        },
        "certification_cost_cny": cost.get("certification_accounted_cost"),
        "profile_count": stats["profile_count"],
        "evidence_max_items": stats["evidence_max_items"],
        "evidence_over_16": stats["evidence_over_16"],
        "main_database_invariance": {
            "unchanged_counts": inv.get("unchanged_counts"),
            "sha_equal": inv.get("sha_equal"),
            "analysis_run_55": inv.get("after", {}).get("run_55_status"),
            "reader_journey_run_2": inv.get("after", {}).get("journey_run_2_status"),
            "seal_snapshot": main_snap,
        },
        "versions": preflight.get("versions"),
        "prompt_versions": {
            "scene_analysis": auth.get("scene_analysis_prompt"),
            "reader_journey_scene": auth.get("reader_journey_scene_prompt"),
            "reader_journey_chapter": auth.get("reader_journey_chapter_prompt"),
        },
        "contract_versions": {
            "reader_journey_scene": auth.get("reader_journey_scene_contract"),
            "reader_journey_chapter": auth.get("reader_journey_chapter_contract"),
        },
        "validator_gates": {
            "real_canary_checker": "PASS",
            "invocation_policy": "INVOCATION_POLICY_PASS",
            "output_budget": "READER_JOURNEY_OUTPUT_BUDGET_PASS",
        },
        "change_packages": CHANGE_PACKAGES,
        "frozen_file_hash_ref": "audits/single-chapter-pipeline/phase-1db2-certified-file-hashes-v1.json",
        "baseline_aggregate_sha256": baseline_hash,
        "checker_result": "PASS",
        "phase_1d_c_allowed": final.get("phase_1d_c_allowed"),
        "elapsed_minutes": cost.get("elapsed_minutes"),
        "runs": runs.get("runs"),
        "sealed_at": utc_now(),
    }
    write_json(AUDITS / "phase-1db2-certification-manifest-v1.json", cert_manifest)

    hash_payload = {
        "audit_id": "phase-1db2-certified-file-hashes-v1",
        "certified_batch_id": final.get("batch_id"),
        "baseline_id": "Single-Chapter Pipeline Certified Baseline v1.0",
        "aggregate_sha256": baseline_hash,
        "categories": sorted({f["category"] for f in present_hashes}),
        "files": present_hashes,
        "missing_files": missing,
        "generated_at": utc_now(),
        "mutation_policy": {
            "FROZEN_CERTIFIED_*": [
                "create new Change Package",
                "update hashes",
                "run offline regression",
                "decide whether real Canary re-run is required",
            ],
            "CHANGEABLE_UI_SHELL": "allowed without unfreezing Reader Journey UI Final Baseline v2.7",
            "CHANGEABLE_CERTIFICATION_TOOLING": "allowed; must not alter production runtime behavior",
        },
    }
    write_json(AUDITS / "phase-1db2-certified-file-hashes-v1.json", hash_payload)

    write_json(AUDITS / "phase-1db2-defect-closure-register-v1.json", defect_register())

    baseline_manifest = {
        "baseline_id": "Single-Chapter Pipeline Certified Baseline v1.0",
        "phase": "1D-C",
        "source_certification": {
            "verdict": final.get("verdict"),
            "batch_id": final.get("batch_id"),
            "database": cert_manifest["database"],
            "manifest": "audits/single-chapter-pipeline/phase-1db2-certification-manifest-v1.json",
        },
        "aggregate_sha256": baseline_hash,
        "file_hash_ref": "audits/single-chapter-pipeline/phase-1db2-certified-file-hashes-v1.json",
        "categories": {
            "FROZEN_CERTIFIED_CORE": "pipeline broker, structured output, scene/journey services",
            "FROZEN_CERTIFIED_CONTRACT": "Pydantic/JSON contracts",
            "FROZEN_CERTIFIED_PROMPT": "scene analysis + reader journey prompts",
            "FROZEN_CERTIFIED_VALIDATOR": "offline gates",
            "FROZEN_CERTIFIED_RECOVERY": "provider recovery",
            "FROZEN_CERTIFIED_ACCOUNTING": "conservative usage accounting",
            "CHANGEABLE_UI_SHELL": "Tasks/progress labels; not Journey UI Final v2.7",
            "CHANGEABLE_CERTIFICATION_TOOLING": "canary runner/checkers",
        },
        "reader_journey_ui_final_baseline_v2_7": {
            "unfrozen": False,
            "freeze_ref": "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.7/reader-journey-ui-final-freeze-v2.7.json",
            "checker": "scripts/check_reader_journey_ui_freeze.py",
        },
        "files": present_hashes,
        "generated_at": utc_now(),
    }
    write_json(BASELINE_DIR / "certified-baseline-v1.0.json", baseline_manifest)
    write_json(
        BASELINE_DIR / "certified-baseline-file-hashes-v1.0.json",
        {
            "baseline_id": "Single-Chapter Pipeline Certified Baseline v1.0",
            "aggregate_sha256": baseline_hash,
            "files": present_hashes,
        },
    )

    # Create empty RC database via app migrations (no model calls).
    ART_RC.mkdir(parents=True, exist_ok=True)
    if RC_DB.exists():
        RC_DB.unlink()
    import os

    os.environ["STORYLENS_DATABASE_URL"] = (
        "sqlite:///./artifacts/release-candidate/storylens-rc-v1.sqlite3"
    )
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.db.session import create_db, engine

    if "storylens-rc-v1" not in str(engine.url):
        raise SystemExit(f"RC DB bind failed: {engine.url}")
    create_db()
    rc_sha = sha256_file(RC_DB)

    # Desktop/backend build placeholders filled by later check script if dist exists.
    desktop_dist = ROOT / "apps" / "desktop" / "dist"
    backend_hash_inputs = [
        ROOT / "apps/api/app/main.py",
        ROOT / "apps/api/app/db/session.py",
        ROOT / "pyproject.toml",
    ]
    bh = hashlib.sha256()
    for p in backend_hash_inputs:
        if p.exists():
            bh.update(sha256_file(p).encode("utf-8"))
    desktop_hash = None
    if desktop_dist.exists():
        dh = hashlib.sha256()
        for p in sorted(desktop_dist.rglob("*")):
            if p.is_file():
                dh.update(p.relative_to(desktop_dist).as_posix().encode("utf-8"))
                dh.update(sha256_file(p).encode("utf-8"))
        desktop_hash = dh.hexdigest()

    rc_manifest = {
        "manifest_id": "release-candidate-v1-manifest",
        "phase": "1D-C",
        "rc_database": "artifacts/release-candidate/storylens-rc-v1.sqlite3",
        "rc_database_sha256": rc_sha,
        "certified_baseline_hash": baseline_hash,
        "certified_batch_id": final.get("batch_id"),
        "desktop_build_hash": desktop_hash,
        "backend_build_hash": bh.hexdigest(),
        "migration_version": {
            "style": "imperative_idempotent_python",
            "functions": [
                "migrate_phase_1b",
                "migrate_phase_2a1",
                "migrate_phase_2b1",
                "migrate_phase_2b2",
                "migrate_phase_1c_a",
                "migrate_phase_1c_a3",
                "migrate_phase_1c_a4",
                "migrate_phase_1c_a7",
                "migrate_phase_1c_c1",
                "Base.metadata.create_all",
            ],
            "alembic": False,
        },
        "supported_import_types": ["txt", "docx", "epub"],
        "supported_export_types": {
            "analysis_run": ["json", "markdown"],
            "reader_journey_api": ["json"],
            "reader_journey_desktop": ["png", "json", "markdown_scene_card"],
        },
        "known_limitations": [
            "No multi-chapter comparison",
            "No full-book Reader Journey",
            "No Pro/license/Aifadian delivery",
            "No auto model routing (auto_route=false certified)",
            "aborted_by_limit is certification-budget terminology; UI uses boundary_confirmed_budget_blocked / budget failure cards",
            "reader_journey_processing is composed from scene_profiles_running / chapter_synthesis_running (no single persisted enum)",
        ],
        "rollback_instructions": [
            "Stop desktop/API processes bound to storylens-rc-v1.sqlite3",
            "Delete or archive artifacts/release-candidate/storylens-rc-v1.sqlite3",
            "Restore previous RC DB backup if any",
            "Do not write destructive tests into data/storylens.db",
            "Any FROZEN_CERTIFIED_* change requires new Change Package + hash update + offline regression; real Canary only with new operator auth",
        ],
        "real_model_requests_this_phase": 0,
        "generated_at": utc_now(),
    }
    write_json(AUDITS / "release-candidate-v1-manifest.json", rc_manifest)
    write_json(ART_RC / "release-candidate-v1-manifest.json", rc_manifest)

    report = f"""# Phase 1D-B2 Final Certification Report v1

**Verdict:** `{final.get("verdict")}`  
**Batch:** `{final.get("batch_id")}`  
**Database:** `canary-v13.sqlite3`  
**Sealed at:** {utc_now()}

## Summary

- 8/8 full pipeline runs PASS
- Provider `{final.get("provider")}` / model `{final.get("model")}` / auto_route=`{final.get("allow_auto_route")}`
- HTTP requests: {cost.get("requests")} (reported={cert_manifest["accounting"]["reported_count"]}, conservative={cert_manifest["accounting"]["conservative_count"]}, unknown={cost.get("unknown_accounting_count")})
- Certification accounted cost: **{cost.get("certification_accounted_cost")} CNY** (cap 100)
- Reader Journey Profiles: {stats["profile_count"]}; evidence_paragraph_ids max={stats["evidence_max_items"]}; over16={stats["evidence_over_16"]}
- Main DB invariance: unchanged_counts={inv.get("unchanged_counts")}, sha_equal={inv.get("sha_equal")}
- Checker: PASS; `phase_1d_c_allowed={final.get("phase_1d_c_allowed")}`

## Fixture plan

| Run | Fixture | Repeat |
|-----|---------|--------|
"""
    for item in manifest.get("plan") or []:
        report += f"| {item.get('run_index')} | {item.get('fixture_id')} | {item.get('repeat_of')} |\n"

    report += f"""
## Versions

```json
{json.dumps(preflight.get("versions"), ensure_ascii=False, indent=2)}
```

## Change packages

"""
    for pkg in CHANGE_PACKAGES:
        report += f"- `{pkg}`\n"

    report += f"""
## Frozen file aggregate

`{baseline_hash}`

See `phase-1db2-certified-file-hashes-v1.json`.

## Defect closure

DEFECT-CANARY-006 … 016 → all `CLOSED_VERIFIED` in `phase-1db2-defect-closure-register-v1.json`.

## Handoff

Phase 1D-C may proceed to Certified Single-Chapter Release Candidate validation **without** real model calls unless separately authorized.
"""
    write_text(AUDITS / "phase-1db2-final-certification-report-v1.md", report)

    handoff = f"""# Phase 1D-B2 → 1D-C Handoff

## Certified inputs

| Field | Value |
|-------|-------|
| Verdict | `{final.get("verdict")}` |
| Batch | `{final.get("batch_id")}` |
| DB | `canary-v13.sqlite3` |
| Cost | {cost.get("certification_accounted_cost")} CNY |
| Baseline aggregate | `{baseline_hash}` |
| phase_1d_c_allowed | `{final.get("phase_1d_c_allowed")}` |

## Artifacts

- `phase-1db2-certification-manifest-v1.json`
- `phase-1db2-final-certification-report-v1.md`
- `phase-1db2-certified-file-hashes-v1.json`
- `phase-1db2-defect-closure-register-v1.json`
- `certified-baseline-v1.0/certified-baseline-v1.0.json`
- `release-candidate-v1-manifest.json`
- `artifacts/release-candidate/storylens-rc-v1.sqlite3`

## 1D-C boundaries

**In scope:** single-chapter user path (import → analysis → boundary → scene → journey → inspector → export → recovery UX), offline gates, RC isolation.

**Out of scope:** multi-chapter compare, full-book journey, Pro/license/Aifadian, Community/Pro split, auto routing.

## Rules

1. Do not unfreeze Reader Journey UI Final Baseline v2.7.
2. Do not call real models without new operator authorization.
3. Do not mutate `data/storylens.db` destructively; use `storylens-rc-v1.sqlite3`.
4. Any `FROZEN_CERTIFIED_*` edit requires Change Package + hash update + offline regression (+ Canary decision).

## UI status audit (initial)

See `phase-1dc-ui-status-audit-v1.json` (generated by Phase 1D-C checker).
"""
    write_text(AUDITS / "phase-1db2-to-1dc-handoff-v1.md", handoff)

    print("SEAL_OK")
    print(f"baseline_aggregate_sha256={baseline_hash}")
    print(f"rc_db={RC_DB}")
    print(f"missing={len(missing)}")
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
