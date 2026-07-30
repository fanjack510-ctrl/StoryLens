# StoryLens 1.1.2-rc.4 — Manual Installed Acceptance Checklist

隔离目录建议：

- Install: `%TEMP%\storylens-112-rc4-installed-acceptance\install\`
- AppData: `%TEMP%\storylens-112-rc4-installed-acceptance\AppData\StoryLens\`

约束：Fake Provider ON；Real Provider OFF；正式 AppData 写入 0；外部 Provider 调用 0。

## A. Provider Health
- [ ] 重新验证成功后立即启动分析
- [ ] preflight=FRESH
- [ ] 无 PROVIDER_HEALTH_STALE
- [ ] 无 HTTP 409
- [ ] API 重启后仍 fresh

## B. Confirm + Delayed Worker
- [ ] 确认 3 个场景并开始分析（点一次）
- [ ] Worker 延迟约 4s：显示「正在启动」，不显示 interrupted/failed，自动完成
- [ ] Worker 延迟约 10s：同上

## C. Confirm 幂等
- [ ] 快速重复 Confirm → revision/analysis/journey/reservation 各 1

## D. API 重启恢复
- [ ] Confirm 后、claim 前重启 API → 同 Run 恢复，不重确认

## E. Recoverable Interrupted Continue
- [ ] 一点 Continue → 同 Analysis/Journey Run，不进确认页，无空白死路

## F. Revision Binding
- [ ] 当前页仅显示确认后场景数；无重复 ordinal；无内部 Scene ID；无旧结果污染

## G. Hook
- [ ] 一句总判断；1–3 问题卡；一条悬念轨迹；一段洞察；无重复说明；无 Hook 技术分

## H. Task Cancellation
- [ ] 停止 → 正在停止 → 已停止；cancelled 不显示失败；停止后无新 Provider 调用；重启后仍停止

## Gate IDs
- Automatic installed acceptance: PASS（见 ISOLATED_INSTALLED_ACCEPTANCE.json）
- CWD: 6/6
- Confirm delay 4s/10s automatic: PASS（CONFIRM_DELAY_GATE.json）
- Next: MANUAL INSTALLED ACCEPTANCE
