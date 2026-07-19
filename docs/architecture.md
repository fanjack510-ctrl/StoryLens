# Architecture (V1.0 阅读版)

StoryLens V1.0 是单机优先的桌面 + 本地 API 应用：

```
Desktop (React/Vite/Tauri)
        │ HTTP
        ▼
Local FastAPI (apps/api)
        │
        ├─ SQLite (books, runs, scenes, journeys, budgets)
        ├─ Model Gateway → Aliyun Qwen (BYOK) / optional local llama (dev)
        └─ OS Keyring (API keys)
```

## 核心流水线（单章）

1. Import → chapters / paragraphs  
2. Boundary candidates → human review → immutable revision  
3. Scene Analysis（可部分完成、可恢复）  
4. Reader Journey（Scene profiles + chapter synthesis）  
5. Deterministic visualization + export  

## 设计约束

- 模型输出经 Pydantic 校验  
- 文学结论绑定真实段落 ID  
- Provider 不写死在业务流水线中；普通 UI 默认只暴露 Qwen  
- 失败可重试、可定位、可单项恢复  
- 预算：分阶段预留 + Run 级临时请求授权  

完整历史方案见 `docs/01_architecture.md`、`docs/04_model_gateway.md`。
