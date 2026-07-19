# Phase 2B.1 结构契约诊断

上一轮10个Plus首轮响应均为合法JSON，但没有遵循Pydantic契约。边界响应实际以`scenes`或`scene_boundaries`为顶层，使用场景段落列表；`SceneBoundaryResult`要求顶层`chapter_id`、`boundaries`、`overall_confidence`，边界项要求`after_paragraph_id`与置信度。因而首轮共同缺失`chapter_id`和`overall_confidence`，且顶层层级错误。

Scene Analysis首轮同样使用了模型自行选择的字段名，缺失`entry_state`、`goal`、`obstacle`、`key_actions`、`turning_point`、`outcome`、`unresolved_question`中的多个必填字段。Evidence层级也没有稳定遵循`{summary,evidence_paragraph_ids}`。这不是JSON提取问题，而是v2 Prompt只要求“现有结构字段”，没有展示精确字段、嵌套、必填项、枚举和空值规则；`response_format=json_object`只保证JSON对象，不保证Schema。

Flash后的响应能通过，是因为repair Prompt附带完整Pydantic Schema；这也证明根因是首次Prompt与Provider请求所见契约不同源，而不是Plus无法输出JSON。

v3通过`response_contract.py`从Pydantic生成规范Schema、精简契约、骨架和hash，并同时注入Prompt与ModelRequest。边界候选增加稳定reason code、摘要和前后状态；Scene Analysis明确Evidence和空值表达。完整响应不写入本诊断文档，且文档不包含用户正文。
