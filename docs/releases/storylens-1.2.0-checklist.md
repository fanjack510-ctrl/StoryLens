# StoryLens 1.2.0 — Release Checklist

**Authority:** CHG-20260803-044 / `v120_free_release_path`  
**Feature end:** WB-2.2-CHAPTER-FUNCTIONS（功能开发已完成）

## Pre-release waves

| Wave | ID | Owner gate | Done? |
|---|---|---|---|
| Scope reconciliation | CHG-20260803-044 | MG-V1.2.0-SCOPE-RECONCILIATION | **PASSED** |
| 1 E2E stabilization plan | CHG-20260803-045 | （planning） | implemented；待授权 Agents |
| 1 E2E stabilization | WB-2.2.1-V120-E2E-STABILIZATION | MG-V1.2.0-E2E-STABILIZATION / MG-WB-2.2.1 | ☐ |
| 2 Release debt triage | WB-2.2.2-V120-RELEASE-DEBT | MG-WB-2.2.2 | ☐ |
| 3 Real Provider L3 | WB-2.2.3-V120-L3-PROVIDER | MG-WB-2.2.3 | ☐ |
| 4a RC / installer / upgrade | WB-6.4-120-RC | MG-WB-6.4 | ☐ |
| 4b Stable release | WB-6.5-120-STABLE | MG-WB-6.5 | ☐ |

## Wave 1 checklist (summary)

- [ ] Free 四模块同一正式分析链路  
- [ ] Cost Estimate + Consent  
- [ ] Pause / Resume / Cancel  
- [ ] Duplicate Provider Calls = 0  
- [ ] Duplicate Assets = 0  
- [ ] confirmed no-overwrite  
- [ ] conflict 行为  
- [ ] 刷新与重新进入  
- [ ] Evidence Deep Link  
- [ ] Dev Harness 不进入正式构建  

## Wave 2 checklist (summary)

- [ ] Public 48 failed / 6 errors 逐条标签  
- [ ] Vitest 30 failed 逐条标签  
- [ ] check_project TIMEOUT 处置  
- [ ] version / registry / gate 锁  
- [ ] native_overview ImportError  
- [ ] Scene baseline failure  

Labels allowed: `release_blocking` | `must_fix` | `formal_exception` | `obsolete_test` | `environment_only`

## Wave 3 checklist (summary)

- [ ] 真实百炼 Provider（用户批准后）  
- [ ] 短书 / 中书 / 长书  
- [ ] 四模块完整执行  
- [ ] 输出截断与 Repair  
- [ ] 费用估算  
- [ ] 中断恢复  
- [ ] Evidence  
- [ ] Provider 调用与计费无重复  

## Wave 4 checklist (summary)

- [ ] Sidecar Build  
- [ ] Windows Installer  
- [ ] V1.1.2 → V1.2.0 升级  
- [ ] 保留已有书籍与分析数据  
- [ ] 正式安装态资源定位  
- [ ] 正式安装态 Provider  
- [ ] 卸载数据保留  
- [ ] Dev Route 不进入正式构建  
- [ ] Release Gate / 版本号 / 更新说明 / Hash / 归档 / Tag / GitHub Release  

## Forbidden before Stable

- 开始 WB-2.3 / WB-2.4 功能编码  
- 增加 Pro 购买 / License / 激活 UI  
- 新增分析模块  
