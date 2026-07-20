from pathlib import Path

REQUIRED = [
    "README.md",
    "AGENTS.md",
    "CODEX_START_PROMPT.md",
    ".env.example",
    "pyproject.toml",
    "apps/api/app/main.py",
    "apps/api/app/db/models.py",
    "apps/api/app/services/book_service.py",
    "apps/api/app/services/extractors.py",
    "apps/api/app/domain/ingestion.py",
    "apps/api/app/api/v1/router.py",
    "apps/api/app/model_gateway/base.py",
    "apps/api/app/model_gateway/gateway.py",
    "apps/api/app/model_gateway/registry.py",
    "apps/api/app/services/scene_pipeline.py",
    "apps/api/app/services/structured_output.py",
    "packages/prompts/scene_boundary/v1/system.md",
    "packages/prompts/scene_boundary/v1/user.md",
    "packages/prompts/scene_boundary/v1/repair.md",
    "packages/prompts/scene_analysis/v1/system.md",
    "packages/prompts/scene_analysis/v1/user.md",
    "packages/prompts/scene_analysis/v1/repair.md",
    "scripts/smoke_local_llama.py",
    "scripts/find_local_models.ps1",
    "scripts/install_local_model.ps1",
    "scripts/start_profile_model.ps1",
    "scripts/probe_structured_output.py",
    "scripts/calibrate_local_model.py",
    "scripts/start_local_model.ps1",
    "scripts/stop_local_model.ps1",
    "scripts/status_local_model.ps1",
    "scripts/monitor_local_model.ps1",
    "scripts/inspect_last_shutdown.ps1",
    "scripts/check_env.py",
    "scripts/package_project.ps1",
    "docs/10_local_model_calibration.md",
    "docs/11_local_model_selection.md",
    "docs/12_aliyun_qwen_provider.md",
    "scripts/probe_aliyun_qwen.py",
    "config/cloud_pricing.example.json",
    "apps/desktop/package.json",
    "apps/desktop/src/app/App.tsx",
    "apps/desktop/src-tauri/tauri.conf.json",
    "scripts/start_backend.ps1",
    "scripts/start_desktop_dev.ps1",
    "scripts/start_storylens_dev.ps1",
    "scripts/stop_storylens_dev.ps1",
    "scripts/build_desktop.ps1",
    "scripts/build_sidecar.ps1",
    "scripts/build_windows_release.ps1",
    "scripts/check_release_artifacts.ps1",
    "scripts/set_version.ps1",
    "scripts/smoke_windows_release.ps1",
    "scripts/stop_owned_process_tree.ps1",
    ".github/workflows/windows-release.yml",
    "docs/windows-desktop-release-plan.md",
    "docs/windows-desktop-updater-keys.md",
    "docs/00_project_overview.md",
    "docs/08_codex_workflow.md",
    "docs/21_phase_1c_assisted_boundary_review.md",
    "docs/22_cursor_project_handoff.md",
    "docs/23_phase_1ca4_staged_budget.md",
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [item for item in REQUIRED if not (root / item).exists()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")
    forbidden_models = list(root.rglob("*.gguf"))
    if forbidden_models:
        raise SystemExit("Model files must not be stored in the project.")
    required_directories = [root / "data"]
    for directory in required_directories:
        directory.mkdir(parents=True, exist_ok=True)
    print("Project scaffold check passed.")


if __name__ == "__main__":
    main()
