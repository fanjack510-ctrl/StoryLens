# Night Execution Manifest｜CHG-20260725-003

**Recorded:** 2026-07-26T01:11:11+08:00
**Change:** CHG-20260725-003
**Night deadline:** started_at + 7 hours (see night-run-summary / operator log)

## Priority (highest first)

```text
冻结 Contract
> Accepted ADR / 正式架构
> StoryLens 1.1.0 Scope
> 当前 Step Detailed 文件
> Night Execution Manifest
> Agent 临时判断
```

任何 Agent 不得以详细文件与冻结契约冲突为由自行修改契约。发现冲突时必须停止并登记 `CONTRACT_AMENDMENT_REQUIRED`。

## Detailed Step Files

| Order | Gate prerequisite | Detailed file | Gate evidence |
|------:|-------------------|---------------|---------------|
| 1 | STEP 2.G3 = PASSED | `release/evidence/CHG-20260725-003/night-run/STEP-2.4-DETAILED.md` | `gate-2g4.md` |
| 2 | STEP 2.G4 = PASSED | `release/evidence/CHG-20260725-003/night-run/STEP-2.5-DETAILED.md` | `gate-2g5.md` |
| 3 | STEP 2.G5 = PASSED | `release/evidence/CHG-20260725-003/night-run/STEP-2.6-DETAILED.md` | `gate-2g6.md` |
| 4 | STEP 2.G6 = PASSED | `release/evidence/CHG-20260725-003/night-run/STEP-2.7-DETAILED.md` | `gate-2g7.md` |

## Auto-advance rule

```text
gate-2g3.md Result=PASSED
→ 读取 STEP-2.4-DETAILED.md

gate-2g4.md Result=PASSED
→ 读取 STEP-2.5-DETAILED.md

gate-2g5.md Result=PASSED
→ 读取 STEP-2.6-DETAILED.md

gate-2g6.md Result=PASSED
→ 读取 STEP-2.7-DETAILED.md

gate-2g7.md Result=PASSED
→ 停止（WAITING_FOR_USER_STEP_2_8）
```

不得只依赖 Agent 口头声明 Gate 通过；必须以对应 `gate-2gN.md` 书面 Result 为准。

## Hard boundaries (all steps)

* No Push / Tag / GitHub Release
* No automatic `verified`
* No permanent `VERSION` change (stay `1.0.5` until STEP 2.8 human acceptance)
* No Structure / Storylines / arcs / hooks / causality / dual-timeline / whole-book Journey expansion
* Protect Structure Empty Policy WIP worktrees
* Real Provider only inside STEP 2.5 (night limit ¥9.00; absolute ¥10.00)
* Windows RC only inside STEP 2.7 (`1.1.0-rc.1` via override; no permanent VERSION commit)

## Current gate snapshot (at manifest write)

| Gate | Status |
|------|--------|
| STEP 2.G3 | PASSED (`gate-2g3.md`) |
| STEP 2.G4 | PASSED (`gate-2g4.md`) |
| STEP 2.G5 | PASSED (`gate-2g5.md`) |
| STEP 2.G6 | NOT STARTED |
| STEP 2.G7 | NOT STARTED |

## Change status rule

Only after STEP 2.G3—G7 all PASS may CHG-20260725-003 advance:

```text
implemented → tested
```

Never auto-advance to `verified` / `ready-for-staging` / `ready` / `released`.
