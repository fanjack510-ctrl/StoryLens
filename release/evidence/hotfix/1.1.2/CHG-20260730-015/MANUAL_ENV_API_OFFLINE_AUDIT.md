# MANUAL_ENV_API_OFFLINE_AUDIT — CHG-20260730-015

Time (local)：2026-07-30 ~14:10+  
Worktree：`D:\Dstorylens-wt-hotfix-1.1.2-integration`  
Expected HEAD：`f4560b19bc57d771e8a1baf0862b8bf1084a6347`

## Symptom

人工打开 Success Fixture 后，前端页面仍可打开，但左下角显示「本地服务离线」，并提示「无法读取数据 / 无法连接本地分析服务」。

## 1. Original API PID 32568

| Check | Result |
|-------|--------|
| Process exists | **YES** — `python.exe` PID 32568, `HasExited=False` |
| Start time | 2026/7/30 14:02:47 |
| Command | `python -m uvicorn app.main:app --host 127.0.0.1 --port 18049` |
| Parent | PID 26028 (venv `python.exe` uvicorn launcher) |

**结论：原 API 进程未退出。**

## 2. Port 18049

| Check | Result |
|-------|--------|
| Listening | **YES** — `127.0.0.1:18049` State=`Listen` OwningProcess=`32568` |
| `GET /health` | **200** `{"status":"ok","service":"storylens-api","database":"ok",...}` |
| CORS with `Origin: http://127.0.0.1:1428` | **200**, `Access-Control-Allow-Origin: http://127.0.0.1:1428` |

## 3. API stdout / stderr（最后有效内容）

`%TEMP%\storylens-mg-chg015-rc4-failure\api.err.log`：

```
INFO:     Started server process [32568]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:18049 (Press CTRL+C to quit)
```

`api.log`：仅有健康与 analysis-runs 的 **200** 访问记录，**无 Traceback / ERROR / Migration / DB lock / Provider crash**。

## 4. 应用日志

`%TEMP%\storylens-mg-chg015-rc4-failure\logs\`：**空 / 无应用滚动日志文件**。

## 5. 未捕获异常

**未发现。** stderr 无 ASGI Exception / Worker / Migration 堆栈。

## 6. 与 Chapter 4 / Analysis Run 4 的关系

API 侧 Run 4 仍可读：

- status=`succeeded`
- effective=`awaiting_scene_boundary_confirmation`
- completed/total scenes on run = 2/2（AI 模型确认集）
- Draft revision id=5：**3 个场景**（人工验收位置未丢）

`GET /api/v1/chapters/4/scene-boundaries` 返回 `awaiting_confirmation=true`，draft scenes=3。

**无证据表明 Chapter 4 操作打崩了 API。**

## 7. 终端关闭 / 人工停止 / 会话退出

**否。** PID 32568 仍存活并监听。

## 8. 数据库锁 / 端口冲突 / Provider / Worker / Migration

| Item | Result |
|------|--------|
| Port conflict | 无（单监听者 32568） |
| DB lock crash | 无 |
| Provider crash | 无（本轮 stderr 无 Provider 异常） |
| Migration crash | 无 |
| On-disk DB | 仅 `storylens-mg-chg015.db`（+ wal/shm）；fixture 数据完整（5 runs） |

注：`/api/v1/runtime` 报告的 `database_path` 显示为 `...\database\storylens.db`（显示路径与 DATA_DIR 默认名），但磁盘上实际数据文件为 `storylens-mg-chg015.db`，且 API 能正确读出 Run 1–5 / Chapter 4 draft。**此为 runtime 路径展示与 URL 文件名不一致，不是本次离线主因。**

## 9. 前端 API 指向

Vite 转换后的 `apiClient.ts` 嵌入：

```text
VITE_API_BASE_URL: "http://127.0.0.1:18049 "
```

**注意尾随空格。**

校验：

- `http://127.0.0.1:18049/health` → **OK**
- `http://127.0.0.1:18049 /health`（带空格）→ **Invalid URI / 连接失败**

前端 `AppShell` 通过 `api("/health")` 判断「本地服务离线」。带尾随空格的 base URL 会使所有 API 请求失败，从而显示离线与「无法连接本地分析服务」，**即使 Sidecar 完全正常**。

FE PID 30944（vite `--port 1428`）仍在线；页面壳可打开，但后端探测失败。

## Root cause verdict

| Question | Answer |
|----------|--------|
| PRODUCT API CRASH | **NO** |
| API process exited | **NO** |
| Accidental terminal kill | **NO** |
| True offline cause | **Frontend `VITE_API_BASE_URL` trailing space → invalid API base → health fetch fails → UI shows 本地服务离线** |

## Recovery action (no reseed / no product code change)

1. Keep API PID **32568** (already healthy on 18049; same DB; **not restarted** because process never exited).
2. Restart Frontend on **1428** with **trimmed** `VITE_API_BASE_URL=http://127.0.0.1:18049` (no trailing space).
3. Post-recovery checks:
   - Embedded URL = `http://127.0.0.1:18049` (no trailing space)
   - FE PID = **196**
   - Chapter 4 draft still **3 scenes**, `awaiting_confirmation=true`
   - Runs 1–4 readable; Journey 1–2 unchanged
   - Fixtures **not** reseeded

## Fixtures preserved at audit time

| Fixture | Run | Journey | State |
|---------|-----|---------|-------|
| A Scene failure | 1 | — | failed_structural 0/3 |
| B Synthesis | 2 | 1 | journey failed JOURNEY_SYNTHESIS_FAILED |
| C Recoverable | 3 | 2 | scene_profiles_partial JOURNEY_INTERRUPTED |
| D Success manual | 4 | — | awaiting confirm; **draft 3 scenes** |
