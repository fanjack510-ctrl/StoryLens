# StoryLens Whole-Book Architecture（正式真值）

**Status:** Frozen (STEP 1.3); **AMENDED BY CHG-20260726-004**  
**Change:** CHG-20260725-003 + CHG-20260726-004  
**Date:** 2026-07-25 / amended 2026-07-26  
**Public Base:** `9f53d4a6349fb76a90465aefc402ed2ee874a94b`  
**Private Base:** `727f886ead297a3af2019354f2f56352cf22a9d4`  
**Free Baseline:** `v1.0.5` / `release/1.0.5` / `ddae7ee4910ab35a443e47fc1ffad4928e7a5543`

> 本文是 StoryLens 整书能力的**产品级架构真值**。  
> Phase 1P–2BR1 分阶段文档（`docs/architecture/narrative-intelligence-core/`）继续作为历史实现与契约记录；若与本文冲突，**以本文与同目录 ADR 为准**。  
> **Private ≠ Paid：** Private Engine 表示闭源组件边界；Free / Pro 表示产品授权层级。  
> **1.1.x：** Native Whole-Book Overview 为 Free；**1.2.0：** Pro 正式起点。

**相关文档：**

- [Public / Private 边界](./storylens-public-private-boundary.md)
- [Step 路线图与 Cursor 模板](./storylens-step-roadmap.md)
- [ADR 索引](./adr/)

---

## 1. 阅读约定：目标 vs 当前

| 标记 | 含义 |
|------|------|
| **目标（Target）** | 已冻结、允许后续 Step 实现的架构决策 |
| **当前（Current）** | 仓库在 STEP 1.3 时点的真实实现状态 |
| **Lab** | Mock / Private Lab / FakeHttp；**不是**正式生产入口 |
| **WIP** | Structure Empty Policy 等工作树；**不是** Integration 能力 |

不得把 Target / Lab / WIP 写成已完成的 Production。

---

## 2. 产品版本边界

### 2.1 Free 1.0.5（已封存基线）

Free 是免费开源**单章分析**正式基线，已包含：

- TXT / DOCX / EPUB 导入
- 书库
- Chapter / Paragraph
- 单章分析、Scene、Reader Journey、单章旅程
- 钩子 / 回报 / 节奏
- Provider 设置、费用与预算
- Windows 桌面、Sidecar、更新基础
- 删除保护（二次确认、运行中阻止、原始文件不删）

**规则：** 上述能力不得在 Pro 中重新定义为“新增功能”。Pro 只增加基于完整原文的整书能力。

### 2.2 StoryLens 1.1.0（Free Native Overview）

从 1.1.0 起增加基于完整原文的整书能力（**产品 Free**）。

**1.1.0 唯一正式新增功能：**

```text
原生全书概览（Native Whole-Book Overview）— FREE in 1.1.x
Private Native Overview Engine — CLOSED SOURCE
```

它**不**代表全部整书 Pro 模块完成，也**不**等于现有「章节聚合洞察」。  
Pro 增强（`whole_book_enhanced` 等）从 **1.2.0** 起作为产品起点；已免费的原生概览不得收回为 Pro 专属。

### 2.3 章节聚合洞察（Current，非原生整书）

Capability key：`pro_whole_book_insights`（兼容保留）。

正式产品名：**章节聚合洞察** / Chapter Asset Aggregation Insights。

- 输入：已完成的单章分析资产
- 不是完整原文直接分析
- 不是 `whole_book_native` 生产流水线
- 未来可作为 `whole_book_enhanced` 的精细资产覆盖辅助视图

详见 STEP 1.2 与 CHG-20260725-002 / CHG-20260725-003。

---

## 3. 单一业务数据库（Target + Current 原则）

详见 [ADR-001](./adr/ADR-001-single-business-database.md)。

```text
%LOCALAPPDATA%\StoryLens\database\storylens.db
```

Free 与 Pro **共用一个**业务 SQLite。Private Engine 不得拥有独立业务库、不得 `create_engine` / Session / Migration。

---

