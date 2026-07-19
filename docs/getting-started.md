# Getting started

StoryLens（叙镜）是面向小说作者与写作学习者的 **本地优先** AI 拆书与读者旅程分析工具。

## V1.0 你需要知道的事

1. 数据默认保存在本机 `data/storylens.db`（运行时在 `data/runtime/`）。
2. 你必须自备 **阿里云百炼 Qwen API Key**（BYOK）。
3. StoryLens **不提供**云端账号；费用由你的阿里云账户承担。
4. V1.0 普通模式正式支持：**阿里云百炼 · Qwen**（内部 `aliyun_qwen_plus`，默认 `qwen3.7-plus`）。
5. 当前正式平台：Windows 10/11。

## 三步开始

```powershell
cd D:\Dstorylens
.\scripts\bootstrap.ps1
.\scripts\start-dev.ps1
```

浏览器打开：`http://127.0.0.1:1420`  
API 健康检查：`http://127.0.0.1:8000/health`

首次进入时，按向导配置 Qwen → 导入一本书 → 选择章节开始分析。

下一步：

- [Qwen API 配置](qwen-api-setup.md)
- [导入第一本书](import-first-book.md)
- [跑通第一次分析](run-first-analysis.md)
