# FORENSIC_SNAPSHOT — INC-20260729-004

- Captured: 2026-07-29 (system local)
- Incident dir: `D:\StoryLensIncident\INC-20260729-004-provider-health-stale\`
- Formal AppData: read-only copy only (`FORMAL DATABASE WRITES: 0`)

## Runtime

- Desktop path: `%LOCALAPPDATA%\StoryLens\storylens-desktop.exe`
- Desktop version: 1.1.2-rc.1 (installed RC)
- Sidecar path: `%LOCALAPPDATA%\StoryLens\storylens-api.exe`
- Sidecar version: 1.1.2-rc.1 (hash matches RC build sidecar)
- API port: dynamic (installed sidecar; see processes.json)
- Database path: `%LOCALAPPDATA%\StoryLens\database\storylens.db`
- System timezone: see `timezone.txt` (China Standard Time / UTC+08 expected)
- Now at freeze: see `now.txt`

## Provider state (from DB copy, secrets redacted)

- Provider: `aliyun_qwen_plus`（阿里云百炼）
- Configured model (`plus_model`): `qwen3.7-plus`
- Validation snapshot status: `success`
- Verified at (UTC): `2026-07-29T11:28:31.833255+00:00`
- Local display equivalent: `2026-07-29 19:28`
- Endpoint host: `dashscope.aliyuncs.com`
- Credential fingerprint present: yes (hash only)
- connection_test ModelInvocation rows: **0**
- Latest ModelInvocation: id 82, `2026-07-28 06:20:55` (HTTP 200 OUTPUT_TRUNCATED) → age > 24h

## Failure

- Request ID: `8eeb82b7eaa54096`
- HTTP status: 409
- Error code: `PROVIDER_HEALTH_STALE`
- User symptom: Settings shows 验证成功 at 19:28; analysis start blocked within ~1 minute

## Installer identity (RC.1 retained)

- Path: `D:\Dstorylens-wt-hotfix-1.1.2-integration\dist\release\StoryLens_1.1.2-rc.1_x64-setup.exe`
- SHA-256: `2C9ED3B8E898118391B56F7A297F96B9CFB8A9951C1226C851C5B7C1AEF1F61F`
- Not overwritten this round
