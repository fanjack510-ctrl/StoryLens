# PRODUCT DEFINITION FREEZE — 章节功能

**Status:** FROZEN for WB-2.2 implementation  
**Change:** CHG-20260802-039

## Definition

「章节功能」分析的是：

> 每一章在整本小说叙事推进中承担的主要作用与辅助作用。

## Granularity（不得 unresolved）

```
GRANULARITY：PER_CHAPTER
```

- SoT 输出为**逐章**一项（`chapter_id` + `chapter_order`）。  
- UI 可将连续相同 primary 的章节**聚合展示**，但**不得**覆盖或删除底层逐章结果。  
- 不以「章节区间」作为唯一持久化粒度。

## Primary / secondary（不得 unresolved）

| Rule | Freeze |
|---|---|
| `primary_function` | 最多 **1**；类型为受控标签或 `null` |
| `secondary_functions` | **0..N** 受控标签；不得与 primary 重复 |
| 无可靠 primary | **合法**：`primary_function=null`，可仍有 secondary，或二者皆空仅当 empty-policy 允许 |
| 同置信度冲突 | 选 **coverage 更贴合章内证据** 的标签；仍并列则 `primary=null` + 二者进 secondary（fail-soft）后记 limitation |
| 一章无任何功能 | **仅**在 empty / insufficient 合法路径；否则 repair 后 fail-closed |
| primary vs secondary 原则 | primary = 该章对全书推进的主导叙事作用；secondary = 并存但非主导的作用 |

## Confidence

```
confidence：REQUIRED per chapter item（0..1 float）
overall / analysis_confidence：optional top-level
```

## Multi-function

Allowed via primary + secondary.  
Do **not** pack `"primary"`/`"secondary"` strings into the label enum（V2 structural fields instead）.
