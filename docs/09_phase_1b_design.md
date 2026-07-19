# 09｜Phase 1B 本地模型分析闭环设计

## 1. 阶段目标

在不接入任何付费云端 API、不开发桌面 UI 的前提下，打通以下最小闭环：

```text
章节段落
→ 本地 llama-server
→ 场景边界识别
→ 场景实体生成
→ 单场景结构分析
→ JSON/Pydantic 校验
→ 段落证据校验
→ SQLite 持久化
→ API 查询与单章重跑
```

本阶段完成后，系统应能够对一个已导入章节生成稳定场景 ID，并为每个场景保存可追溯的结构化分析。

## 2. 阶段边界

### 本阶段必须完成

- OpenAI 兼容的通用模型 Provider；
- `local_llama` Provider 配置；
- Provider 能力描述与健康检查；
- 场景边界 Schema；
- 场景分析 Schema；
- 版本化 Prompt；
- JSON 提取、修复与 Pydantic 校验；
- 段落 ID 与证据范围校验；
- `Scene`、`AnalysisArtifact`、`AnalysisEvidence`、`ModelInvocation` 持久化；
- AnalysisRun 状态机；
- 单章节异步分析、结果查询和失败重跑；
- Fake Provider 单元测试；
- 本地 llama-server 手工冒烟测试脚本。

### 本阶段禁止完成

- 阿里云百炼、DeepSeek、智谱、Kimi；
- 情节链、钩子、人物描写、场景描写；
- 桌面 UI；
- Redis、Celery、消息队列；
- 向量数据库与 pgvector；
- LoRA 训练；
- 多模型投票；
- 全书伏笔、人物弧光、图数据库；
- 把模型名称或 Provider 判断写入领域业务代码。

## 3. 领域数据模型

### 3.1 Scene

建议字段：

- `id`：稳定 ID，格式 `B0001-C0001-S0001`；
- `book_id`；
- `chapter_id`；
- `ordinal`；
- `start_paragraph_id`；
- `end_paragraph_id`；
- `content_hash`；
- `created_by_run_id`；
- `boundary_confidence`；
- `boundary_reason_json`；
- `created_at`、`updated_at`。

约束：

- 同一章节内 `ordinal` 唯一；
- 起止段落必须属于同一章节；
- 起始段落序号不得大于结束段落序号；
- 场景必须连续覆盖章节正文，不得重叠、不得漏段。

### 3.2 AnalysisArtifact

用于保存所有结构化分析结果，为 Phase 1C 复用。

建议字段：

- `id`；
- `run_id`；
- `artifact_type`：当前仅 `scene_boundary`、`scene_analysis`；
- `subject_type`：`chapter` 或 `scene`；
- `subject_id`；
- `schema_version`；
- `prompt_version`；
- `payload_json`；
- `confidence`；
- `validation_status`：`valid`、`invalid`、`needs_review`；
- `created_at`。

### 3.3 AnalysisEvidence

建议字段：

- `id`；
- `artifact_id`；
- `field_path`：例如 `goal.evidence`、`turning_point.evidence`；
- `paragraph_id`；
- `paragraph_hash`；
- `created_at`。

模型只返回段落 ID，原文由程序从数据库读取。禁止让模型生成“原文摘录”作为权威证据。

### 3.4 ModelInvocation

每一次模型调用均需保存：

- `id`；
- `run_id`；
- `task_type`；
- `provider_name`；
- `model_name`；
- `prompt_version`；
- `schema_version`；
- `attempt_no`；
- `request_hash`；
- `input_snapshot_json`；
- `raw_response_text`；
- `parsed_response_json`；
- `status`；
- `latency_ms`；
- `error_code`、`error_message`；
- `created_at`。

不得把 API Key、Authorization Header 写入数据库或日志。

## 4. AnalysisRun 状态机

```text
queued
→ running
→ succeeded

queued/running
→ failed

failed
→ queued（人工重跑，生成新的 run 或增加 retry_of_run_id）
```

建议保存：

- `task_type=scene_pipeline`；
- `subject_type=chapter`；
- `subject_id`；
- `provider_name`；
- `model_name`；
- `status`；
- `progress_current`、`progress_total`；
- `input_hash`；
- `prompt_version`；
- `schema_version`；
- `error_code`、`error_message`；
- `retry_of_run_id`；
- 开始、结束时间。

