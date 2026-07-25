# StoryLens Cursor Prompt｜STEP 2.6 Free 1.0.5 全面回归与升级验证

## 1. 任务标识

```text
STEP：2.6
阶段名称：Free 1.0.5 全面回归与升级验证
版本目标：StoryLens 1.1.0
Change ID：CHG-20260725-003
主轨道：I
协作轨道：A / C
审计轨道：D
前置门禁：STEP 2.G5 = PASSED
目标门禁：STEP 2.G6
```

唯一目标：

> 证明 Pro 原生全书概览没有破坏 Free 1.0.5、旧数据库、导入、书库、单章分析和桌面既有行为。

---

## 2. 数据安全

只能使用：

* 临时数据库；
* 测试 Fixture；
* 1.0.5 数据库副本。

禁止：

* 直接打开正式用户 `storylens.db` 进行 Migration；
* 修改正式用户书库；
* 删除真实用户文件；
* 使用未知私人作品；
* 清理 `%LOCALAPPDATA%\StoryLens` 正式目录。

如果需要运行桌面测试，必须使用明确测试数据目录或复制目录。

---

## 3. 开始前检查

记录：

```text
Public HEAD
Private HEAD
Public Clean
Private Clean
VERSION
v1.0.5
release/1.0.5
Structure WIP
Feature Flag
Live Cost Total
剩余时间
```

确认：

```text
v1.0.5 与 release/1.0.5
仍指向 ddae7ee4910ab35a443e47fc1ffad4928e7a5543
```

不一致立即停止。

---

## 4. 数据库升级测试

### 4.1 生成或复制 1.0.5 测试库

测试库必须包含：

* Book；
* Chapter；
* Paragraph；
* 至少一个旧 AnalysisRun；
* Scene 或 Reader Journey 结果；
* Provider/设置可读取结构；
* 删除测试所需数据。

记录升级前：

```text
Book Count
Chapter Count
Paragraph Count
AnalysisRun Count
Journey Count
Scene Count
```

### 4.2 执行升级

使用正式应用 Migration 路径。

验证：

* 新表创建；
* 新字段创建；
* 旧数据不变化；
* 没有第二数据库；
* 没有不可逆旧数据改写；
* 不依赖 `create_all()` 掩盖 Migration 缺失。

### 4.3 重复启动

执行两次或更多次初始化。

必须：

* 不重复建表报错；
* 不重复插入 Schema 数据；
* 旧数据数量不变；
* 新 Pro 表可用。

### 4.4 升级后读取

验证：

* Book；
* Chapter；
* Paragraph；
* 旧 AnalysisRun；
* Reader Journey；
* Scene；
* 章节聚合洞察；
* 设置；
* 新 Whole-Book Run 创建。

---

## 5. 导入回归

### TXT

验证：

* 导入；
* 章节识别；
* Paragraph；
* 稳定 ID；
* 重复导入行为；
* 原文件不删除。

### DOCX

必须有专项自动化测试：

* 创建最小 DOCX Fixture；
* 导入；
* 章节/段落读取；
* 原 DOCX 文件保留；
* 删除书籍不删除 DOCX。

### EPUB

必须有专项自动化测试：

* 创建或使用合法最小 EPUB Fixture；
* 导入；
* 章节/段落读取；
* 原 EPUB 文件保留；
* 删除书籍不删除 EPUB。

不得为本 Step 重构导入系统。

---

## 6. 书库和删除保护

验证：

* 书库读取；
* 打开书籍；
* 重复导入；
* 删除二次确认；
* 删除本地 StoryLens 数据；
* 原始文件仍存在；
* 运行中 Chapter Task 阻止删除；
* 运行中 Whole-Book Run 阻止删除；
* Completed Run 不错误阻止删除；
* 删除后派生数据按现有规则清理。

---

## 7. Free 单章功能回归

必须验证：

