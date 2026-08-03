# V120_REMAINING_RELEASE_PATH — authoritative Free 1.2.0 chain

## Formal steps remaining: **5**（4 waves）

| Wave | Formal ID(s) | Goal | Product code | Real Provider | Installer | Manual gate |
|---|---|---|---|---|---|---|
| 1 | **WB-2.2.1-V120-E2E-STABILIZATION** | Free 四模块同一正式链路；Cost/Consent；Pause/Resume/Cancel；无重复 Provider/Asset；confirmed no-overwrite；conflict；刷新重进；Evidence deep link；Dev harness 正式构建隔离 | YES（稳定化） | NO | NO | MG-WB-2.2.1 |
| 2 | **WB-2.2.2-V120-RELEASE-DEBT** | 分类/修复 Public 48f/6e、Vitest 30f、check_project TIMEOUT、version/registry/gate、native_overview ImportError、scene baseline | minimal if main-chain | NO | NO | MG-WB-2.2.2 |
| 3 | **WB-2.2.3-V120-L3-PROVIDER** | 真实百炼；短/中/长书；四模块完整执行；截断 Repair；费用；中断恢复；Evidence；无重复计费/调用 | minimal fixes | **YES** | NO | MG-WB-2.2.3 |
| 4 | **WB-6.4-120-RC** → **WB-6.5-120-STABLE** | Sidecar/Installer；1.1.2→1.2.0 升级；数据保留；安装态 Provider/资源；卸载保留；无 Dev Route；Release Gate/Tag/GitHub Release | packaging | as gate | **YES** | MG-WB-6.4 / MG-WB-6.5 |

## Planned Change IDs（not started）

| Step | Planned Change |
|---|---|
| WB-2.2.1 | CHG-20260803-045 |
| WB-2.2.2 | CHG-20260803-046 |
| WB-2.2.3 | CHG-20260803-047 |
| WB-6.4 | CHG-20260728-037（historical reserved） |
| WB-6.5 | CHG-20260728-038（historical reserved） |

## Next after this reconciliation is verified

1. Owner PASS on **MG-V1.2.0-SCOPE-RECONCILIATION**  
2. Authorize **WB-2.2.1-V120-E2E-STABILIZATION**  

## Explicitly not next

- WB-2.3-STORYLINES  
- WB-2.4-FIRST-FOUR-PRODUCT  
- Any WB-3.x～WB-5.x feature step  

## Process

继续压缩流程：实施计划 → ≤2 路并行 Agent → Integration → 人工验收。  
仅在高风险边界未冻结时增加 Pre-Implementation Freeze。  
不恢复每步重型 Contract 流程。

## This Change does not execute Waves 1–4
Only freezes IDs and path.
