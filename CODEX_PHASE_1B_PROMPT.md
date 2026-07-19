# Codex 执行任务｜Phase 1B：本地模型场景分析闭环

你现在负责 StoryLens 项目的 Phase 1B 实施。

## 一、开始前必须做

1. 阅读项目根目录 `README.md`、`AGENTS.md`。
2. 阅读 `docs/` 下全部文档，重点阅读：
   - `03_processing_pipeline.md`
   - `04_model_gateway.md`
   - `06_mvp_roadmap.md`
   - `09_phase_1b_design.md`
3. 检查当前 Phase 0 + Phase 1A 代码和测试，禁止推倒重写已经通过验收的导入链路。
4. 先输出你的实施计划、预计修改文件和风险点，再开始编码。

## 二、本轮唯一目标

打通以下闭环：

```text
已导入章节
→ local_llama Provider
→ 场景边界识别
→ Scene 实体生成
→ 单场景结构分析
→ JSON/Pydantic/证据校验
→ SQLite 持久化
→ API 查询
→ 单章失败重跑
```

本轮只做“场景边界 + 场景结构分析”。不要实现情节链、钩子、人物描写、场景描写。

## 三、必须实现的架构

### 1. 通用模型网关

实现与厂商无关的：

- `ModelGateway`
- `ModelProvider` 协议或抽象基类
- `OpenAICompatibleProvider`
- `local_llama` Provider 注册
- `ProviderCapabilities`
- Provider 健康检查

领域服务不得直接调用 llama-server，也不得出现：

```python
if provider == "local_llama":
```

业务层只能通过模型网关调用。

### 2. 本地 llama-server 配置

从环境变量读取，至少支持：

```text
STORYLENS_DEFAULT_PROVIDER=local_llama
STORYLENS_LOCAL_LLAMA_BASE_URL=http://127.0.0.1:8080/v1
STORYLENS_LOCAL_LLAMA_API_KEY=local
STORYLENS_LOCAL_LLAMA_MODEL=<可配置>
STORYLENS_LOCAL_LLAMA_TIMEOUT_SECONDS=300
STORYLENS_LOCAL_LLAMA_MAX_CONTEXT_TOKENS=<可配置>
```

不得写死本地模型名称、端口和路径。

### 3. 数据库

在保留现有模型的基础上，增加可复用的数据结构：

- `Scene`
- `AnalysisArtifact`
- `AnalysisEvidence`
- `ModelInvocation`

扩展 `AnalysisRun` 状态和元数据，使其能够保存：

- `task_type=scene_pipeline`
- `subject_type=chapter`
- `subject_id`
- provider/model
- prompt/schema 版本
- input hash
- progress
- queued/running/succeeded/failed
- 错误信息
- retry 关系

不要为每一种后续文学分析都建立独立结果表。`AnalysisArtifact` 必须能供 Phase 1C 复用。

### 4. 场景 ID 与覆盖规则

Scene ID：

```text
B0001-C0001-S0001
```

必须满足：

- 顺序稳定；
- 整章段落连续覆盖；
- 无重叠；
- 无漏段；
- 场景起止段落属于同一章节；
- 新一次分析保留历史，不覆盖旧 Run 和旧 Artifact。

### 5. 场景边界任务

实现 `SceneBoundaryResult` Pydantic Schema。

模型只返回内部场景边界：

```json
{
  "chapter_id": "B0001-C0001",
  "boundaries": [
    {
      "after_paragraph_id": "B0001-C0001-P0012",
      "reasons": ["地点发生变化", "当前任务发生变化"],
      "confidence": 0.86
    }
  ],
  "overall_confidence": 0.82
}
```

程序负责把边界构造成 Scene，模型不得直接决定场景编号和最终起止范围。

长章节必须支持按字符数窗口化和段落重叠，禁止按固定段数独立切开后直接视为场景。

### 6. 场景结构分析任务

实现 `SceneAnalysisResult` Pydantic Schema，至少包括：

- entry_state
- goal
- obstacle
- key_actions
- turning_point
- outcome
- unresolved_question
- function_tags
- confidence

每个主要字段必须携带 `evidence_paragraph_ids`。

所有证据必须由程序验证：

- 段落真实存在；
- 属于当前章节；
- 属于当前场景；
- 起止顺序正确。

模型只返回段落 ID。原文由数据库读取，不接受模型自行改写出的“原文证据”。

### 7. JSON 解析与修复

实现统一结构化输出管线：

```text
原始响应
→ 去代码围栏
→ 提取完整 JSON
→ json.loads
→ Pydantic 校验
→ 业务校验
```

失败时调用版本化 Repair Prompt，最多两次。

每一次尝试都写入 `ModelInvocation`，包括：

- 原始响应；
- 解析结果；
- 校验错误；
- 耗时；
- provider/model；
- prompt/schema 版本；
- attempt_no。

两次修复后仍失败，AnalysisRun 必须为 `failed`，不得用空结果伪装成功。

