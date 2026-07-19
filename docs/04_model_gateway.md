# 04｜模型网关设计

## 1. 目标

本地模型与国内 API 使用统一接口，业务层不得包含厂商判断。

```python
result = await gateway.generate(
    task_type="scene_analysis",
    messages=messages,
    output_schema=SceneAnalysisResult,
    provider="local_llama",
)
```

## 2. Provider 优先级

1. `local_llama`：开发默认。
2. `aliyun_bailian`：首选云端升级。
3. `deepseek`：复杂推理与交叉复核。
4. `zhipu`：中文分析备用。
5. `kimi`：长文本补漏备用。

## 3. 统一能力描述

每个 Provider 注册：

- supports_stream
- supports_json_schema
- supports_thinking
- supports_batch
- max_context
- default_timeout
- enabled

## 4. 结构化输出

流程固定为：

```text
模型返回
→ 提取 JSON
→ Pydantic 校验
→ 段落 ID 校验
→ 业务约束校验
→ 保存原始输出与验证输出
```

不得只保存模型整理后的结果。

## 5. 错误策略

- 网络错误：指数退避重试；
- JSON 错误：执行修复 Prompt，最多两次；
- 证据错误：禁止自动入库，进入待审；
- 上下文超限：拆分任务或切换高上下文 Provider；
- API 余额、限流：切换备用 Provider，但必须记录原因。
