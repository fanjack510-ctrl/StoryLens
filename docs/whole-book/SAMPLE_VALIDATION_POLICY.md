# Whole-Book Sample S / M / L Validation Policy

This Step freezes **selection criteria and registration format only**.  
Do **not** commit copyrighted full novel text into the Public repository.

## Gradient

| Sample | Purpose | Requirements |
|---|---|---|
| **S** | Basic correctness | Few chapters; clear entities/events; human can fully check; own/public/constructed text; no work-specific production tuning |
| **M** | Cross-chapter merge, clues, recovery, cost | Multi-chapter; aliases; cross-chapter events; ≥1 clue/goal migration; human sampling check |
| **L** | Full-length performance/cost/consistency | Only after S and M PASS; separate approval for Provider/model/calls/cost; no work-specific tuning |

Flow: **S → PASS → M → PASS → L**. Never jump to L first.

## Registration template (no body)

```text
Sample ID：
等级：S / M / L
文本来源：
授权状态：
章节数：
段落数：
字数：
人物数量预期：
事件数量预期：
关键别名：
关键跨章关系：
适用 Step：
禁止提交正文：
YES
```

Store filled registrations under `release/evidence/whole-book/samples/` (metadata only) when samples are chosen in later Steps.