### 8. Prompt 文件化

在 `packages/prompts/` 下建立：

```text
scene_boundary/v1/system.md
scene_boundary/v1/user.md
scene_boundary/v1/repair.md
scene_analysis/v1/system.md
scene_analysis/v1/user.md
scene_analysis/v1/repair.md
```

Prompt 必须：

- 版本化；
- 可读取；
- 计算内容哈希；
- 保存到运行元数据；
- 不得大段硬编码在 Python 业务函数中。

### 9. 后台任务

不得引入 Redis/Celery。

允许使用 FastAPI `BackgroundTasks` 或轻量应用内执行器：

- POST 立即返回 `202`；
- 状态持久化；
- 异常转为 failed；
- 进程重启遗留 running 任务不得被误认为成功；
- 支持人工重跑。

## 四、必须实现的 API

### Provider

```text
GET /api/v1/model-providers
GET /api/v1/model-providers/{provider_name}/health
```

### 运行任务

```text
POST /api/v1/chapters/{chapter_id}/analysis-runs
GET  /api/v1/analysis-runs/{run_id}
POST /api/v1/analysis-runs/{run_id}/retry
```

创建请求：

```json
{
  "task_type": "scene_pipeline",
  "provider_name": "local_llama",
  "force": false
}
```

创建成功返回 `202 Accepted`。

### 场景结果

```text
GET /api/v1/chapters/{chapter_id}/scenes
GET /api/v1/scenes/{scene_id}
GET /api/v1/scenes/{scene_id}/analysis-artifacts
```

所有错误继续使用 Phase 1A 已有的统一错误结构。

## 五、测试要求

默认自动测试不得依赖真实 llama-server。必须实现 Fake Provider。

至少覆盖：

1. Provider 注册、能力与配置；
2. Provider 健康检查成功和失败；
3. JSON 代码围栏提取；
4. JSON 非法后进入修复流程；
5. Pydantic 校验失败；
6. 引用不存在段落 ID 被拒绝；
7. 引用场景外段落被拒绝；
8. 场景连续覆盖、无重叠、无漏段；
9. Fake Provider 完整场景流水线；
10. AnalysisRun 成功、失败与进度；
11. POST 返回 202；
12. 重跑保留旧运行和旧结果；
13. 同一输入下 Scene ID 稳定；
14. 文件导入原有 4 个测试仍通过。

增加可选本地模型冒烟测试：

```text
STORYLENS_RUN_LOCAL_MODEL_TESTS=1
```

该测试默认跳过，使用项目内原创中文 fixture，不使用外部版权小说。

## 六、脚本和文档

更新或新增：

- `.env.example`
- `README.md`
- `scripts/check_project.py`
- 一个本地模型健康检查/冒烟测试脚本
- 必要的数据库初始化或迁移说明

不得要求用户手工修改数据库文件。

## 七、明确禁止

本轮禁止：

- 接入阿里云百炼、DeepSeek、智谱、Kimi；
- 写桌面 UI；
- 做钩子、人物、环境、情节链；
- 使用 Redis、Celery、Neo4j、pgvector；
- 训练或加载拆书 LoRA；
- 多模型投票；
- 一次把整本书发送给模型；
- 用模型生成的摘录替代数据库原文；
- 为赶进度绕过 Pydantic 或证据校验；
- 删除 Phase 1A 已通过功能。

## 八、验收命令

完成后必须实际运行并报告：

```text
pytest
ruff check
python scripts/check_project.py
```

还要实际启动 API，验证：

```text
GET /health
GET /api/v1/model-providers
POST /api/v1/chapters/{chapter_id}/analysis-runs
GET /api/v1/analysis-runs/{run_id}
GET /api/v1/chapters/{chapter_id}/scenes
```

没有本地模型时使用 Fake Provider 完成闭环；有本地 llama-server 时再执行可选冒烟测试。

## 九、完成报告格式

完成后严格按以下结构返回：

```text
Phase 1B 完成情况

1. 实际读取文件数量
2. 新增文件列表
3. 修改文件列表
4. 数据模型变更
5. API 完成情况
6. Model Gateway 完成情况
7. JSON/证据校验完成情况
8. 测试命令及完整结果
9. Fake Provider 闭环结果
10. 本地 llama-server 冒烟测试结果（执行/未执行及原因）
11. 已知限制
12. 未完成项
13. 是否跨越 Phase 1B 边界：必须回答“否”
```

## 十、停止条件

出现以下情况时停止并报告，不得擅自改架构：

- 现有 AnalysisRun 模型与新状态机存在不可兼容冲突；
- 现有段落 ID 无法保证顺序或唯一性；
- 需要更换数据库技术才能实现；
- llama-server 接口与配置无法按 OpenAI 兼容方式接入；
- 测试无法在无真实模型环境下运行；
- 需要跨入 Phase 1C 才能完成当前闭环。
