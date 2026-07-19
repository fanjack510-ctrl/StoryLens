# Phase 2B.8 候选边界二次裁决

v3.4 的 `goal_change` 复验中，T0007 位于第三个检测批次的首个 owned transition。该批只包含 P0007—P0009，缺少 P0001—P0006 中建立上层场景目标和持续行动链的内容，因此局部步骤完成被误分类为 `completed_then_new + new_chain`。这属于批次接缝造成的局部视野误报，不是 JSON、Schema 或枚举能力问题。

v3.5 将第一遍输出改为 `boundary_candidate`，并移除模型 Evidence。候选 Evidence 由程序固定生成相邻 transition 的左右段落 ID，公共 Canonical 结果和历史 v3.4 读取保持兼容，也不再产生 Evidence repair。

第一遍完成全部确定性拆批后，系统合并候选并进入 `scene_boundary_adjudication/v1`。裁决输入提供候选左右段落、最多三个前置与三个后续段落、章节标题、transition 序号和总数。短 fixture 可合并完整小范围上下文；长章节按保守 Token 估算确定性拆分，每个候选仅归属一个裁决批次。

最终边界同时要求第一遍枚举满足既有业务规则，以及第二遍返回 `accept=true + primary_scene_change + new_scene_chain`。裁决只确认变化范围，不改变第一遍确定生成的 Canonical reason。局部子目标、临时中断、同场景行动链或恢复原行动链均被拒绝并保留审计。
