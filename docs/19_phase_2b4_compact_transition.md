# Phase 2B.4 紧凑 Transition 协议

v3.3 将 Provider DTO 与 Canonical `SceneBoundaryResult` 分离。每个候选只返回枚举 decision，
只有选中边界返回自然语言详情；适配器验证覆盖、顺序、重复、详情对应、业务规则和 Evidence，
再确定性映射到 left paragraph。Provider 与 Canonical schema hash 分别保存，拒绝候选的枚举
分类进入脱敏 Invocation 审计。

正式章节使用 `TransitionBatchPlanner` 规划不重叠 owned transitions，上下文可以重叠但决策
所有权不重叠。真实复验证明最初基于重复键压缩的估算过度乐观：goal_change 的八个 compact
decisions 仍连续两次达到 768 Token。因此估算已改为 ASCII 四字符一 Token、CJK 一字符一
Token 的保守算法；超过 72% 输出预算时自动拆批。按本轮门禁，目标样本再次截断后停止，
不进入其余五组和完整 Run，Plus 继续保持非默认。