* 创建单章分析；
* 读取单章结果；
* Scene；
* Reader Journey；
* 节奏；
* 钩子；
* 回报；
* Chapter Deep Link；
* 旧结果兼容；
* Provider 配置；
* 预算；
* 错误状态。

不得因为 Pro 新状态机修改旧单章状态语义。

---

## 8. 章节聚合洞察回归

验证：

* 页面仍叫“章节聚合洞察”；
* API 路径不变；
* Capability Key 不变；
* Pro License Gate 不变；
* 单章覆盖率语义不变；
* 不被原生全书页面覆盖；
* Router 正常；
* Deep Link 正常。

---

## 9. 设置和授权回归

验证：

* Provider 设置；
* API Key 不被日志输出；
* 测试连接；
* 分析模式；
* 预算上限；
* 主题；
* 字号；
* 行距；
* 开发者模式；
* Telemetry Consent；
* Free / VIP 状态；
* Pro Native Overview 授权；
* 无授权后端 403。

---

## 10. 前端回归

至少运行：

* Book Workspace；
* Library；
* Delete；
* Reader；
* Chapter Analysis；
* Reader Journey；
* 章节聚合洞察；
* Pro 原生全书概览；
* Settings；
* Router；
* Error Boundary；
* First Launch。

---

## 11. 完整测试门禁

本阶段允许执行：

### Public

```text
完整 Pytest
```

### Private

```text
完整 Pytest
```

### Desktop

```text
完整 Vitest
npm run typecheck
```

### 项目检查

```text
check_project.py
git diff --check
Registry 定向校验
```

如全局 Registry 仍只有既有 CHG-002 head_inclusion 问题：

* 记录；
* 不在本 Step 修；
* 确认 CHG-003 自身合法。

---

## 12. 失败处理

全量测试失败后：

```text
先运行失败测试
→ 定位是否本 Change 引入
→ 修复
→ 运行相邻模块
→ 最后只再跑一次完整门禁
```

禁止反复无意义执行全量套件。

只自动修：

* 本次 Change；
* Free 回归；
* 升级；
* 构建阻断。

无关历史测试失败：

* 确认基线是否已有；
* 记录 BASELINE_FAILURE；
* 不扩大范围。

---

## 13. STEP 2.G6 通过条件

必须全部满足：

* [ ] 1.0.5 数据库副本升级；
* [ ] 重复启动安全；
* [ ] 旧 Book 数量不变；
* [ ] 旧 Chapter 数量不变；
* [ ] 旧 Paragraph 数量不变；
* [ ] 旧 AnalysisRun 可读；
* [ ] Reader Journey 可读；
* [ ] TXT 导入通过；
* [ ] DOCX 专项导入通过；
* [ ] EPUB 专项导入通过；
* [ ] 原始文件保护通过；
* [ ] 删除二次确认通过；
* [ ] 活动 Whole-Book Run 阻止删除；
* [ ] Free 单章功能通过；
* [ ] 章节聚合洞察通过；
* [ ] Provider 设置通过；
* [ ] License 通过；
* [ ] Public 完整测试通过，或仅有已确认基线失败；
* [ ] Private 完整测试通过；
* [ ] Desktop 完整测试通过；
* [ ] Typecheck 通过；
* [ ] 项目检查通过；
* [ ] D-Audit 无 P0；
* [ ] VERSION 仍为 1.0.5；
* [ ] Feature Flag 默认 false；
* [ ] 未 Push；
* [ ] 未 verified。

P1 未关闭时不得进入 Windows 发布候选。

---

## 14. Gate 报告

写入：

```text
release/evidence/CHG-20260725-003/night-run/gate-2g6.md
```

包括：

```text
Upgrade Fixture
Before Counts
After Counts
Repeat Startup
TXT/DOCX/EPUB
Free Features
Chapter Aggregation
Delete Protection
Full Test Results
Baseline Failures
P0/P1/P2
Public HEAD
Private HEAD
Result
Next Step
```

通过后才能读取 `STEP-2.7-DETAILED.md`。
