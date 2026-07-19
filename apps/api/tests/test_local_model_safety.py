from pathlib import Path

from app.core.config import Settings
from app.services.gpu_safety import parse_nvidia_smi_line, safety_stop_reason


ROOT = Path(__file__).resolve().parents[3]


def test_safe_defaults_never_use_full_offload() -> None:
    settings = Settings(_env_file=None)
    assert settings.local_llama_profile == "safe"
    assert settings.local_llama_context_size == 4096
    assert settings.local_llama_gpu_layers == 16
    script = (ROOT / "scripts/start_local_model.ps1").read_text(encoding="utf-8")
    assert "layers=999" not in script and "-ngl',999" not in script
    assert "cannot exceed 16 GPU layers" in script


def test_gpu_metrics_and_thresholds() -> None:
    metrics = parse_nvidia_smi_line("79, 96, 13800, 72.5")
    assert metrics.power_w == 72.5
    assert safety_stop_reason(metrics, max_temperature_c=80, max_vram_mb=14336) is None
    assert (
        safety_stop_reason(
            parse_nvidia_smi_line("80, 1, 1000, N/A"),
            max_temperature_c=80,
            max_vram_mb=14336,
        )
        == "temperature_threshold"
    )
    assert (
        safety_stop_reason(
            parse_nvidia_smi_line("70, 1, 14336, 20"),
            max_temperature_c=80,
            max_vram_mb=14336,
        )
        == "vram_threshold"
    )


def test_monitor_and_smoke_are_explicit_and_pid_scoped() -> None:
    monitor = (ROOT / "scripts/monitor_local_model.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts/stop_local_model.ps1").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/smoke_local_llama.py").read_text(encoding="utf-8")
    assert "process.json" in monitor and "Stop-Process -Name" not in monitor
    assert "ExecutablePath" in stop and "process.json" in stop
    assert 'choices=("health", "minimal", "fixture", "pipeline")' in smoke
    assert "max_tokens=min(args.max_output_tokens, 32)" in smoke


def test_sqlite_integrity(testing_session) -> None:
    assert (
        testing_session.execute(__import__("sqlalchemy").text("PRAGMA integrity_check")).scalar()
        == "ok"
    )


def test_package_excludes_runtime_and_incidents() -> None:
    package = (ROOT / "scripts/package_project.ps1").read_text(encoding="utf-8")
    assert "'runtime'" in package
    assert "'.env.backup-*'" in package
