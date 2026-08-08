from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="STORYLENS_",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/storylens.db"
    data_dir: str = ""
    log_dir: str = ""
    uploads_dir: str = ""
    exports_dir: str = ""
    config_dir: str = ""
    default_model_provider: str = "none"

    local_llama_base_url: str = "http://127.0.0.1:8080/v1"
    local_llama_api_key: str = "local"
    local_llama_model: str = "qwen-local"
    local_llama_timeout_seconds: int = 300
    local_llama_max_context_tokens: int = 4096
    scene_window_max_chars: int = 12000
    scene_window_overlap_paragraphs: int = 4
    scene_boundary_min_confidence: float = 0.65
    scene_boundary_min_vote_ratio: float = 0.5
    model_max_attempts: int = 3
    prompt_root: str = "packages/prompts"
    llama_server_path: str = ""
    local_model_path: str = ""
    local_llama_context_size: int = 4096
    local_llama_gpu_layers: int = 16
    local_llama_port: int = 8080
    local_llama_host: str = "127.0.0.1"
    local_llama_profile: str = "safe"
    local_llama_parallel: int = 1
    local_llama_batch_size: int = 128
    local_llama_ubatch_size: int = 64
    local_llama_max_output_tokens: int = 128
    local_llama_cooldown_seconds: int = 90
    local_llama_monitor_interval_seconds: int = 2
    local_llama_max_gpu_temp_c: int = 80
    local_llama_max_vram_mb: int = 14336
    local_llama_max_single_request_seconds: int = 300

    aliyun_enabled: bool = False
    aliyun_api_key: str = ""
    aliyun_workspace_id: str = ""
    aliyun_base_url: str = ""
    aliyun_plus_model: str = "qwen3.7-plus"
    aliyun_max_model: str = "qwen3.7-max"
    aliyun_flash_model: str = "qwen3.6-flash"
    aliyun_timeout_seconds: int = 300
    aliyun_max_retries: int = 3
    # DEFECT-CANARY-009: cloud transport resilience (total attempts incl. initial)
    aliyun_transport_max_attempts: int = 3
    aliyun_transport_retry_delay_1_min: float = 2.0
    aliyun_transport_retry_delay_1_max: float = 4.0
    aliyun_transport_retry_delay_2_min: float = 8.0
    aliyun_transport_retry_delay_2_max: float = 12.0
    # Canary batch inter-run cooldown after cloud journey stages (seconds)
    canary_inter_run_cooldown_seconds: float = 8.0
    # DEFECT-CANARY-014: Scene Analysis provider recovery (circuit breaker)
    scene_analysis_recovery_max_cycles: int = 3
    scene_analysis_recovery_max_duration_seconds: float = 1800.0
    scene_analysis_recovery_cooldown_seconds: float = 15.0
    scene_analysis_recovery_max_cost: float | None = None
    aliyun_structured_output_mode: str = "json_object"
    aliyun_enable_thinking: bool = False

    # DeepSeek (OpenAI-compatible) — independent from Aliyun settings/keyring.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: int = 300
    deepseek_max_retries: int = 3
    deepseek_structured_output_mode: str = "json_object"

    cloud_raw_logging: bool = False
    cloud_output_connection_test: int = 64
    cloud_output_minimal_json_test: int = 128
    cloud_output_scene_boundary: int = 768
    cloud_output_scene_analysis: int = 1600
    cloud_output_full_run_boundary: int = 768
    cloud_output_full_run_scene_analysis: int = 1600
    cloud_output_json_schema_repair: int = 1200
    cloud_output_business_repair: int = 1600
    # DEFECT-016: scene/schema_repair must fit max-legal Profile + safety margin;
    # stay under typical cloud hard cap (4000). Compaction uses evidence_repair.
    cloud_output_reader_journey_scene: int = 3500
    cloud_output_reader_journey_chapter: int = 3000
    cloud_output_reader_journey_json_repair: int = 1200
    cloud_output_reader_journey_schema_repair: int = 3500
    cloud_output_reader_journey_evidence_repair: int = 1600
    cloud_output_reader_journey_business_repair: int = 3500
    reader_journey_batch_size: int = 2
    reader_journey_formula_path: str = "config/reader_journey_formulas.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
