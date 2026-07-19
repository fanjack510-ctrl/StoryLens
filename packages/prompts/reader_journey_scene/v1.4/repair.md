修复以下Reader Journey Scene JSON，使其满足 v1.4 契约与Evidence范围。不得大幅改写文学判断，只修JSON/Schema/Evidence/覆盖/数量与长度上限。

特别针对读者问题：
- 若错误为 JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION：不得编造 prior question；应将非法 answered 删除或改为与真实 prior 完全一致的问题文本；若实际是信息揭示/回报，把内容移入 payoffs 或 information_changes，并使 reader_question_answered=[]。
- created_in_scene 必须迁移到 reader_question_created。
- reader_question_out 必须含 origin 与 evidence_paragraph_ids。
- 不得通过删除全部问题链逃避校验；不得改变 Scene 数量或 Scene ID；不得伪造 Evidence。

错误：{validation_error}
无效JSON或片段：{raw_response}
契约：{schema_json}
修复原因：{repair_reason}
