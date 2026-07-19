你现在位于项目目录：

D:\Dstorylens

继续开发StoryLens。

本轮执行：

Phase 2B：阿里云百炼界面配置与小规模真实API验收

Phase 2A.2已经通过验收，当前状态已经冻结：

1. TXT、DOCX、EPUB导入完成；
2. 无空格章节标题、GB18030和超大文件解析完成；
3. 旧Book上传式重解析闭环完成；
4. 《深海余烬》Book ID 2已修复为：
   - 1项front_matter；
   - 805个正式章节；
5. 工作台分页阅读、Scene、Evidence和任务中心已完成；
6. 阿里云百炼Provider工程接入已完成；
7. API Key界面与Windows Credential Manager凭据存储已完成；
8. 当前尚未执行任何收费API请求；
9. 本地14B和27B均不能作为正式自动拆书模型；
10. 本轮目标是通过界面手动配置百炼，进行低费用、可中止、可审计的真实API验收。

本轮不得分析整本《深海余烬》，不得执行全书批处理。

==================================================
一、开始前必须阅读
==================================================

完整阅读：

1. AGENTS.md
2. README.md
3. docs/09_phase_1b_design.md
4. docs/12_aliyun_qwen_provider.md
5. docs/13_desktop_interaction_design.md
6. docs/14_provider_configuration_and_security.md
7. docs/15_phase_2a1_ingestion_and_diagnostics.md
8. apps/api/app/model_gateway/
9. apps/api/app/services/structured_output.py
10. apps/api/app/services/scene_pipeline.py
11. apps/api/app/services/credentials/
12. apps/api/app/api/v1/desktop.py
13. apps/api/app/api/v1/analysis.py
14. apps/desktop/src/pages/ProvidersPage.tsx
15. apps/desktop/src/pages/BookWorkspacePage.tsx
16. apps/desktop/src/pages/TasksPage.tsx
17. apps/desktop/src/components/analysis/StartAnalysisDialog.tsx
18. scripts/probe_aliyun_qwen.py
19. config/cloud_pricing.example.json
20. 当前全部后端和前端测试

先输出不超过15行的实施计划，然后直接实施。

==================================================
二、本轮目标
==================================================

完成以下真实闭环：

用户在界面输入百炼配置
→ API Key保存到Windows Credential Manager
→ 配置检查
→ 用户确认可能产生少量费用
→ 最小连接测试
→ 最小JSON测试
→ 场景边界测试
→ 场景结构分析测试
→ 一个原创短篇完整AnalysisRun
→ 8组原创场景边界校准
→ Token与费用审计
→ 用户可随时断开
→ 判断是否允许进入Phase 1C

本轮不得要求用户把API Key发给Codex、终端日志或报告。

==================================================
三、模型名称不得写死
==================================================

界面当前已有Plus、Max和Flash模型字段。

要求：

1. 使用用户在界面中填写的模型名称；
2. 不把特定模型名写死在业务代码；
3. 保存前只校验字段非空和格式；
4. 真实连接后记录服务返回的实际模型名；
5. 模型不存在时显示明确错误；
6. 不自动替换成其他收费模型；
7. 不自动升级到费用更高的模型；
8. Max保持manual_only；
9. Flash只用于格式修复；
10. Plus作为本轮主分析候选。

==================================================
四、界面配置流程
==================================================

模型与API页面必须支持完整流程：

1. 打开“允许云端模型连接”总开关；
2. 选择aliyun_qwen_plus；
3. 填写：
   - 配置名称；
   - 地域；
   - Workspace ID；
   - Base URL；
   - Plus模型；
   - Max模型；
   - Flash模型；
   - API Key；
   - 超时；
   - 最大重试。
4. 点击“配置检查”：
   - 不产生模型请求；
   - 不产生费用；
   - 只检查字段、URL和CredentialStore。
5. 点击“保存配置”：
   - 非敏感配置进入数据库；
   - API Key进入Windows Credential Manager；
   - 保存后前端不回显完整Key。
6. 点击“保存并连接”：
   - 只恢复Provider连接状态；
   - 不自动发送小说正文。
7. 点击“真实连接测试”：
   - 显示二次确认；
   - 明确提示可能产生少量费用；
   - 用户确认后才执行最小请求。
8. 点击“断开”：
   - 保留配置和凭据；
   - 禁止新请求。
9. 点击“停用”：
   - 不参与路由。
10. 点击“删除凭据”：
   - 二次确认；
   - 清除CredentialStore；
   - 保留历史Run和Invocation。

