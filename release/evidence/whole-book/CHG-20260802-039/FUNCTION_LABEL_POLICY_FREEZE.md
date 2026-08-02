# FUNCTION LABEL POLICY FREEZE

**Status:** FROZEN  
**Decision:** **CONTROLLED**（方案 B）

## Why CONTROLLED（not OPEN / HYBRID）

| Option | Verdict | Reason |
|---|---|---|
| A OPEN | Rejected | Private runner already fail-closes unknown labels；OPEN 破坏确定性与测试 |
| B CONTROLLED | **Selected** | Evidence: `GENERAL_LABELS` in Private `runner.py`；SPEC multi-label；phase2b generic enums |
| C HYBRID | Rejected for wire | UI 文案可本地化；wire 必须单一受控词表 |

Chinese narrative examples（开篇建立、伏笔回收…）appeared only as **planning examples** without formal enum evidence → **not** auto-imported into wire.

## CANONICAL LABELS（wire English snake_case）

```
setup
escalation
climax
resolution
transition
side_story
flashback
empty
non_mainline
unknown
```

**Removed from Lab GENERAL_LABELS meta-tags:** `primary`, `secondary`  
→ become V2 structural fields, not function labels.

## NORMALIZATION POLICY

1. Lowercase + trim；`-` → `_`.  
2. Unknown label → reject（repair once may map only via explicit synonym table below； else fail field）.  
3. Synonym table（closed；impl must not expand per novel）：

| Alias → | Canonical |
|---|---|
| rising / rising_action | escalation |
| ending / denouement | resolution |
| bridge | transition |
| aside | side_story |
| none / blank | empty |

4. Duplicate labels in secondary → dedupe preserve order.  
5. If primary equals a secondary → drop from secondary.  
6. `normalize_function_labels` repair rule：**REQUIRED to implement**（manifest today；code MISSING）.

## Chinese UI mapping（display-only； not wire）

| Wire | UI（zh） |
|---|---|
| setup | 开篇/建立 |
| escalation | 冲突升级 |
| climax | 高潮 |
| resolution | 收束 |
| transition | 过渡 |
| side_story | 支线章 |
| flashback | 回溯 |
| empty | 空章/填充 |
| non_mainline | 非主线 |
| unknown | 未判定 |

UI may refine copy without changing wire.

## Forbidden

- Genre-specific labels（修仙境界章、甜宠……）  
- Per-novel custom taxonomies  
- Treating mood/pacing/character traits as function labels  
- Unbounded synonym growth outside this freeze without a new Change
