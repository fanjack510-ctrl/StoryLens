# 场景边界人工审阅

云端只生成边界候选；正式 Scene 在你确认后才固化。

## 你能做什么

- 接受 / 拒绝候选  
- 处理冲突与批量操作  
- 保存草稿  
- 完成审阅（覆盖应达到可分析状态）  

边界修订（BoundaryRevision）在确认后应按不可变审计理解：不要指望“悄悄改历史成功结果”。

预算采用分阶段预留：创建任务先覆盖边界阶段；确认边界后再为 Scene Analysis 预留。详见 `docs/21_phase_1c_assisted_boundary_review.md` 与 `docs/23_phase_1ca4_staged_budget.md`。
