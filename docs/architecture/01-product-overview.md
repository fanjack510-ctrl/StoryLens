# 01 — Product Overview

## StoryLens 产品定位

**StoryLens（叙镜）** 是面向小说作者与写作学习者的 **本地优先** AI 拆书、结构化场景分析与读者旅程可视化工具。

- 不是在线协作写作平台
- 不是全书社交社区
- 不是自动改稿 / 自动训练系统
- V1.0 聚焦：**单章**导入 → 边界审阅 → Scene Analysis → Reader Journey → 导出

## 核心用户

| 角色 | 诉求 |
|------|------|
| 小说作者 | 理解单章节奏、场景切分、读者情绪曲线，辅助改稿决策 |
| 写作学习者 | 拆解优秀章节的场景结构与证据链 |
| 本地隐私敏感用户 | 文本留在本机 SQLite；自备云端 Key（BYOK） |

## 核心使用流程

```
配置阿里云百炼 Qwen Key（设置 → AI服务）
        ↓
导入小说（TXT / DOCX / EPUB）
        ↓
打开书籍 → 选择章节 → 正文阅读
        ↓
发起分析（预算预检 + 云端同意）
        ↓
边界候选 → 人工审阅确认
        ↓
Scene Analysis（可部分完成 / 可恢复）
        ↓
Reader Journey（场景画像 + 章节综合）
        ↓
图表 / Inspector / Evidence / 导出 PNG·JSON·Markdown
```

## 当前实现能力（V1.0 Ordinary）

| 能力 | 状态 |
|------|------|
| 单章导入与阅读 | ✅ |
| 章节重解析 / 诊断 | ✅ |
| 场景边界检测 + 人工审阅 | ✅ |
| Scene Analysis + 证据绑定段落 ID | ✅ |
| Reader Journey 工作区（v4.2） | ✅ |
| 统一恢复中心 / 预算暂停恢复 | ✅ |
| 本地 SQLite 持久化 | ✅ |
| BYOK 阿里云 Qwen（`aliyun_qwen_plus` / `qwen3.7-plus`） | ✅ |
| 开发者模式：任务中心 / 多 Provider / 本地模型 | ⚠️ 可用但不面向普通用户 |
| 多章对比 / 全书伏笔网络 / Neo4j / 计费 | ❌ 明确不在 V1.0 |

## 平台与数据

- **平台：** Windows 10/11（PowerShell 引导）；桌面栈 React + Vite + Tauri 2
- **数据：** `data/storylens.db`；运行时 `data/runtime/`；Key 存 OS Keyring
- **费用：** 由用户阿里云账户承担；StoryLens 不提供云端账号
