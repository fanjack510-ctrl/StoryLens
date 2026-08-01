# CONFIRM_START_JOURNEY_RACE_AUDIT — CHG-20260730-013 / INC-20260730-006

- Public base HEAD: `c568ab9a248e91dca5e14b666e4345dc30f80cd0` (hotfix/1.1.2 @ RC.3)
- Incident freeze: `D:\StoryLensIncident\INC-20260730-006-confirm-start-journey-race\FORENSIC_SNAPSHOT.md`
- Formal DB writes during investigation: **0**
- Real Provider calls during investigation: **0**

## Call chain (as implemented before fix)

1. UI: 「确认这 N 个场景并开始分析」→ `POST .../scene-boundaries/draft/{id}/confirm` (`start_journey=true`)
2. `confirm_scene_revision_and_start_journey_v1` — confirm revision + create/get journey run in DB session, commit
3. API returns with `journey_run_id` while status was historically `queued`
4. `BackgroundTasks.add_task(execute_reader_journey)` — **after** commit (not same atomic unit as DB)
5. Worker: `execute_reader_journey` → scene profiles → synthesis
6. Frontend polls workflow / journey; Continue resolves route via `effective_chapter_status` / composition

## Answers to required audit questions

| # | Question | Finding |
|---|---|---|
| 1 | Confirm 与 Start 是否同一事务？ | **部分是**：Revision confirm + Journey row 在同一服务方法/会话中提交；内存 enqueue **不在** DB 事务内。 |
| 2 | API 成功返回时 Run 是否已持久化？ | **是**（journey/analysis 行已 commit 后才返回）。 |
| 3 | Run 持久化后 Worker 是否一定可领取？ | **否**：依赖 BackgroundTasks / 进程存活；重启窗口内可能未 enqueue。 |
| 4 | DB 已提交但未 enqueue？ | **是**（设计缺口）：仅依赖 in-process `add_task`。 |
| 5 | Enqueue 但 Run 状态仍旧？ | 可能短暂停留在 starting/queued；修复后明确为 `starting` + startup intent。 |
| 6 | Worker 启动前空窗是否被判 interrupted？ | **是（根因）**：`recover_orphaned_reader_journeys(force_startup=True)` 把未领取的 queued 一律打断。 |
| 7 | 页面何时将 running 判为失联/中断？ | 后端写入 `JOURNEY_INTERRUPTED` 后前端展示中断；亦可被 stale `awaiting_scene_boundary_confirmation` 带偏路由。 |
| 8 | 是否缺少启动中明确状态？ | **是**；修复增加/复用 `starting` + `workflow_state=starting`。 |
| 9 | Continue 是否重新创建 Journey Run？ | 设计意图否；事故现场多次 Continue 后仍是同一 journey id=4 最终成功（幂等键存在，但中断/恢复抖动）。 |
| 10 | 多次 Continue 是否多个 Run？ | 事故副本：同 analysis_run 下 journey 仍为单一成功行；风险在错误中断 + 路由死路，非必然多 Run。 |
| 11 | Continue 是否错误路由到 scene-boundary-review？ | **是**：live journey 未优先于 awaiting confirmation marker。 |
| 12 | 已确认仍进「无需确认」页？ | **是**：确认后 draft 清空 + awaiting marker 残留 → 空白确认页 + 顶栏继续分析。 |
| 13 | 前端是否用旧 run 查询参数？ | 可能；composition 需偏向 current live journey。 |
| 14 | 最新 Run 与 URL Run 是否混读？ | 风险存在；修复侧优先 live journey / confirmed revision。 |
| 15 | ETag/轮询缓存旧 workflow_state？ | 次要；主因是后端误打断 + status 优先级。 |
| 16 | API/Worker 重启是否扩大竞态？ | **是**：boot `force_startup` 误打断未领取任务。 |
| 17 | `0/3` 与「生成失败」转换？ | starting/queued 被标 interrupted → UI 失败/中断文案，尽管 scene 尚未开始。 |
| 18 | 阶段/checkpoint 非原子？ | 事故 DB 可见 progress 不一致（如 2/1）；handoff 字段非完全原子。 |
| 19 | 未领取任务是否被当成可恢复中断？ | **是**（核心缺陷）。 |
| 20 | 多次 Continue 后为何成功？ | 最终某次 resume 在 Worker 已就绪时重入同一 journey，覆盖中断元数据并跑完。 |

## Root cause classification

**Primary: C. WORKER_STARTUP_WINDOW_MARKED_INTERRUPTED**

Contributing:

- **A/B**: Confirm+Start DB 提交与 BackgroundTasks enqueue 非原子；无 outbox 时依赖启动 intent + requeue。
- **F/H**: Continue / workflow 路由把 stale awaiting confirmation 置于 live journey 之上 → scene-review 死路。
- **G**: confirmed revision 未在 presentation 层压过 draft-empty 空态。

Not primary: Provider/quota (现场充足).

## Fix summary (this change)

1. Confirm+Start 写入 `starting` + `mark_journey_startup_intent`；响应带 `workflow_state` / `already_started` / ids。
2. `force_startup` **不得**打断未领取 starting/queued；返回 `requeue_journey_ids`，lifespan 安全重入。
3. Worker `claim_journey_worker`：starting → running + claim 时间戳。
4. `effective_chapter_status` / 前端 composition：**live journey 优先于** awaiting confirmation。
5. Continue / 确认页：已确认时返回进度，不进死路；文案区分「正在启动」与真实中断。

## Invariants (post-fix)

见需求第七节；由 `apps/api/tests/test_confirm_start_journey_race_chg013.py` 与前端 composition/presentation 测试覆盖关键路径。