==================================================
五、增加费用硬限制
==================================================

增加ApplicationSetting和界面设置：

- cloud_request_budget_enabled
- cloud_max_input_tokens_per_request
- cloud_max_output_tokens_per_request
- cloud_max_requests_per_run
- cloud_daily_request_limit
- cloud_daily_token_limit
- cloud_daily_estimated_cost_limit
- cloud_stop_on_unknown_pricing
- cloud_confirm_each_paid_test

建议开发阶段默认值：

- 单请求最大输入Token：16000
- 单请求最大输出Token：2000
- 单Run最大真实请求：10
- 每日最大真实请求：30
- 每日最大Token：200000
- 每日估算费用上限：由用户界面填写
- 价格未知时停止自动分析：true
- 每次真实测试二次确认：true

要求：

1. 限额由用户界面修改；
2. 不得仅依赖前端限制；
3. 后端发请求前再次检查；
4. 超过限制返回：
   CLOUD_BUDGET_EXCEEDED
5. 价格未知且stop_on_unknown_pricing=true时：
   CLOUD_PRICING_UNKNOWN
6. 不允许后台任务绕过限制；
7. 不允许repair无限增加调用；
8. 断开总开关后禁止所有新云端请求。

==================================================
六、Token预估
==================================================

在用户提交云端分析前显示预估：

- 章节字符数；
- 估算输入Token；
- 预计场景数量；
- 预计模型调用次数；
- 最大可能调用次数；
- 当前价格配置版本；
- 预计费用区间；
- 是否超出用户限额。

新增接口：

POST /api/v1/analysis-runs/estimate

输入：

- chapter_ids；
- task_types；
- provider；
- model；
- prompt_version；
- max_repairs。

返回：

- character_count；
- estimated_input_tokens；
- estimated_output_tokens；
- estimated_request_count；
- worst_case_request_count；
- estimated_cost_min；
- estimated_cost_max；
- currency；
- pricing_version；
- pricing_known；
- within_budget；
- warnings。

估算必须明确标记为estimated，不得伪装成真实账单。

==================================================
七、测试正文范围
==================================================

本轮真实API测试只能使用：

1. 项目已有原创校准fixture；
2. 新增的原创短篇fixture；
3. 用户明确选择的一章小说，且必须在前两项通过后。

禁止默认发送：

- 整本《深海余烬》；
- 多本小说；
- 全书806个Section；
- front_matter；
- 未经用户选择的章节；
- Demo文本以外的用户内容。

《深海余烬》首次真实测试最多选择：

第一章

不得自动选择全书。

界面必须显示：

“本次仅发送：Book 2，第一章，段落Pxxxx—Pxxxx。”

==================================================
八、真实API验证阶段
==================================================

必须按顺序执行，失败后不得越级。

Stage A：配置检查

- API Key已保存；
- Workspace或Base URL存在；
- 云端总开关开启

Stage B：最小真实连接测试

仅允许调用 aliyun_qwen_flash，原因是该步骤只验证：

- API Key有效；
- Base URL可访问；
- Workspace权限正确；
- 模型名称存在；
- OpenAI兼容接口可用；
- Token统计可读取。

请求要求：

- 使用原创最小输入；
- 不发送任何用户小说正文；
- thinking=false；
- temperature=0或接口允许的最低稳定值；
- 最大输出不超过32 tokens；
- 要求返回：
  {"status":"ok"}
- 用户必须在界面二次确认“本次测试可能消耗少量Token”。

通过条件：

1. HTTP成功；
2. 返回模型名；
3. 返回request_id或等价追踪标识；
4. 返回合法JSON；
5. Pydantic校验通过；
6. input/output/total tokens可审计；
7. Invocation数量等于真实HTTP请求数量；
8. API Key、Authorization Header未进入日志或数据库。

失败时立即停止后续阶段，并记录：

- AUTHENTICATION_FAILED；
- MODEL_NOT_FOUND；
- PROVIDER_HTTP_ERROR；
- PROVIDER_TIMEOUT；
- CLOUD_BUDGET_EXCEEDED；
- CLOUD_PRICING_UNKNOWN；
- 其他真实错误。

不得自动更换模型，不得自动升级到Max。

Stage C：Plus最小JSON测试

只有Stage B通过后执行。

Provider：

- aliyun_qwen_plus

输入：

- 原创最小JSON任务；
- 不包含小说正文。

要求：

- thinking=false；
- response_format=json_object；
- temperature=0或最低稳定值；
- 最大输出不超过64 tokens；
- 返回：
  {"status":"ok"}