## 4. 完整原文第一事实源

详见 [ADR-002](./adr/ADR-002-whole-book-native-source-of-truth.md)。

```text
完整小说原文 + 对应 Book Snapshot
= Pro 整书分析的第一事实源
```

要点：

1. 不要求用户提前完成所有单章分析  
2. Chapter 是导航单位，不是强制语义边界  
3. 原生整书必须建立跨章节重叠窗口  
4. 单章 Scene / Journey / Beat 等只能作增强输入  
5. 单章资产不得覆盖或替代原文事实  
6. 单章分析覆盖率不得称为原文覆盖率  
7. 章节聚合洞察 ≠ 原生整书分析  
8. Completed Snapshot 对绑定 Run 不可变  

---

## 5. 两种整书模式

详见既有契约 `phase2b-native-enhanced.md`；本文冻结产品语义。

### 5.1 `whole_book_native`（标准原生）

- 直接读取完整原文  
- 不依赖单章分析  
- 原文覆盖率必须达到 100%  
- 独立建立 Entity / Asset / Relation / Evidence  

### 5.2 `whole_book_enhanced`（精细增强）

- 完整原文仍为第一事实源  
- 可使用已有 Scene / Beat / Reader Journey / Chapter Analysis / Evidence  
- 有多少精细资产就增强多少区域  
- 缺少精细资产仍可完成整书分析  
- **不得**将增强覆盖率称为原文覆盖率  

### 5.3 覆盖率必须分别显示

```text
原文覆盖率
精细章节资产覆盖率
Scene 覆盖率
Beat 覆盖率
Evidence 覆盖率
```

---

## 6. 七层总体架构（Target）

```text
一、原始正文层
   Book / Volume / Chapter / Paragraph

二、快照与结构定位层
   Book Snapshot / Paragraph Locator / Scene / Beat / 跨章节语义窗口

三、分析运行层
   Chapter Run / Whole-Book Run / Run Stage / Checkpoint / Usage / Cost

四、叙事事实与资产层
   事件 / 目标 / 阻碍 / 冲突 / 行动 / 选择 / 后果 / 信息揭示

五、关系与生命周期层
   因果链 / 人物关系链 / 故事线 / 钩子回报链 / 伏笔链 / 双时间线

六、整书叙事模型层
   结构阶段 / 章节功能 / 主线支线 / 人物弧 / 阅读旅程 / 问题诊断

七、Pro 产品与资产层
   结果页 / Evidence / 用户纠正 / 正式资产 / 灵感库 / 故事实验台
```

**Current：** 层一～三骨架与层四～五 ORM/服务大量已存在；层六多为 Lab/DTO；层七部分 UI（章节聚合洞察）已集成，原生 Overview 未产品化。

---

## 7. 统一叙事资产架构（Target）

详见 [ADR-003](./adr/ADR-003-unified-narrative-assets.md)。

### 7.1 核心实体（长期目标）

`Character` · `Location` · `Organization` · `Object` · `WorldConcept` · `TimeAnchor`

须支持 Stable ID / Alias / Canonical / Merge / Version / Evidence / Accepted|Rejected / Lock / stale|superseded。

**Current ORM `EntityType` 映射（不在本阶段改 Enum）：**

| 目标 | 当前 `EntityType` |
|------|-------------------|
| Character | `character` |
| Location | `location` |
| Organization | `organization`（另有 `faction`） |
| Object | `object` |
| WorldConcept | `concept` |
| TimeAnchor | `timeline_entity` |
| — | `unknown` |

### 7.2 核心资产类型（长期目标 vs 当前）

| 目标类型 | 当前 `AssetType` | 备注 |
|----------|------------------|------|
| plot_event | `event` | 命名映射 |
| character_goal | `goal` | |
| obstacle | （缺失） | 后续 Step 扩展 |
| conflict | `conflict` | |
| character_action | （缺失） | 后续 Step |
| character_choice | `choice` | |
| consequence | `consequence` | |
| state_change | （缺失） | 后续 Step |
| question / hook / clue / foreshadowing / misdirection | 同名或已有 | |
| information_reveal | `reveal` | 命名映射 |
| partial_payoff / final_payoff / reversal | 已有 | |
| relationship_change | （缺失资产型；有 Relation） | |
| world_rule / theme_signal | （缺失） | 后续 Step |
| structure_stage / storyline / chapter_function | 已有 | |
| character_arc_node | `character_arc_stage` | 命名映射 |
| timeline_event | （缺失） | 后续 Step |

