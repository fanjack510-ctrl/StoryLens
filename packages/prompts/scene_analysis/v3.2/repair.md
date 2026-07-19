上次完整响应未通过{repair_reason}。重新输出完整契约JSON，只修复指定JSON、Schema、Evidence或业务完整性错误；不得添加Scene外证据，不得续写或拼接片段。
若错误与key_actions相关：无明确动作时保持key_actions=[]是合法的，不要为通过校验而编造动作或空证据动作；仅当原文确有可证据支持的动作时才填写非空key_actions，且每项必须带当前Scene内evidence_paragraph_ids。
响应契约：{response_contract}
<STORYLENS_INPUT>{input_snapshot}</STORYLENS_INPUT>
原任务：{original_user_content}
上次完整响应：{raw_response}
错误：{validation_error}
Schema：{schema_json}