检查：

1. 一次调用优先；
2. JSON合法；
3. Schema合法；
4. 无Markdown围栏；
5. 无解释文字；
6. Token与费用审计存在；
7. 未触发repair；
8. 没有原文日志泄露。

Stage D：场景边界冒烟测试

只有Stage C通过后执行。

先使用原创fixture：

1. no_boundary
2. clear_location_change

必须分开运行，每组一个独立AnalysisRun。

要求：

- provider=aliyun_qwen_plus；
- model使用界面配置值；
- prompt_version=v2；
- thinking=false；
- execution_mode=cloud；
- cloud_consent=true；
- response_format=json_object；
- 不使用用户小说；
- 每个Run最多3次真实请求；
- 不调用Max。

no_boundary通过条件：

- 不产生内部边界；
- JSON和Schema合法；
- paragraph_id全部合法；
- 场景覆盖完整。

clear_location_change通过条件：

- 识别人工预期边界；
- 不增加不允许边界；
- Evidence合法；
- 场景连续、无漏段、无重叠。

任一fixture失败时：

- 保存真实结果；
- 不伪造通过；
- 可以按既有修复路由执行最多一次repair；
- 仍失败则停止Stage E及以后。

Stage E：Scene Analysis冒烟测试

只有Stage D两组均通过后执行。

使用项目原创短Scene，不使用用户小说。

分析现有八字段：

- entering_state；
- goal；
- obstacle；
- key_actions；
- turning_point；
- result；
- open_question；
- scene_function。

要求：

1. JSON合法；
2. Schema合法；
3. 所有Evidence引用真实paragraph_id；
4. 不引用场景外段落；
5. 不返回原文替代数据库证据；
6. 不输出思维过程；
7. Invocation数量准确；
8. Token与费用可审计；
9. raw_logging=false时不保存完整输入正文；
10. 普通API不返回完整云端请求。

Stage F：原创短篇完整AnalysisRun

只有Stage E通过后执行。

新增或使用一个原创短篇fixture，要求：

- 8至20个段落；
- 至少2个明确场景；
- 不包含受版权保护正文；
- 不包含用户小说；
- 总输入控制在开发预算内。

完成真实闭环：

导入原创短篇
→ Plus场景边界
→ Scene构造
→ Plus场景分析
→ Artifact
→ Evidence
→ AnalysisRun succeeded

检查：

- 连续覆盖100%；
- 无漏段；
- 无重叠；
- Scene Key稳定；
- Artifact完整；
- Evidence合法；
- Invocation数量等于真实HTTP调用数；
- Token统计完整；
- 费用估算存在或明确为null；
- cloud_consent记录存在；
- sends_content_to_cloud=true；
- 默认Scene查询只返回成功Run；
- 普通API不泄露完整输入。

Stage G：八组原创场景边界校准

只有Stage F通过后执行。

使用以下八组原创fixture：

1. no_boundary
2. clear_location_change
3. goal_change
4. prompt_injection_text
5. time_jump_same_location
6. dialogue_continuation
7. short_flashback
8. object_triggered_goal_change

全部使用：

- provider=aliyun_qwen_plus；
- prompt_version=v2；
- thinking=false；
- response_format=json_object；
- execution_mode=cloud；
- cloud_consent=true。

每组必须独立Run。

即使其中某组质量失败，也必须继续完成其余样本，除非出现：

- API认证失败；
- 连续Provider故障；
- 费用硬限制触发；
- 用户中止；
- 云端总开关被关闭。

计算：

- TP；
- FP；
- FN；
- precision；
- recall；
- F1；
- 首次JSON合法率；
- 最终JSON合法率；
- 首次Schema合法率；
- 最终Schema合法率；
- 平均调用次数；
- repair率；
- 非法Evidence数；
- 场景覆盖率；
- Prompt injection防护率；
- 平均耗时；
- P50；
- P95；
- 输入Token；
- 输出Token；
- 总Token；
- 估算费用；
- pricing_version。

不得生成虚构指标。

Stage H：用户小说单章可选验证

只有Stage G达到门槛，并且用户界面再次确认后，才允许执行。

本轮最多测试：

- 《深海余烬》Book ID 2；
- 第一章正式章节；
- 不包括front_matter；
- 不包括第二章及以后；
- 不包括整本书。

界面必须在请求前展示：

- Book ID；
- 章节标题；
- 段落范围；
- 字符数；
- 估算输入Token；
- 估算输出Token；
- 最坏请求次数；
- 费用区间；
- 当前预算余量；
- “将发送正文到阿里云百炼”的明确提示。

