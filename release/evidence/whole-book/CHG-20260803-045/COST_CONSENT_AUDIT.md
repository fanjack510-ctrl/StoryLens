# COST_CONSENT_AUDIT — CHG-20260803-045

## Cost estimate

| Item | Status | Evidence |
|---|---|---|
| Prepare 双路径含 estimate | ALREADY COMPLETE | prepare payload `estimate` + CHG-030 |
| 窗口单位纳入估算 | ALREADY COMPLETE | `estimated_window_count` |
| overview / structure / CF 合成计入 | PARTIALLY COMPLETE | `provider_calls = window_count + 3`（固定 +3） |
| characters_events 单独行 | N/A / covered by windows | 抽取在 window units 内 |
| chapter_functions 多批次 | MISSING in estimate | 估算未按 `MAX_CHAPTERS_PER_BATCH` 展开 |
| repair unit | MISSING in estimate | CF 最多 1 repair/batch 未计入 |
| max calls / budget 提示 | ALREADY COMPLETE | `recommended_limits` in prepare |
| Provider disabled 阻止正式启动 | ALREADY COMPLETE | `run_creation_enabled: real_on`；create_free 拒绝 |
| Fixture vs formal 区分 | ALREADY COMPLETE | `fixture_preview_enabled` + UI banner |

**COST ESTIMATE COMPLETE：PARTIAL**

Wave 1 必修：估算与实际 Provider Unit 规划对齐（至少 CF batch 数量；repair 策略明示）。

## Consent

| Item | Status | Evidence |
|---|---|---|
| Consent 绑定 revision | ALREADY COMPLETE | `create_whole_book_consent` / `validate_whole_book_consent` 比 `book_revision_hash` |
| Revision 变更失效 | ALREADY COMPLETE | `WHOLE_BOOK_BOOK_CHANGED` |
| Estimate 过期失效 | ALREADY COMPLETE | `is_estimate_valid` |
| 重复点击重复 Run | PARTIAL | run idempotency on `client_request_id`；UI 防抖/重复提交正式测缺口 |
| Fixture consent 自动创建 | INCONSISTENT | fixture create 内部建 consent；见下 |
| Consent 绑 snapshot_id | MISSING | 仅 `book_revision_hash` + estimate；无 snapshot_id |

**CONSENT BINDING CORRECT：PARTIAL**

### Wave 1 must-fix（Backend audit 确认）
`create_fixture_free_whole_book_analysis_v1` 调用：

```text
validate_whole_book_consent(session, consent.id, book_id)
```

但 `validate_whole_book_consent(session, consent_id, *, now=None)` **不接受** positional `book_id` → 产品 create-fixture 路径存在 **TypeError** 风险；现有 pytest 多用 `prepare_sample_s_run`，**未覆盖 create-fixture**。

## Wave 1 scope
- **修复 create-fixture consent 校验调用签名**（P0）  
- 对齐 cost ↔ unit plan（Backend）  
- 文档化/确认 consent 是否需绑 snapshot_id（产品决策；默认至少保持 revision）  
- 正式页：disabled provider / fixture banner / duplicate create 行为（Desktop）  
- **不**在本 Wave 开放真实 Provider 计费实跑（Wave 3）

## Audit delta source
[Audit Free E2E backend](a0adc3cd-2d08-4ffa-b307-2f95c98da697)