同一章节允许保留多次分析历史。新结果不得覆盖旧结果。

## 5. Model Gateway

### 5.1 统一接口

```python
class ModelProvider(Protocol):
    name: str

    async def health(self) -> ProviderHealth: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    def capabilities(self) -> ProviderCapabilities: ...
```

业务层只依赖 `ModelGateway`，不得直接 import `LocalLlamaProvider`。

### 5.2 OpenAICompatibleProvider

使用 `httpx.AsyncClient` 实现通用 `/v1/chat/completions` 调用。

`local_llama` 仅是配置实例：

```text
provider_type=openai_compatible
base_url=http://127.0.0.1:8080/v1
api_key=local
model=<环境变量>
```

后续百炼、DeepSeek 等可复用此 Provider 或增加薄适配器。

### 5.3 Provider 能力

至少包括：

- `supports_stream`；
- `supports_json_schema`；
- `supports_thinking`；
- `supports_batch`；
- `max_context_tokens`；
- `default_timeout_seconds`；
- `enabled`。

Phase 1B 默认 `supports_json_schema=false`，仍必须通过 Prompt + 本地校验实现结构化输出。

## 6. 场景边界任务

### 6.1 输入

- 章节 ID、标题；
- 按顺序排列的段落 ID 与原文；
- 只允许依据输入内容判断；
- 不得虚构人物、地点、事件或上下文。

### 6.2 输出 Schema

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

规则：

- 只返回“场景结束段落”；
- 不得把章节最后一段作为额外边界；
- `after_paragraph_id` 必须存在于输入章节；
- 结果按段落顺序排列；
- 不得重复；
- `reasons` 只能来自：时间、地点、视角人物、当前目标、冲突阶段、叙事任务明显变化；
- 如果没有内部边界，返回空数组。

### 6.3 长章节窗口化

不得按固定段数粗暴独立切分后直接生成场景。

建议：

- 以字符数为主构造窗口；
- 每个窗口保留 3—5 个重叠段落；
- 每个候选边界必须在至少一个窗口中获得完整前后文；
- 重复边界按段落 ID 合并；
- 冲突结果保留高置信度并记录来源；
- 最终由程序构造连续、无重叠、无漏段的场景。

## 7. 场景分析任务

### 7.1 输出 Schema

```json
{
  "scene_id": "B0001-C0001-S0001",
  "entry_state": {
    "summary": "人物以何种状态进入场景",
    "evidence_paragraph_ids": ["B0001-C0001-P0001"]
  },
  "goal": {
    "summary": "场景当前目标",
    "evidence_paragraph_ids": ["B0001-C0001-P0002"]
  },
  "obstacle": {
    "summary": "阻力；不存在时为空字符串",
    "evidence_paragraph_ids": []
  },
  "key_actions": [
    {
      "summary": "关键行动",
      "evidence_paragraph_ids": ["B0001-C0001-P0004"]
    }
  ],
  "turning_point": {
    "summary": "转折；不存在时为空字符串",
    "evidence_paragraph_ids": []
  },
  "outcome": {
    "summary": "场景结束时发生的变化",
    "evidence_paragraph_ids": ["B0001-C0001-P0011"]
  },
  "unresolved_question": {
    "summary": "交给后续场景的问题；不存在时为空字符串",
    "evidence_paragraph_ids": []
  },
  "function_tags": ["事件推进", "人物塑造"],
  "confidence": 0.84
}
```

### 7.2 业务校验

- 所有证据段落必须属于当前场景；
- 至少 `entry_state`、`goal`、`outcome` 各有一个有效证据；
- `key_actions` 可为空，但不可重复；
- `function_tags` 只能来自受控枚举；
- 不得把模型推测写成文本事实；
- 证据不充分时必须降低置信度或留空，不得编造。

## 8. JSON 解析与修复

固定流程：

```text
原始响应
→ 去除 Markdown 代码围栏
→ 提取第一个完整 JSON 对象
→ JSON 解析
→ Pydantic 校验
→ 业务校验
→ 成功保存
```

失败时：

