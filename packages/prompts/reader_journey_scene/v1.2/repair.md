修复以下Reader Journey Scene JSON，使其满足 v1.2 契约与Evidence范围。不得大幅改写文学判断，只修JSON/Schema/Evidence/覆盖/数量与长度上限。
- created_in_scene 必须迁移到 reader_question_created
- reader_question_out 必须含 origin 与 evidence_paragraph_ids
错误：{validation_error}
无效JSON或片段：{raw_response}
契约：{schema_json}
修复原因：{repair_reason}
