# MANUAL_UI_ENV — CHG-20260729-006

## Isolation

| Item | Value |
|------|--------|
| DATABASE | `%TEMP%\storylens-mg-chg006-task-cancel\database\storylens-mg-chg006.db` |
| API | `http://127.0.0.1:18045` |
| FRONTEND | `http://127.0.0.1:1424` |
| TASK CENTER | `http://127.0.0.1:1424/tasks` |
| Fake Provider | ON |
| Real Provider | OFF |
| Formal AppData DB | NOT USED |

## Public base HEAD

`595545351972cacd010b149061f4f513d8a0bd71`

## Suggested start (PowerShell)

```powershell
$env:STORYLENS_DATABASE_URL = "sqlite:///$env:TEMP/storylens-mg-chg006-task-cancel/database/storylens-mg-chg006.db"
New-Item -ItemType Directory -Force -Path "$env:TEMP\storylens-mg-chg006-task-cancel\database" | Out-Null
# API on 18045 with Fake Provider; FE vite --port 1424 with API base 18045
```

## Manual steps

1. Open Task Center; see Fake 6-scene analyzing task (slow Fake delay).
2. Click **停止分析** → confirm dialog → **确认停止**.
3. Status → **正在停止** → after in-flight Fake call → **已停止**.
4. Detail: partial scenes + usage retained; reservation released.
5. Refresh page; still **已停止**.
6. Restart API; still **已停止**.
7. **重新分析** → new Task ID (do not revive cancelled run).

## Confirm copy (frozen)

确定停止本次分析吗？

停止后将不再处理剩余场景，也不会再发起新的模型请求。
已完成的分析结果和已产生的用量会保留。
已经发出的模型请求可能仍会完成并产生相应用量。

需要再次分析时，将创建一个新任务。
