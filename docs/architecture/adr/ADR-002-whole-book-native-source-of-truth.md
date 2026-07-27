# ADR-002：整书原生分析的第一事实源

- **Status:** Accepted (STEP 1.3)
- **Change:** CHG-20260725-003
- **Date:** 2026-07-25

## Context

若以“先跑完全书所有单章分析”为前置，则原生整书无法成立，且会把单章资产覆盖率误称为原文覆盖率。现有「章节聚合洞察」已证明单章聚合路径的产品价值，但语义上不是原生整书。

## Decision

```text
完整小说原文 + 对应 Book Snapshot
是 Pro 整书分析（whole_book_native / whole_book_enhanced）的第一事实源。
```

强制含义：

1. 不要求用户提前完成所有单章分析  
2. Chapter 是导航单位，不是强制语义边界  
3. 原生整书必须建立跨章节重叠窗口  
4. 单章 Scene / Journey / Beat 等只可作为增强输入  
5. 单章资产不得覆盖或替代原文事实与 Evidence  
6. 单章分析覆盖率不得称为原文覆盖率  
7. 章节聚合洞察 ≠ 原生整书分析  
8. Completed Snapshot 对绑定的 Run 不可变  

模式区分见总架构与 `phase2b-native-enhanced.md`：`whole_book_native` / `whole_book_enhanced`。

## Consequences

- STEP 2 Overview 必须以 Snapshot 原文窗口驱动  
- Enhanced 可选用单章资产，但覆盖率必须分列显示  
- 章节聚合洞察可继续作为辅助视图，不得改称原生 Overview  

## Related Steps

STEP 2（原生 Overview）；STEP 3+（统一事实底座深化）。
