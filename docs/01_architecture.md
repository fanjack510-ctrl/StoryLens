# 01｜系统总体架构

## 1. 分层架构

```text
桌面端 / Web UI
        ↓
FastAPI 应用服务
        ↓
领域服务层
├─ 文件导入
├─ 文本清洗
├─ 章节与段落解析
├─ 场景切分
├─ 专项分析器
├─ 证据验证
└─ 检索与导出
        ↓
模型网关 Model Gateway
├─ 本地 llama.cpp
├─ 阿里云百炼
├─ DeepSeek
├─ 智谱 GLM
└─ Kimi
        ↓
数据层
├─ SQLite（开发）
├─ PostgreSQL + pgvector（正式）
└─ 原始文件与中间产物存储
```

## 2. 核心模块

### 2.1 Ingestion

负责文件类型检测、内容读取、编码修复、章节候选识别和原文保存。

### 2.2 Narrative Parser

负责把章节进一步切分为场景和叙事单元，不承担跨章节复杂推理。

### 2.3 Analysis Engine

采用多个专项分析器：

- scene_analysis
- plot_chain
- hook_analysis
- character_portrayal
- setting_description

每个分析器拥有独立 Prompt、Schema、版本号和评测集。

### 2.4 Evidence Validator

负责校验：

- 段落 ID 是否存在；
- 引用是否属于当前输入范围；
- 开始与结束段落顺序是否合法；
- 模型是否返回了未输入的证据；
- 结论与证据是否需要人工复核。

### 2.5 Model Gateway

统一暴露 `generate()`，业务代码只关心任务类型和输出 Schema。

## 3. 部署形态

### 开发阶段

- Windows 单机；
- FastAPI；
- SQLite；
- llama-server；
- 手动切换云端 Provider。

### 正式阶段

- 桌面端 Tauri + React；
- 后端本机服务或局域网服务；
- PostgreSQL + pgvector；
- 后台任务队列；
- 国内 API 自动路由。
