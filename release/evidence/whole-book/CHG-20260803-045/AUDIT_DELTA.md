# AUDIT_DELTA — post-planning subagent corroboration

Planning commit baseline: `f2d54c6ed0e333d38207d1345e65b760fc028245`（CHG-045）

## Sources
- [Audit Free E2E backend](a0adc3cd-2d08-4ffa-b307-2f95c98da697)
- [Audit Free E2E desktop](da1b73d8-c797-4e73-a382-993852f31373)

## Newly confirmed Wave 1 must-fix（beyond initial plan draft）

| ID | Finding | Owner |
|---|---|---|
| B1 | `validate_whole_book_consent(session, consent.id, book_id)` 签名不兼容 → create-fixture TypeError 风险 | Agent 1 |
| B2 | Consent 无 snapshot_id 绑定（仅 revision）— 需产品确认，至少测 revision | Agent 1 |
| B3 | `project_result` finalize 不 gate 四模块齐备 | Agent 1 |
| D1 | Reader 用 `chapter_index` 当 chapter id → 错章 | Agent 2 |
| D2 | Evidence drawer `indexOf` fuzzy 与 no-fuzzy 合同冲突 | Agent 2 |
| D3 | CF restore* 正式 Evidence 回链丢失 / restoreCursor 未恢复分页 | Agent 2 |

## Unchanged high-level verdict
Fixture 同 Run 主链存在；正式 real create 仍关闭；Wave 1 = Fake/Fixture 稳定化 + 上述 P0；48f/Vitest30/check_project → Wave 2。

## Docs updated this delta
- `COST_CONSENT_AUDIT.md`
- `EVIDENCE_E2E_AUDIT.md`
- `IMPLEMENTATION_PLAN.md`
- `AGENT_OWNERSHIP.md`
- `TEST_COVERAGE_GAP.md`
