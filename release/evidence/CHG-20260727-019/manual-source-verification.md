# CHG-20260727-019 Manual Source Verification

**Status:** verified  
**Incident:** INC-20260727-001  
**Date:** 2026-07-27  

## Acceptance evidence

| Criterion | Result |
|-----------|--------|
| 故障快照零费用恢复脚本 PASS | PASS (`release/evidence/CHG-20260727-019/verification-result.txt`) |
| Journey 孤儿任务 → JOURNEY_INTERRUPTED | PASS (snapshot Journey #1 → failed / JOURNEY_INTERRUPTED / retryable) |
| Sidecar 启动不自动调用 Provider | PASS (recovery auto-enqueue = NO; REAL PROVIDER CALLS = 0 in verify script) |
| 用户主动恢复后进入 scene_profiles_running | PASS (user-confirmed; resume contract unit-tested) |
| 任务中心「阅读旅程 0/7 + 查看进度」 | PASS (Vitest composite lifecycle + user-confirmed) |
| 新增 2 条 model_invocations 来自用户主动启动 | PASS (not from auto-recovery; documented by acceptor) |

## Non-goals / still blocked

- CHG-20260727-018 stable 1.1.0 acceptance remains BLOCKED pending RC8 install acceptance.
- This verification does not Push / Tag / Release.

## Artifacts

- `verification-result.txt` — automated zero-cost gate
- `verify-reader-journey-recovery.ps1` — reproducible script
- Primary fix commit: `26abc3e9339f2acaa16afd25c184479d1472cb46`
