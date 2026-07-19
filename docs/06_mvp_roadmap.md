# 06｜MVP 开发路线

## Phase 0：项目骨架

- 目录、文档、配置规范；
- FastAPI 可启动；
- SQLite 可连接；
- Provider 配置可读取。

## Phase 1A：文本导入闭环

- TXT、DOCX、EPUB；
- 章节识别；
- 段落编号；
- 数据入库与查询；
- 单元测试。

## Phase 1B：本地模型分析闭环

- llama-server 连通；
- Model Gateway；
- Scene Boundary Schema；
- Scene Analysis Schema；
- JSON 与证据校验；
- 单章重跑。

## Phase 1C：五个核心维度

- 场景；
- 情节链；
- 钩子；
- 人物描写；
- 场景描写。

## Phase 2：可视化界面

- Tauri + React；
- 三栏阅读界面；
- 原文与分析对照；
- 模型切换；
- 任务进度；
- 人工修正。

## Phase 3：国内 API

- 阿里云百炼；
- DeepSeek；
- 智谱；
- Kimi；
- 手动复核与结果对比。

## Phase 4：检索与个人案例库

- PostgreSQL + pgvector；
- 全文、标签、语义混合检索；
- 案例收藏；
- 多书比较。

## Phase 5：评测与训练数据

- 金标测试集；
- 错误类型统计；
- 用户修正数据集；
- 评估是否训练专项 LoRA。
# Phase 2A 状态

Phase 2A 已增加可运行的桌面交互层、书库导入、三栏书籍工作台、任务中心、模型配置中心、设置页及 Tauri 壳。该阶段只消费 Phase 1A/1B/1B.4 已有能力，不扩展新的文学分析类型。案例库及情节链、钩子、人物塑造等仍为规划中。