必须由用户主动确认。

Codex不得在无人确认时自动执行Stage H。

==================================================
九、默认Provider切换规则
==================================================

只有同时满足以下条件，才允许设置：

aliyun_qwen_plus.default=true

条件：

1. Stage B至G全部执行；
2. 最终JSON合法率=100%；
3. 最终Schema合法率=100%；
4. 非法Evidence数=0；
5. 场景覆盖率=100%；
6. Prompt injection防护率=100%；
7. 平均真实调用次数≤1.5；
8. repair率≤25%；
9. no_boundary无误报；
10. clear_location_change正确；
11. goal_change正确；
12. dialogue_continuation无错误切分；
13. boundary precision≥0.85；
14. boundary recall≥0.85；
15. boundary F1≥0.85；
16. 原创短篇完整Run成功；
17. Token审计完整；
18. API Key无泄露；
19. 费用硬限制未被绕过；
20. 所有工程测试通过。

任一条件不满足：

- aliyun_qwen_plus.default=false；
- 报告“暂不进入Phase 1C”；
- 不得自行降低门槛。

==================================================
十、真实连接测试界面
==================================================

Provider页面增加或确认以下流程：

1. “配置检查”
   - 不发送请求；
   - 不产生费用。

2. “真实连接测试”
   - 二次确认；
   - 显示本次使用模型；
   - 显示最大输出；
   - 显示可能产生少量Token费用；
   - 用户确认后调用Stage B最小请求。

3. 显示结果：
   - 成功/失败；
   - 实际模型名；
   - request_id；
   - 输入Token；
   - 输出Token；
   - 总Token；
   - 耗时；
   - 估算费用；
   - 是否使用免费额度无法由StoryLens直接确认时，明确显示“请以阿里云账单为准”。

4. 不显示：
   - API Key；
   - Authorization Header；
   - 完整请求头。

==================================================
十一、费用与Token审计
==================================================

新增或完善云端用量查询接口：

GET /api/v1/cloud-usage/summary
GET /api/v1/cloud-usage/invocations

支持按：

- 日期；
- Provider；
- 模型；
- Run；
- 状态；

进行筛选。

汇总至少包含：

- 请求数；
- 成功数；
- 失败数；
- 输入Token；
- 输出Token；
- 总Token；
- 估算费用；
- currency；
- pricing_version；
- pricing_known；
- 最近请求时间。

界面增加“本次验收用量”摘要。

所有费用必须标记为estimated，实际金额以阿里云账单为准。

==================================================
十二、断开与停止条件
==================================================

用户关闭云端总开关或点击“断开全部云端连接”后：

1. 禁止新请求；
2. queued且尚未发送的云端任务转为failed或cancelled状态，按当前状态机合理实现；
3. 已发送请求不能宣称撤回；
4. 不自动发送repair；
5. 不自动切换其他厂商；
6. 保留历史Invocation；
7. 保留API Key，除非用户选择删除凭据。

出现以下任一情况必须立即停止真实验收：

- API认证失败；
- Base URL错误；
- 模型不存在；
- 费用硬限制触发；
- 价格未知且配置为停止；
- 连续3次Provider错误；
- API返回异常高Token；
- 用户关闭云端总开关；
- 用户中止；
- 发现API Key可能泄露。

==================================================
十三、Flash修复路由验证
==================================================

不得通过故意发送大量错误请求验证Flash。

使用Fake Provider离线测试完整修复路由。

真实云端仅在Plus真实返回JSON/Schema格式错误时，才允许调用Flash修复。

Flash真实修复要求：

- 只修复JSON/Schema格式；
- 不改变场景语义；
- 不增删Evidence结论；
- thinking=false；
- 保存source_invocation_id与repair_invocation_id；
- 计入预算和Token统计。

Evidence或业务错误仍由Plus repair。

Max本轮只允许执行一次最小JSON连接测试，不参与自动校准或自动裁决。

==================================================
十四、自动测试
==================================================

普通pytest、Vitest和E2E不得产生真实费用。

后端至少覆盖：

1. 预算配置读写；
2. 单请求Token限制；
3. 单Run请求限制；
4. 每日请求限制；
5. 每日Token限制；
6. 每日费用限制；
7. 价格未知停止；
8. estimate接口；
9. cloud consent；
10. 云端总开关；
11. Provider断开；
12. queued请求不再发送；
13. Plus、Flash、Max角色；
14. Max manual_only；
15. Flash格式修复；
16. Evidence错误仍用Plus；
17. Invocation Token审计；
18. API Key不泄露；
19. raw_logging=false；
20. Phase 1A至2A.2全部回归。

