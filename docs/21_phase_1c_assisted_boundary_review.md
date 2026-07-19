# Phase 1C-A 人工辅助场景边界审阅

## Phase 2B 冻结结论

云端 Provider、安全预算、Invocation 审计、结构化输出、Scene Analysis 和原创短篇流水线工程链路已经就绪。现有有限校准样本显示，Plus 在部分复杂目标变化边界上仍有语义不稳定风险；这不代表模型在所有文本上的普遍表现，但足以阻止未经审阅的自动边界路由。

冻结能力标记为：`cloud_engineering_ready=true`、`structured_output_ready=true`、`scene_analysis_ready=true`、`automatic_boundary_routing_ready=false`、`assisted_boundary_review_ready=true`。Plus 保持非默认，`allow_auto_route=false`。

## 适用范围

Plus 可用于生成结构化边界候选和已确认 Scene 的结构分析；不可把复杂边界候选直接固化为用户小说的正式 Scene。所有正式章节均进入 Review Session，包括没有候选的章节。

## Review 数据

`BoundaryReviewSession` 关联 Book、Chapter、AnalysisRun、Provider、模型和 Prompt 版本，并维护 pending、in_review、confirmed、superseded、cancelled 状态。

`BoundaryReviewDecision` 保存 transition 左右段落、模型候选枚举、裁决结果、风险等级和用户接受、拒绝或人工新增决定。模型请求正文和凭据不进入审阅表。

`BoundaryRevision` 保存不可覆盖的最终边界列表、确认人、确认时间和覆盖率。正式 Scene 关联 Revision，并记录 `model_accepted` 或 `user_added` 来源；模型拒绝决定保留在 Review Decision 中。

## 用户流程

候选生成完成后 Run 进入 `awaiting_boundary_review`。用户在连续正文和章节时间线上查看候选，可接受、拒绝、在其他段落间隙新增或删除人工边界、撤销操作、保存草稿并查看 Scene 预览。风险仅控制 high、medium、low 排序，不会自动接受候选。

确认时后端校验所有模型候选已有决定、边界属于本章、不重复且不位于最后一段之后；随后生成新 Revision 和连续覆盖全章的 Scene。旧 Run、Artifact、Decision、Revision 和 Scene 均不覆盖。

## Scene Analysis 门禁

正式用户章节只有 Review Session 为 confirmed 且 Scene 覆盖率为 100% 时才能进入 Scene Analysis。未确认返回 `BOUNDARY_REVIEW_REQUIRED`。跳过审阅默认关闭，只保留给明确标识的离线 fixture，不能默认用于用户小说。

## Phase 1C-A.4 分阶段预算

创建任务（Stage 1）只为边界候选 Detection + Adjudication 预留预算，不得包含 `expected_scenes` / Scene Analysis。进入 `awaiting_boundary_review` 前释放 Stage 1 Reservation。确认边界后按最终 Scene 做 Stage 2 预留；不足时进入 `boundary_confirmed_budget_blocked`，可通过 `resume-scene-analysis` 恢复。详见 `docs/23_phase_1ca4_staged_budget.md`。

## Provider 能力状态

`aliyun_qwen_plus` 暴露：结构化输出支持、Scene Analysis 支持、边界候选支持、自动边界路由关闭、需要边界审阅。进入 Phase 1C-A 不会改变 default 或 `allow_auto_route`。

## Phase 1C-A.5 传输与错误分类

Provider 传输失败不得误标为业务校验失败。单 Provider 启停以 `ProviderConfiguration.enabled` 为准；「传输诊断」零 Token，「真实连接测试」需单独确认。详见 `docs/24_phase_1ca5_provider_transport.md`。

## Phase 1C-A.7 语义冲突与恢复

人工审阅模式不再因单个候选与确定性枚举规则冲突而丢弃整章。Schema 与 transition 覆盖
合法后，冲突保存为 `semantic_review_conflict`，以 high priority、pending 状态进入
Review Session，不执行 semantic business repair。用户接受冲突时必须选择人工原因，
来源保存为 `user_accepted_model_conflict`。

Detection 每批完成后写入不含正文的检查点。历史失败 Run 可从 Invocation 离线重建检查点；
用户查看剩余预算并重新同意云端正文后，可创建带来源关系的新 Run，只执行未完成批次。
原 Run 和 Invocation 不改写。详见
`docs/26_phase_1ca7_review_conflicts_and_checkpoints.md`。

确认后的 Stage 2 失败不得再显示 Detection「从已有结果继续」。应复用 BoundaryRevision 与
正式 Scene，经 `resume-scene-analysis` 只分析未完成 Scene。详见
`docs/27_phase_1ca10_scene_analysis_resume.md`。

## 后续样本计划

后续可在用户明确选择并确认费用后扩大原创、多题材和不同章节长度的审阅样本，统计人工接受率、误报类型和风险分级校准；不得以单个校准样本替代跨题材能力结论。
