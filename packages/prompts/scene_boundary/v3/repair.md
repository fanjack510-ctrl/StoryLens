上次响应未通过{repair_reason}。保持原有语义和paragraph_id结论，仅修复指定错误；若错误属于Evidence或业务规则，重新依据正文判断。只返回契约JSON。
响应契约：{response_contract}
<STORYLENS_INPUT>{input_snapshot}</STORYLENS_INPUT>
原任务：{original_user_content}
上次响应：{raw_response}
错误：{validation_error}
Schema：{schema_json}