### 7.3 核心关系类型

**Current `RelationType`：**  
`causes` · `enables` · `blocks` · `escalates` · `resolves` · `pays_off` · `foreshadows` · `reveals` · `contradicts` · `belongs_to` · `advances` · `changes_relationship` · `precedes` · `parallels`

**目标集合中尚未落地的示例（后续 Step，不在 1.3 改 Enum）：**  
`involves_character` · `belongs_to_storyline` · `occurs_in` · `concurrent_with` · `motivates` · `changes_goal` · `produces_consequence` · `raises_question` · `strengthens` · `provides_clue` · `misdirects` · `partially_pays_off` · `answers` · `revealed_to_reader` · `known_by_character` · `hidden_from_character` · `reinterprets` 等。

### 7.4 候选 → 正式生命周期（Target）

```text
candidate → validated → accepted | rejected → (lock)
              ↘ superseded / stale
```

流程：

```text
Private 生成 Candidate
→ Public 校验
→ Entity Resolution / 去重
→ Evidence 校验
→ candidate / validated
→ 用户认可或纠正
→ accepted / rejected
→ 锁定
→ 重跑生成新版本
```

**Current review_status：** `candidate` · `confirmed` · `corrected` · `rejected`（与目标 `accepted` 语义接近；不在本阶段重命名）。

---

## 8. 运行架构（Target）

详见 [ADR-004](./adr/ADR-004-whole-book-runtime-and-analysis-passes.md)。

### 8.1 生产级调用链

```text
前端创建 Run
→ Public License / Capability 校验
→ 冻结 Book Snapshot
→ 创建 Run 和 Stage
→ 建立跨章节窗口
→ 组装当前全局状态
→ 调用 Private Engine
→ 返回 Candidate
→ Public 校验与 Materialize
→ 更新 Entity / Asset / Relation / Evidence
→ 更新全局状态
→ 保存 Usage / Cost / Checkpoint
→ 推进下一窗口或下一 Stage
→ 生成 Result Projection
→ 前端展示
```

### 8.2 事务边界（原则）

同一窗口内尽量同事务提交：Candidate Materialization、Entity/Asset/Relation、Evidence、Usage、Global State Version、Checkpoint。避免半写入与重复计费。**实现细节在 STEP 2.1。**

### 8.3 Book 级全局叙事状态（Target）

可恢复的运行状态（非正式事实唯一来源）；正式事实仍进 Entity / Asset / Relation / Evidence。状态版本绑定 Run、Snapshot、处理窗口。

---

## 9. 5-Pass 与 10-Stage 映射

> **5-Pass = 分析算法阶段；现有 10-stage = 运行协议阶段。二者不互斥，不得删除当前 10-stage。**

| Pass | 算法焦点 | 主要对齐的 `WholeBookStageKey`（Current） |
|------|----------|-------------------------------------------|
| Pass 0 快照与前检 | Snapshot、完整性、模式、Provider、费用、原文覆盖、索引准备 | `build_fulltext_index` + Preflight（非 stage 表项） |
| Pass 1 事实抽取与实体统一 | Window、Entity、Alias、Event、Goal、Action、Choice、Consequence、Reveal、Evidence | `resolve_entities` |
| Pass 2 动态叙事图谱 | Relation、冲突升级、钩子生命周期、时间线关系 | `analyze_hooks` · `analyze_causality_timeline`（部分） |
| Pass 3 全局叙事模型 | Storylines、Structure、Chapter Functions、Arcs、Timeline | `analyze_structure` · `analyze_storylines` · `analyze_characters` |
| Pass 4 综合与证据复核 | Overview、Diagnosis、冲突解决、低置信度、Evidence Repair | `generate_diagnostics` · `verify_evidence` · `persist_narrative_assets` |
| Pass 5 整书阅读旅程 | 动力、张力、节奏、疲劳/停滞/高潮 | **尚未有独立 stage；属 STEP 7 范围** |

