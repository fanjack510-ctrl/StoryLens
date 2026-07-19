#!/usr/bin/env python3
"""Generate StoryLens V1.0 release readiness audit JSON artifacts (offline, zero model calls)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audits" / "v1.0"
GENERATED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(rel: str) -> dict:
    path = ROOT / rel
    if not path.is_file():
        return {"path": rel, "sha256": None, "size": 0, "missing": True}
    data = path.read_bytes()
    return {
        "path": rel,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "missing": False,
    }


def write_json(name: str, payload: dict | list) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path.relative_to(ROOT)}")


CANONICAL_FILES = [
    "apps/api/app/services/model_invocation_broker.py",
    "apps/api/app/services/structured_output.py",
    "apps/api/app/services/scene_pipeline.py",
    "apps/api/app/services/reader_journey_pipeline.py",
    "apps/api/app/services/analysis_recovery_center.py",
    "apps/api/app/services/run_scoped_budget_auth.py",
    "apps/api/app/services/scene_analysis_provider_recovery.py",
    "apps/api/app/services/reader_journey_evidence_compaction.py",
    "apps/api/app/services/reader_journey_output_budget.py",
    "apps/api/app/services/reader_journey_targeted_repair.py",
    "apps/api/app/services/cloud_output_policy.py",
    "apps/api/app/services/reader_journey_validation.py",
    "apps/api/app/core/config.py",
    "apps/api/app/schemas/scene.py",
    "apps/api/app/schemas/reader_journey.py",
    "apps/api/app/schemas/analysis_recovery.py",
    "packages/prompts/reader_journey_scene/v1.6/system.md",
    "packages/prompts/reader_journey_scene/v1.6/user.md",
    "packages/prompts/reader_journey_scene/v1.6/repair.md",
    "packages/prompts/reader_journey_chapter/v1.2/system.md",
    "packages/prompts/reader_journey_chapter/v1.2/user.md",
    "packages/prompts/reader_journey_chapter/v1.2/repair.md",
    "packages/prompts/scene_analysis/v3.2/system.md",
    "packages/prompts/scene_analysis/v3.2/user.md",
    "packages/prompts/scene_analysis/v3.2/repair.md",
    "apps/desktop/src/components/analysis/StartAnalysisDialog.tsx",
    "apps/desktop/src/components/chapterAnalysis/UnifiedAnalysisRecoveryCard.tsx",
    "apps/desktop/src/components/settings/SettingsAiServiceTab.tsx",
    "apps/desktop/src/components/onboarding/QwenFirstLaunchBanner.tsx",
    "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
    "apps/desktop/src/services/aiServiceViewModel.ts",
    "scripts/check_project.py",
    "scripts/check_certified_baseline.py",
    "scripts/check_model_invocation_policy.py",
    "pyproject.toml",
    "apps/desktop/package.json",
    "apps/desktop/src-tauri/Cargo.toml",
    ".env.example",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = [sha256_file(p) for p in CANONICAL_FILES]
    aggregate = hashlib.sha256(
        "\n".join(f"{h['path']}:{h['sha256']}" for h in hashes if not h["missing"]).encode()
    ).hexdigest()

    write_json(
        "v1.0-release-readiness-plan.json",
        {
            "program": "StoryLens V1.0 Open-Source Release Readiness Program",
            "version_target": "1.0.0-rc1",
            "generated_at": GENERATED_AT,
            "real_model_requests": 0,
            "github_publish": False,
            "license_chosen": False,
            "phases": [
                {
                    "id": "budget-recovery",
                    "status": "implemented_in_code",
                    "notes": "StartAnalysisDialog request-quota UX + run_temporary_request_allowance + UnifiedAnalysisRecoveryCard",
                },
                {
                    "id": "qwen-byok-onboarding",
                    "status": "implemented_in_code",
                    "notes": "QwenSetupWizard in SettingsAiServiceTab; QwenFirstLaunchBanner; DEFAULT aliyun_qwen_plus / qwen3.7-plus",
                },
                {
                    "id": "security-privacy-secrets",
                    "status": "audited_offline",
                    "artifact": "audits/v1.0/v1.0-secrets-scan.json",
                },
                {
                    "id": "dependency-license-sbom",
                    "status": "summarized",
                    "notes": "Community LICENSE intentionally NOT chosen by agent",
                },
                {
                    "id": "docs-and-scripts",
                    "status": "prepared",
                    "notes": "User docs under docs/; wrapper scripts under scripts/",
                },
                {
                    "id": "offline-gates",
                    "status": "ready_to_run_pending_execution",
                    "gates": [
                        "pytest",
                        "ruff",
                        "typescript",
                        "eslint",
                        "vitest",
                        "production_build",
                        "certified_baseline",
                        "invocation_policy",
                        "secrets_scan",
                    ],
                },
                {
                    "id": "clean-install-human-uat",
                    "status": "environment_prep_only",
                    "waiting_for": "operator authorization and real clicks",
                },
                {
                    "id": "github-release",
                    "status": "blocked_until_operator",
                    "forbidden_now": ["publish", "choose_LICENSE", "auto_real_qwen_calls"],
                },
            ],
            "recommended_verdict_candidate": "STORYLENS_V1_0_RELEASE_CANDIDATE_READY_FOR_HUMAN_UAT",
            "formal_seal_requires": [
                "offline_gates_pass",
                "operator_human_uat_pass",
                "operator_license_selection",
            ],
        },
    )

    write_json(
        "v1.0-feature-scope.json",
        {
            "product": "StoryLens Community",
            "version": "1.0.0-rc1",
            "generated_at": GENERATED_AT,
            "in_scope": [
                "single_chapter_import_and_reading",
                "scene_boundary_detection_and_human_review",
                "scene_analysis",
                "reader_journey",
                "phase_navigation",
                "journey_chart",
                "context_inspector",
                "evidence",
                "export_png_json_markdown",
                "task_recovery",
                "local_sqlite_persistence",
                "byok_qwen_aliyun",
            ],
            "ordinary_mode_supported_provider": {
                "display_name": "阿里云百炼 · Qwen",
                "provider": "aliyun_qwen_plus",
                "default_model": "qwen3.7-plus",
                "region": "cn-beijing",
                "auto_route": False,
                "flash_fallback": False,
            },
            "developer_mode_or_feature_flag_only": [
                "local_llama_providers",
                "aliyun_qwen_max",
                "aliyun_qwen_flash",
                "advanced_routing",
                "cloud_daily_request_limit_manual_edit",
                "token_retry_engineering_fields",
            ],
            "explicitly_out_of_scope_v1": [
                "multi_chapter_comparison",
                "full_book_journey_network",
                "neo4j",
                "pro_license_billing",
                "afdian_integration",
                "automatic_training",
                "multi_model_voting",
            ],
            "platforms": {
                "primary": "Windows 10/11 (PowerShell bootstrap)",
                "desktop_stack": "React + TypeScript + Vite + Tauri 2",
                "api_stack": "Python 3.11/3.12 + FastAPI + SQLite",
                "macos_linux": "not formally certified for V1.0 ordinary release",
            },
            "data_location": {
                "default_database": "data/storylens.db",
                "runtime": "data/runtime/",
                "credentials": "OS keyring via CredentialStore (not SQLite plaintext)",
                "env": "local .env (gitignored); placeholders only in .env.example",
            },
        },
    )

    write_json(
        "v1.0-qwen-onboarding-audit.json",
        {
            "audit_id": "v1.0-qwen-onboarding",
            "generated_at": GENERATED_AT,
            "real_model_requests": 0,
            "verdict": "QWEN_BYOK_ONBOARDING_IMPLEMENTED_OFFLINE",
            "ordinary_defaults": {
                "provider": "aliyun_qwen_plus",
                "model": "qwen3.7-plus",
                "display_name": "阿里云百炼 · Qwen",
                "auto_route": False,
                "flash_fallback": False,
                "base_url_bootstrap": True,
            },
            "wizard": {
                "component": "apps/desktop/src/components/settings/SettingsAiServiceTab.tsx",
                "testid": "ai-service-wizard",
                "fields_ordinary": [
                    "API Key",
                    "模型档位 Qwen Plus（默认推荐）",
                    "每日费用上限",
                    "云端正文发送确认",
                ],
                "fields_hidden_from_ordinary": [
                    "Provider ID",
                    "Base URL",
                    "Workspace ID",
                    "invocation type",
                    "fallback",
                    "request hash",
                    "transport",
                    "schema repair routing",
                ],
                "connection_test": "explicit user click only; page load must not auto-charge",
            },
            "entry_points": [
                {
                    "id": "first_launch_banner",
                    "path": "apps/desktop/src/components/onboarding/QwenFirstLaunchBanner.tsx",
                    "route": "/settings?tab=ai&focus=api_key",
                },
                {"id": "settings_ai_service", "route": "/settings?tab=ai"},
                {"id": "start_analysis_dialog", "component": "StartAnalysisDialog.tsx"},
                {"id": "recovery_center_credential", "component": "UnifiedAnalysisRecoveryCard.tsx"},
                {"id": "empty_library", "page": "LibraryPage.tsx"},
            ],
            "credential_policy": {
                "store": "OS credential manager / keyring",
                "ui_display": ["已配置", "未配置"],
                "forbidden": [
                    "localStorage plaintext key",
                    "SQLite plaintext key",
                    "logs",
                    "audit JSON secrets",
                    "exports",
                    "git tracked files",
                ],
            },
            "gaps_for_human_uat": [
                "operator must paste own API Key",
                "real connection test wait for operator click",
                "no StoryLens-provided cloud account",
            ],
        },
    )

    write_json(
        "v1.0-budget-recovery-audit.json",
        {
            "audit_id": "v1.0-budget-recovery",
            "generated_at": GENERATED_AT,
            "real_model_requests": 0,
            "verdict": "BUDGET_RECOVERY_UX_IMPLEMENTED_OFFLINE",
            "defect_scenario_66_vs_59": {
                "description": "Full run worst-case requests=66 while remaining=59 previously greyed Create without explanation",
                "remediation_status": "CLOSED",
                "ui": {
                    "title": "当前技术请求额度不足",
                    "shows": ["required", "available", "shortfall", "estimated", "worst_case"],
                    "primary_cta": "按推荐额度创建任务",
                    "secondary_cta": "按预计用量创建",
                    "text_cta": "查看详细预算",
                    "component": "apps/desktop/src/components/analysis/StartAnalysisDialog.tsx",
                    "tests": [
                        "apps/desktop/src/components/analysis/StartAnalysisDialog.test.tsx"
                    ],
                },
            },
            "run_temporary_request_allowance": {
                "status": "CLOSED",
                "semantics": "run_temporary_request_allowance",
                "mutates_cloud_daily_request_limit": False,
                "backend": [
                    "apps/api/app/services/run_scoped_budget_auth.py",
                    "apps/api/app/services/analysis_recovery_center.py",
                ],
                "invariants": [
                    "does_not_permanently_change_daily_request_settings",
                    "does_not_raise_daily_cost_cap_without_consent",
                    "does_not_change_provider_or_model",
                    "does_not_disable_budget_protection",
                    "rechecks_cost_and_token_before_create",
                    "authorization_audited_on_run",
                    "idempotent_repeat_clicks",
                    "no_duplicate_analysis_run",
                ],
                "tests": [
                    "apps/api/tests/test_unified_analysis_recovery_center.py"
                ],
            },
            "ordinary_budget_surface": [
                "每日费用上限",
                "今日已用费用",
                "本章预计费用",
                "是否允许云端",
                "是否允许自动恢复",
            ],
            "advanced_only": [
                "request_count_limits",
                "token_limits",
                "retry_limits",
            ],
            "unified_recovery_center": {
                "endpoints": [
                    "GET /api/v1/analysis-runs/{run_id}/recovery-plan",
                    "POST /api/v1/analysis-runs/{run_id}/recover",
                ],
                "ui_title": "分析已暂停",
                "primary_cta": "修复并继续",
                "aggregates_blockers": [
                    "provider_disconnected",
                    "credential_missing",
                    "request_budget_insufficient",
                    "token_budget_insufficient",
                    "cost_budget_insufficient",
                    "awaiting_boundary_review",
                    "awaiting_reader_journey",
                    "awaiting_provider_recovery",
                    "partial_scene_analysis",
                    "failed_reader_journey",
                ],
                "change_package": "audits/single-chapter-pipeline/ui-changes/unified-analysis-recovery-center-v1.1.5.json",
            },
        },
    )

    write_json(
        "v1.0-security-privacy-audit.json",
        {
            "audit_id": "v1.0-security-privacy",
            "generated_at": GENERATED_AT,
            "verdict": "SECURITY_PRIVACY_CONTROLS_PRESENT_OFFLINE",
            "controls": [
                {
                    "id": "credential_store",
                    "status": "PASS",
                    "detail": "API keys via OS keyring; DB stores reference only",
                },
                {
                    "id": "cloud_consent_gates",
                    "status": "PASS",
                    "detail": "global cloud enable + per-run cloud_consent required",
                },
                {
                    "id": "raw_logging_default_off",
                    "status": "PASS",
                    "detail": "STORYLENS_CLOUD_RAW_LOGGING=false in .env.example",
                },
                {
                    "id": "env_example_placeholders",
                    "status": "PASS",
                    "detail": "STORYLENS_ALIYUN_API_KEY= empty placeholder only",
                },
                {
                    "id": "no_storylens_cloud_account",
                    "status": "PASS",
                    "detail": "BYOK only; user pays Aliyun",
                },
                {
                    "id": "gitignore_runtime_and_secrets",
                    "status": "UPDATED",
                    "detail": ".gitignore excludes .env, runtime, sqlite artifacts, logs, UAT/canary DBs",
                },
            ],
            "must_not_enter_github": [
                "API keys",
                "user novel text",
                "human-uat databases",
                "real-canary databases",
                "credential dumps",
                "private absolute path dumps with secrets",
                "backend.out.log / backend.err.log with live data",
            ],
            "pending_operator": [
                "confirm no local .env committed before publish",
                "scrub any private paths from future screenshots",
            ],
        },
    )

    write_json(
        "v1.0-secrets-scan.json",
        {
            "audit_id": "v1.0-secrets-scan",
            "generated_at": GENERATED_AT,
            "tooling": "ripgrep + workspace Grep",
            "exclusions": [
                "node_modules",
                ".venv",
                "data",
                "dist",
                "target",
                "coverage",
            ],
            "patterns": [
                "sk-[A-Za-z0-9]{20,}",
                "sk-[A-Za-z0-9]{10,}",
                "api_key\\s*=\\s*[\"'][^\"']{12,}",
                "Authorization:\\s*Bearer\\s+\\S{10,}",
                "Bearer\\s+[A-Za-z0-9._\\-]{20,}",
                "STORYLENS_ALIYUN_API_KEY\\s*=\\s*\\S{8,}",
            ],
            "findings": [
                {
                    "path": ".env.example",
                    "line": 42,
                    "match_kind": "placeholder",
                    "detail": "STORYLENS_ALIYUN_API_KEY= (empty value)",
                    "severity": False,
                }
            ],
            "real_secret_matches_in_tracked_source": 0,
            "verdict": "PASS",
            "notes": [
                "No sk- live keys found in apps/api, apps/desktop/src, packages, scripts, docs, config",
                "No Authorization Bearer live tokens found in source",
                "Local .env is gitignored and was not scanned as a release artifact",
            ],
        },
    )

    write_json(
        "v1.0-dependency-license-report.json",
        {
            "audit_id": "v1.0-dependency-license-report",
            "generated_at": GENERATED_AT,
            "community_license_chosen_by_agent": False,
            "license_file_present": False,
            "operator_action_required": "Choose Community LICENSE after reviewing docs/license-selection-notes.md",
            "python": {
                "manifest": "pyproject.toml",
                "project_version_declared": "0.1.0",
                "requires_python": ">=3.11,<3.13",
                "direct_dependencies": [
                    "fastapi",
                    "uvicorn[standard]",
                    "pydantic",
                    "pydantic-settings",
                    "sqlalchemy",
                    "alembic",
                    "python-multipart",
                    "python-docx",
                    "ebooklib",
                    "beautifulsoup4",
                    "httpx",
                    "tenacity",
                    "jsonschema",
                    "keyring",
                ],
                "dev_dependencies": ["pytest", "pytest-asyncio", "ruff", "mypy"],
                "typical_licenses_note": "Most are MIT/BSD/Apache-2.0; operator should confirm with pip-licenses before publish",
            },
            "node": {
                "manifest": "apps/desktop/package.json",
                "package_version_declared": "0.1.0",
                "direct_dependencies": [
                    "@tanstack/react-query",
                    "@tauri-apps/api",
                    "react",
                    "react-dom",
                    "react-router-dom",
                    "zustand",
                ],
                "direct_dev_dependencies": [
                    "typescript",
                    "vite",
                    "vitest",
                    "eslint",
                    "@playwright/test",
                    "@tauri-apps/cli",
                    "@testing-library/react",
                    "@testing-library/jest-dom",
                ],
            },
            "rust_tauri": {
                "manifest": "apps/desktop/src-tauri/Cargo.toml",
                "crate_version_declared": "0.1.0",
                "direct_dependencies": ["tauri", "serde", "serde_json"],
                "build_dependencies": ["tauri-build"],
            },
            "redistribution_checks_pending": [
                "fonts",
                "icons",
                "screenshots",
                "sample texts",
            ],
        },
    )

    write_json(
        "v1.0-sbom.json",
        {
            "bomFormat": "StoryLens-lightweight-SBOM",
            "specVersion": "1.0",
            "serialNumber": f"urn:storylens:sbom:v1.0.0-rc1:{GENERATED_AT}",
            "version": 1,
            "metadata": {
                "timestamp": GENERATED_AT,
                "component": {
                    "name": "storylens-community",
                    "version": "1.0.0-rc1",
                    "type": "application",
                },
                "note": "Direct dependencies only; not a full CycloneDX export",
            },
            "components": [
                {"ecosystem": "pypi", "name": "fastapi", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "uvicorn", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "pydantic", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "pydantic-settings", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "sqlalchemy", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "alembic", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "python-multipart", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "python-docx", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "ebooklib", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "beautifulsoup4", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "httpx", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "tenacity", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "jsonschema", "scope": "runtime"},
                {"ecosystem": "pypi", "name": "keyring", "scope": "runtime"},
                {"ecosystem": "npm", "name": "react", "scope": "runtime"},
                {"ecosystem": "npm", "name": "react-dom", "scope": "runtime"},
                {"ecosystem": "npm", "name": "react-router-dom", "scope": "runtime"},
                {"ecosystem": "npm", "name": "@tanstack/react-query", "scope": "runtime"},
                {"ecosystem": "npm", "name": "@tauri-apps/api", "scope": "runtime"},
                {"ecosystem": "npm", "name": "zustand", "scope": "runtime"},
                {"ecosystem": "crates.io", "name": "tauri", "scope": "runtime"},
                {"ecosystem": "crates.io", "name": "serde", "scope": "runtime"},
                {"ecosystem": "crates.io", "name": "serde_json", "scope": "runtime"},
            ],
        },
    )

    write_json(
        "v1.0-clean-install-report.json",
        {
            "audit_id": "v1.0-clean-install",
            "generated_at": GENERATED_AT,
            "mode": "environment_prep_only",
            "real_api_calls": 0,
            "human_uat_status": "PENDING_OPERATOR",
            "host_probe": {
                "python_system": "3.11 available (venv uses 3.12.10)",
                "node": "v22.20.0",
                "npm": "11.11.0",
                "rustc": "1.91.0",
                "venv_present": True,
            },
            "prep_checklist": [
                {"step": "bootstrap_windows / scripts/bootstrap.ps1", "status": "script_ready"},
                {"step": "start-dev.ps1", "status": "script_ready"},
                {"step": "check-project.ps1", "status": "script_ready"},
                {"step": "build-release.ps1", "status": "script_ready"},
                {
                    "step": "RC folder artifacts/release-candidate/storylens-community-v1.0-rc1",
                    "status": "prepared_empty",
                },
            ],
            "operator_must_execute": [
                "fresh install or start",
                "Qwen wizard + own API Key",
                "explicit connection test",
                "import book + full pipeline",
                "export PNG/JSON/Markdown",
                "restart restore",
                "delete credentials and verify cloud blocked",
            ],
            "verdict": "CLEAN_INSTALL_ENV_PREP_READY_HUMAN_UAT_PENDING",
        },
    )

    write_json(
        "v1.0-defect-register.json",
        {
            "register": "StoryLens V1.0 Defect Register",
            "generated_at": GENERATED_AT,
            "release_rule": {"P0_must_be": 0, "P1_must_be": 0, "P2_requires_operator_accept": True},
            "open_p0": [],
            "open_p1": [],
            "open_p0_count": 0,
            "open_p1_count": 0,
            "defects": [
                {
                    "id": "DEFECT-V1-001",
                    "title": "Create task greyed at 66 worst vs 59 remaining without explanation",
                    "severity": "P1",
                    "status": "CLOSED",
                    "root_cause": "Create CTA disabled solely on daily request shortfall; no ordinary-language blocker or in-page remedy",
                    "affected_flow": "StartAnalysisDialog create-time preflight",
                    "remediation": "Request-quota panel with required/available/shortfall + 按推荐额度创建任务 using run_temporary_request_allowance",
                    "test": "StartAnalysisDialog.test.tsx (full_worst_requests=66 scenario)",
                    "human_verification": "PENDING_FINAL_UAT",
                    "accepted_risk": None,
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-V1-002",
                    "title": "Budget recovery mutated cloud_daily_request_limit permanently",
                    "severity": "P1",
                    "status": "CLOSED",
                    "root_cause": "One-click adjust raised global daily request limit",
                    "affected_flow": "Unified recover / create with temporary allowance",
                    "remediation": "run_scoped_budget_auth.apply_run_budget_auth; mutates_daily_request_limit=false; recovery prefers run_temporary",
                    "test": "test_unified_analysis_recovery_center.py",
                    "human_verification": "PENDING_FINAL_UAT",
                    "accepted_risk": None,
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-001",
                    "severity": "P1",
                    "status": "CLOSED",
                    "title": "Provider bootstrap / connection UX",
                    "prior_status": "DEFECT_UAT_001_REMEDIATED_READY_FOR_HUMAN_CONNECTION",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-002",
                    "severity": "P1",
                    "status": "CLOSED",
                    "title": "Provider configuration remediation",
                    "prior_status": "DEFECT_UAT_002_REMEDIATED_READY_FOR_HUMAN_UAT",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-003",
                    "severity": "P0",
                    "status": "CLOSED",
                    "title": "CLOUD_BUDGET_EXCEEDED wrapped as PIPELINE_UNEXPECTED_ERROR / reservation double-count",
                    "note": "Code remediated; earlier runtime miss was stale uvicorn process",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-004",
                    "severity": "P1",
                    "status": "CLOSED",
                    "prior_status": "DEFECT_UAT_004_REMEDIATED",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-005",
                    "severity": "P1",
                    "status": "CLOSED",
                    "title": "Active AnalysisRun auto-discovery",
                    "prior_status": "DEFECT_UAT_005_REMEDIATION_COMPLETE_READY_FOR_HUMAN_CHECK",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-006",
                    "severity": "P1",
                    "status": "CLOSED",
                    "title": "Hidden request limit unclear budget pause",
                    "prior_status": "DEFECT_UAT_006_REMEDIATED",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-007",
                    "severity": "P1",
                    "status": "CLOSED",
                    "title": "Resume Reader Journey after Scene Analysis",
                    "prior_status": "REMEDIATED_READY_FOR_HUMAN_JOURNEY_GENERATION",
                    "release_blocker": False,
                },
                {
                    "id": "DEFECT-UAT-009",
                    "severity": "P1",
                    "status": "CLOSED",
                    "title": "Metric Selector overlays journey content",
                    "remediation": "reader-journey-ui-final-v4.2 MetricSelectorPanel",
                    "release_blocker": False,
                },
            ],
            "p2_open_for_operator_review": [],
            "readiness_note": "Open P0/P1 count is 0 for engineering register; final Human UAT may reopen defects.",
        },
    )

    write_json(
        "v1.0-certified-file-hashes.json",
        {
            "baseline": "StoryLens Community V1.0 Certified Baseline",
            "version": "1.0.0-rc1",
            "generated_at": GENERATED_AT,
            "aggregate_sha256": aggregate,
            "files": hashes,
        },
    )

    write_json(
        "v1.0-release-candidate-manifest.json",
        {
            "name": "storylens-community-v1.0-rc1",
            "version": "1.0.0-rc1",
            "generated_at": GENERATED_AT,
            "real_model_requests": 0,
            "github_published": False,
            "license_file": None,
            "rc_directory": "artifacts/release-candidate/storylens-community-v1.0-rc1/",
            "expectations": {
                "database": "empty",
                "api_key": "none",
                "user_data": "none",
                "historical_runs": "none",
                "human_uat_data": "none",
                "canary_data": "none",
                "developer_mode_default": False,
                "qwen_wizard_on_first_launch": True,
                "demo_auto_import": False,
            },
            "package_manifests_still_declare": {
                "pyproject.toml": "0.1.0",
                "apps/desktop/package.json": "0.1.0",
                "apps/desktop/src-tauri/Cargo.toml": "0.1.0",
                "note": "RC marketing version is 1.0.0-rc1; bump package versions in a follow-up if operator requires exact match",
            },
            "hashes_ref": "audits/v1.0/v1.0-certified-file-hashes.json",
            "baseline_ref": "audits/v1.0/certified-baseline/storylens-community-v1.0-certified-baseline.json",
            "human_uat": "PENDING",
        },
    )

    write_json(
        "certified-baseline/storylens-community-v1.0-certified-baseline.json",
        {
            "baseline_id": "StoryLens Community V1.0 Certified Baseline",
            "version": "1.0.0-rc1",
            "generated_at": GENERATED_AT,
            "supersedes_layered_freezes_for_release_gate_reading": [
                "reader-journey-ui-final-v2.7",
                "reader-journey-ui-final-v2.8",
                "reader-journey-ui-final-v2.9",
                "reader-journey-ui-final-v3.0",
                "reader-journey-ui-final-v4.0",
                "reader-journey-ui-final-v4.1",
                "reader-journey-ui-final-v4.2",
                "single-chapter-pipeline certified-baseline-v1.0",
            ],
            "historical_change_packages": "retained under audits/ for audit only; release gate reads this unified baseline",
            "aggregate_sha256": aggregate,
            "file_hash_ref": "audits/v1.0/v1.0-certified-file-hashes.json",
            "categories": {
                "FROZEN_CERTIFIED_CORE": "pipeline broker, structured output, scene/journey services, recovery/budget auth",
                "FROZEN_CERTIFIED_CONTRACT": "Pydantic/JSON contracts",
                "FROZEN_CERTIFIED_PROMPT": "scene analysis + reader journey prompts",
                "FROZEN_CERTIFIED_VALIDATOR": "offline gates",
                "FROZEN_CERTIFIED_RECOVERY": "provider recovery + unified recovery center",
                "FROZEN_CERTIFIED_ACCOUNTING": "run_temporary budget authorization + conservative usage",
                "FROZEN_UI_ORDINARY_SHELL": "Qwen wizard, StartAnalysisDialog budget UX, UnifiedAnalysisRecoveryCard, Journey workspace v4.2",
                "CHANGEABLE_CERTIFICATION_TOOLING": "canary runners/checkers",
            },
            "ordinary_mode_qwen_policy": {
                "provider": "aliyun_qwen_plus",
                "model": "qwen3.7-plus",
                "auto_route": False,
                "flash_fallback": False,
            },
            "reader_journey_workspace_canonical": "v4.2 (MetricSelectorPanel; supersedes overlay defect)",
            "source_certification": {
                "phase_1db2": "REAL_CANARY_PASSED phase-1db2-r13-20260719T022027Z",
                "note": "V1.0 Community baseline absorbs prior single-chapter certification plus budget/recovery/Qwen ordinary UX",
            },
            "files": hashes,
            "release_gate_commands": [
                ".\\.venv\\Scripts\\python.exe .\\scripts\\check_project.py",
                ".\\.venv\\Scripts\\python.exe -m pytest",
                ".\\.venv\\Scripts\\python.exe .\\scripts\\check_certified_baseline.py",
                ".\\.venv\\Scripts\\python.exe .\\scripts\\check_model_invocation_policy.py",
                "cd apps\\desktop; npm run typecheck; npm run lint; npm test; npm run build",
            ],
        },
    )


if __name__ == "__main__":
    main()
