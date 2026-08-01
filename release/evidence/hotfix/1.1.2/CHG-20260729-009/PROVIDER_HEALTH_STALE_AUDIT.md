# PROVIDER_HEALTH_STALE_AUDIT — CHG-20260729-009 / INC-20260729-004

## Answers

1. **Settings “验证成功” source**  
   `application_settings.ai_service_validation_snapshot` via `ai_validation_snapshot.py` (`validation_status=success`, `validated_at` UTC ISO).

2. **Analysis startup health source**  
   `evaluate_manual_boundary_candidate` → `_runtime_health_from_invocations` over `model_invocations` (24h TTL), then `analysis_preflight` hard-fails on `health_state == "stale"` with HTTP 409 `PROVIDER_HEALTH_STALE`.

3. **Same Provider Health Service?**  
   **No (before fix).** Settings UI uses validation snapshot; analysis preflight used invocation cache. Execution plan partially overrode snapshot for `can_start`, but preflight did not.

4. **Same database?**  
   Yes — formal AppData SQLite (`storylens.db`). No evidence of split DB for this incident.

5–6. **provider_id / model_id**  
   Both sides use `aliyun_qwen_plus` / `qwen3.7-plus` (snapshot + provider_configurations.plus_model).

7–8. **均衡模式 resolved model**  
   Balanced resolves to configured `plus_model` = `qwen3.7-plus`. Not a qwen-plus silent switch in this incident.

9–10. **API Key fingerprint / endpoint**  
   Snapshot stores credential + configuration fingerprints for dashscope host. Preflight did not consult them for stale override.

11–13. **Timezones**  
   Snapshot `validated_at` is UTC-aware (`…+00:00`). Invocation `created_at` is naive UTC wall clock, then `replace(tzinfo=UTC)`. Not a UTC-vs-local compare bug for the false positive; age of latest invocation was genuinely >24h.

14. **TTL**  
   `HEALTH_TTL_SECONDS = 24 * 60 * 60`.

15. **Why stale within one minute?**  
   Settings wrote a **fresh snapshot** at 11:28Z, but did **not** create a `connection_test` ModelInvocation (0 rows). Preflight used latest invocation from **2026-07-28 06:20:55** (>24h) → `stale`. Snapshot override only covered `unhealthy`+`cached_failure`, **not** `stale`.

16–17. **Cache / ETag**  
   Snapshot updated; invocation-based health cache not invalidated; preflight ignored snapshot for stale.

18–21. **Multi-sidecar / ports / restart**  
   Process list captured; no proof of dual DB. Root cause does not require multi-instance. Snapshot persists across API restart; invocation-stale pathology also persists until fix.

22. **request_id `8eeb82b7…` branch**  
   `analysis_preflight` → `evaluation["health_state"] == "stale"` → HTTP 409 `PROVIDER_HEALTH_STALE`.

## Root cause classification

- **A. MULTIPLE_HEALTH_FACT_SOURCES** (primary)
- **F. HEALTH_CACHE_NOT_INVALIDATED** (snapshot success did not refresh preflight fact)
- **J. HEALTH_RECORD_NOT_PERSISTED** (no `connection_test` invocation for the Settings probe)

Not primary: C/D/E/H/I for this incident.

## Fix

Unify: matching successful Settings validation snapshot (UTC `validated_at` within TTL) becomes canonical healthy fact for analysis preflight, overriding stale/unhealthy invocation cache. Connection-test success also records the same snapshot. Differentiated error codes for mismatch cases.
