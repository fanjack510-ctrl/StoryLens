# PROVIDER_CONFIGURATION

DATE：2026-08-07  
CHANGE：CHG-20260807-053

PROVIDER：  
aliyun_qwen_plus（阿里云百炼 · Qwen）

MODEL：  
qwen3.7-plus

API KEY CONFIGURED：  
YES（Windows Keyring `StoryLens` / `aliyun_qwen_plus`）

PROVIDER ENABLED：  
YES（isolated L3 temp DB `ProviderConfiguration.enabled=true`）

CLOUD MASTER：  
YES（`application_settings.cloud_enabled=true` in temp DB）

ENDPOINT：  
configured_or_default（Aliyun OpenAI-compatible；未在报告中打印完整 URL/密钥）

NETWORK：  
YES，仅百炼正式 Provider

REAL PROVIDER SMOKE：  
PASS  
Evidence：`provider_smoke.txt`  
Meta（redacted）：http_status=200，input_tokens=25，output_tokens=5，latency_ms≈2280，parsed_status=ok

FREE REAL PATH FLAG：  
`STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED=true` 已设置

FREE CREATE PATH：  
**NOT OPEN** — `create_free_whole_book_analysis_v1` 在 flag 通过后仍硬抛  
`WHOLE_BOOK_CAPABILITY_DISABLED`（「真实 Provider 路径尚未在本版本开放」）

SOURCE：  
`apps/api/app/narrative_core/services/whole_book_free_product_v1_service.py`  
`apps/api/app/narrative_core/services/whole_book_fixture_pipeline_v1_service.py`（real flag 下拒绝 fixture pipeline）

AVAILABLE FREE TRANSPORTS：  
仅 `Fixture*`（Overview / WindowAnalysis / Structure / ChapterFunctions）  
无 Free Real / Bailian Transport 接四模块产品主链