1. 保存第一次原始响应和校验错误；
2. 使用修复 Prompt，输入原始响应、Schema 摘要和校验错误；
3. 最多修复两次；
4. 仍失败则标记 `failed`，不得伪造默认成功结果；
5. 所有尝试均写入 `ModelInvocation`。

## 9. API 合同

### Provider

- `GET /api/v1/model-providers`
- `GET /api/v1/model-providers/{provider_name}/health`

### AnalysisRun

- `POST /api/v1/chapters/{chapter_id}/analysis-runs`

请求：

```json
{
  "task_type": "scene_pipeline",
  "provider_name": "local_llama",
  "force": false
}
```

返回 `202 Accepted` 与 `run_id`。

- `GET /api/v1/analysis-runs/{run_id}`
- `POST /api/v1/analysis-runs/{run_id}/retry`

### Scene

- `GET /api/v1/chapters/{chapter_id}/scenes`
- `GET /api/v1/scenes/{scene_id}`
- `GET /api/v1/scenes/{scene_id}/analysis-artifacts`

## 10. 后台执行

本阶段不得引入 Redis/Celery。

可使用 FastAPI `BackgroundTasks` 或应用内轻量执行器。要求：

- POST 立即返回 `202`；
- 状态写入 SQLite；
- 异常必须转为 `failed`；
- 进程重启后，遗留 `running` 任务不得显示为成功；
- 可在应用启动时将超时 `running` 标记为 `interrupted/failed`，并允许人工重跑。

## 11. Prompt 管理

目录建议：

```text
packages/prompts/
├─ scene_boundary/v1/
│  ├─ system.md
│  ├─ user.md
│  └─ repair.md
└─ scene_analysis/v1/
   ├─ system.md
   ├─ user.md
   └─ repair.md
```

要求：

- Prompt 文件化、版本化；
- 运行时计算 Prompt 内容哈希；
- Prompt 版本与哈希写入运行记录；
- 禁止把大段 Prompt 硬编码在路由或服务函数中。

## 12. 测试策略

### 必须有的自动测试

- Provider 注册与配置读取；
- Provider 健康检查成功/失败；
- JSON 围栏提取；
- 非法 JSON 修复路径；
- Pydantic 校验失败；
- 不存在段落 ID 被拒绝；
- 跨场景证据被拒绝；
- 场景连续覆盖、无重叠、无漏段；
- Fake Provider 完整闭环；
- AnalysisRun 成功与失败状态；
- 单章重跑保留历史记录；
- API 202、查询和错误结构。

### 本地模型冒烟测试

增加独立脚本，只有设置环境变量时执行，不进入默认单元测试：

```text
STORYLENS_RUN_LOCAL_MODEL_TESTS=1
```

使用原创短篇 fixture，验证：

- llama-server 可达；
- 返回可解析 JSON；
- 生成至少一个场景；
- 所有证据 ID 真实存在；
- 分析结果可通过 API 查询。

## 13. Phase 1B 验收标准

以下条件全部满足才算通过：

1. `pytest` 全部通过；
2. Ruff 通过；
3. `scripts/check_project.py` 通过；
4. Provider 健康检查接口可用；
5. 对 fixture 章节提交分析后立即返回 `202`；
6. AnalysisRun 能从 `queued/running` 进入 `succeeded`；
7. 场景覆盖整章，段落无漏项、无重叠；
8. 场景 ID 稳定；
9. 每个场景均有通过 Schema 和证据校验的分析结果；
10. 每次模型调用保留原始输出、解析结果、耗时和错误；
11. 无真实模型时，Fake Provider 测试仍可完整通过；
12. 重跑不会覆盖旧分析记录；
13. 未接入任何云端付费 API；
14. 未跨入 Phase 1C。

## 14. 当前实现说明

- SQLite 采用应用启动时的幂等增量迁移，兼容 Phase 1A 已存在的数据库和数据。
- `Scene.scene_key` 是稳定业务 ID；数据库 `Scene.id` 是历史记录 ID。`(created_by_run_id, scene_key)` 唯一，从而允许重跑保留旧场景，同时保持同一输入的场景业务 ID 稳定。
- 章节场景列表默认返回最新一次成功 Run 的场景；使用数据库 Scene ID 可查询对应历史场景及 Artifact。
- 后台执行使用 FastAPI `BackgroundTasks` 和独立 SQLAlchemy Session，不引入外部队列。