当前 10 keys：

```text
build_fulltext_index
resolve_entities
analyze_structure
analyze_storylines
analyze_characters
analyze_hooks
analyze_causality_timeline
generate_diagnostics
verify_evidence
persist_narrative_assets
```

---

## 10. 长文本检索

详见 [ADR-005](./adr/ADR-005-long-text-index-strategy.md)。

长期：`SQLite + FTS5 + 关系表`。STEP 2 不强制实现 FTS5；暂不引入 Neo4j / 向量库。

---

## 11. 十一核心功能共享底座

```text
Snapshot / Run / Window
        ↓
Entity / Event / Goal / Choice / Consequence
        ↓
Relation / Global State
        ↓
Storyline / Structure / Chapter Function
        ↓
Character Arc / Relationship / Hook / Causality / Timeline
        ↓
Overview / Diagnosis
        ↓
Whole-Book Journey
```

**禁止：** 每页独立事实源、互不关联大 JSON、重复抽取、独立数据库、矛盾主角/故事线。

11 个产品模块（`WholeBookModuleKey`）共用同一叙事底座，不是 11 套引擎。

---

## 12. 1.1.0 范围冻结（= STEP 2）

### 必须完成

- Pro License  
- Native Run  
- Snapshot  
- 原文覆盖  
- 跨章节窗口  
- 最小全局状态  
- Entity / Asset / Evidence  
- Overview Projection  
- 进度 / 错误 / Retry / 恢复  
- Evidence 跳转  
- Windows 安装  
- 1.0.5 数据库升级  
- Free 回归  

### 明确不做

完整 Structure / Storylines / 人物弧 / 人物关系 / 钩子生命周期 / 因果链 / 双时间线产品化；原生整书阅读旅程；大型资产编辑器；灵感库；FTS5 正式实现；增量局部重分析。

> **1.1.0 Overview 是首个完整 Pro 产品切片，不代表 Pro V1 全部完成。**

---

## 13. 当前实现状态矩阵（Current）

| 能力 | 当前状态 |
|------|----------|
| Free 1.0.5 | 已完成并封存 |
| 单一业务数据库原则 | 已建立（见 ADR-001 风险） |
| Public / Private 分仓 | 已建立 |
| Snapshot | 已存在 |
| Entity / Asset / Relation / Evidence ORM | 已存在 |
| Whole-Book Run 正式入口 | **未启用**（`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED`） |
| 生产 Orchestrator | **未建立**（Mock/Lab orchestrator 存在） |
| Book 全局状态 | **未建立** |
| 跨章节窗口生产执行 | **未产品化** |
| Book Overview | Lab / FakeHttp 基础存在 |
| Structure Stages | Integration 不完整；Structure Empty Policy **WIP 未合入** |
| Chapter Functions | Lab |
| Storylines | Lab |
| 后七模块 | 以 DTO / Contract 为主 |
| 章节聚合洞察 | UI 已集成（STEP 1.2） |
| 原生整书概览 | **未开发** |
| 原生整书阅读旅程 | **未开发** |

---

## 14. 已知风险（记录，本阶段不修复）

1. `Settings.database_url` 开发默认 `sqlite:///./data/storylens.db`；正式桌面依赖 `apply_runtime_path_defaults`。  
2. 仓库本地 `data/storylens.db`（gitignored）≠ 正式用户库。  
3. `create_all()` 与自定义 Migration 双轨需后续治理。  
4. Structure Empty Policy WIP 不得计入 Integration 能力、不得自动合入。  

---

## 15. 变更记录

| 日期 | Step | 说明 |
|------|------|------|
| 2026-07-25 | STEP 1.3 | 首次冻结产品级整书架构真值 |
