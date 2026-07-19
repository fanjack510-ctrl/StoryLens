修复以下Reader Journey Scene JSON，使其满足 v1.6 契约与Evidence范围。不得大幅改写文学判断，只修JSON/Schema/Evidence/覆盖/数量与长度上限。

特别针对读者问题与分数：
- 若错误为 JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION：不得编造 prior question；应将非法 answered 删除或重分类到 payoffs/information_changes。
- 若分数与 Hook 不匹配：仅校准 hook_score 与 Hook/Evidence 一致性；不得从 tension/curiosity 复制；不得为“制造分布”机械生成一个低分 Scene；不得删除合法 Hook/Evidence。
- created_in_scene 必须迁移到 reader_question_created。
- reader_question_out 必须含 origin 与 evidence_paragraph_ids。
- 不得通过删除全部问题链逃避校验；不得改变 Scene 数量或 Scene ID；不得伪造 Evidence。

特别针对 Evidence 数量（v1.6）：
- 顶层 evidence_paragraph_ids 最多 16 个；使用最少充分证据；不得枚举 Scene 全部段落。
- 若仅 Evidence 数量超限，系统会走定向压缩 patch，不得借机重写整个 Profile。

错误：{validation_error}
无效JSON或片段：{raw_response}
契约：{schema_json}
修复原因：{repair_reason}