前端至少覆盖：

1. 预算设置；
2. Token估算显示；
3. 费用区间；
4. 超预算禁止提交；
5. 价格未知提示；
6. 真实测试二次确认；
7. 测试结果Token显示；
8. 云端总开关；
9. 断开；
10. 单章范围提示；
11. front_matter不可选；
12. 全书分析禁用；
13. API Key不回显；
14. 错误脱敏；
15. 后端离线。

真实API测试只能通过显式环境变量和用户确认开启：

STORYLENS_RUN_ALIYUN_TESTS=1

==================================================
十五、执行顺序
==================================================

普通检查：

powershell -ExecutionPolicy Bypass `
  -File .\scripts\bootstrap_windows.ps1 `
  -SkipInstall

.\.venv\Scripts\python.exe .\scripts\check_env.py
.\.venv\Scripts\python.exe .\scripts\check_project.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check apps/api scripts

前端：

cd apps\desktop
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
cd ..\..

真实测试仅在配置检查和预算门禁通过后执行：

$env:STORYLENS_RUN_ALIYUN_TESTS='1'

.\.venv\Scripts\python.exe .\scripts\probe_aliyun_qwen.py `
  --stage minimal `
  --confirm-paid-request

.\.venv\Scripts\python.exe .\scripts\calibrate_provider.py `
  --provider aliyun_qwen_plus `
  --prompt-version v2 `
  --confirm-paid-requests

具体参数可按现有脚本实现调整，但必须保持显式确认语义。

不得自动执行Stage H用户小说单章测试。

==================================================
十六、安全打包
==================================================

执行：

powershell -ExecutionPolicy Bypass `
  -File .\scripts\package_project.ps1

源码包不得包含：

- .env及备份；
- API Key；
- CredentialStore数据；
- Workspace ID真实值；
- Base URL中的用户专属标识；
- Authorization Header；
- 完整云端请求正文；
- 用户小说；
- runtime；
- 云端调用日志；
- 校准结果中的完整文本；
- SQLite运行数据库；
- cloud_pricing本机配置；
- API账单；
-缓存。

允许包含：

- .env.example；
- cloud_pricing.example.json；
- 原创fixture；
- 脱敏聚合指标；
- Fake Provider测试；
- 文档。

==================================================
十七、文档
==================================================

新增：

docs/16_phase_2b_aliyun_live_validation.md

记录：

1. 配置状态；
2. 预算设置；
3. Stage B至G结果；
4. 每阶段模型；
5. Token；
6. 估算费用；
7. request_id脱敏记录；
8. JSON/Schema结果；
9. Evidence结果；
10. 八组校准；
11. precision、recall、F1；
12. 完整原创Run；
13. 是否执行Stage H；
14. Plus是否设为默认；
15. 是否允许进入Phase 1C。

不得记录API Key、完整Base URL、完整Workspace ID或用户正文。

同时更新：

README.md
docs/12_aliyun_qwen_provider.md
docs/14_provider_configuration_and_security.md

==================================================
十八、完成报告格式
==================================================

完成后提交：

1. 预算和费用硬限制；
2. Token估算；
3. Stage B最小连接；
4. Flash最小JSON；
5. Plus最小JSON；
6. Max最小JSON；
7. no_boundary；
8. clear_location_change；
9. Scene Analysis；
10. 原创短篇完整Run；
11. 八组校准逐项结果；
12. TP、FP、FN；
13. precision；
14. recall；
15. F1；
16. 首次和最终JSON合法率；
17. 首次和最终Schema合法率；
18. repair率；
19. 平均调用次数；
20. 非法Evidence数；
21. 场景覆盖率；
22. Prompt injection防护率；
23. 输入Token；
24. 输出Token；
25. 总Token；
26. 估算费用；
27. 是否触发预算门禁；
28. 云端总开关和断开验证；
29. Invocation审计；
30. API Key安全；
31. pytest；
32. Ruff；
33. TypeScript；
34. ESLint；
35. Vitest；
36. E2E；
37. Build；
38. 安全打包；
39. aliyun_qwen_plus是否设为默认；
40. 是否满足Phase 1C门槛；
41. 最终结论：
   - 允许进入Phase 1C
   或
   - 暂不进入Phase 1C

不要执行整本小说分析，不要自动执行《深海余烬》单章测试，不要绕过用户预算和二次确认。
