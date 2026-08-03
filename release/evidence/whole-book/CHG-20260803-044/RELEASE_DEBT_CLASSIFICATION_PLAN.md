# RELEASE_DEBT_CLASSIFICATION_PLAN — CHG-20260803-044

## Honesty baseline (do not rewrite)

| Suite | Result |
|---|---|
| Public Full | 2114 passed / **48 failed** / **6 errors** / 54 skipped |
| Public WB-2.2 new failures | **0** |
| Vitest Full | 1376 passed / **30 failed** |
| Vitest WB-2.2 new failures | **0** |
| check_project.py | **TIMEOUT** |

本轮 **不修复**；仅冻结 Wave 2（WB-2.2.2）必须完成的分类标签。

## Required labels (every failure/error must receive one)

| Label | Meaning |
|---|---|
| `release_blocking` | 阻断 V1.2.0 RC/Stable，除非修复 |
| `must_fix` | 必须修复（通常也是 blocking） |
| `formal_exception` | 产品负责人书面豁免并归档 |
| `obsolete_test` | 过期断言（如锁死 1.0.5），可改测试或例外 |
| `environment_only` | 仅环境/密钥/网络，不代表产品回归 |

## Seed classification plan（Wave 2 执行时落证，本轮不结案）

| Cluster | Examples (from CHG-042 pytest_full_summary) | Planned label seed |
|---|---|---|
| Version / registry / gate locks | `change_registry_check`, `version_is_1_0_5`, `gates_and_version_locked`, `test_version_unchanged` | obsolete_test **or** must_fix（发布工具链相关→偏 release_blocking） |
| native_overview ImportError (6 errors) | `test_native_overview_*` collection errors | must_fix / release_blocking until proven env-only |
| Live network / transport | `live_network_gate`, live transport persistence | environment_only **or** formal_exception if not required offline |
| Scene baseline | `test_fake_provider_complete_pipeline` | triage: must_fix vs formal_exception（基线已失败） |
| Pro license / Pro insights gates | `test_pro_license_local`, `test_pro_whole_book_insights_gate` | obsolete_test / formal_exception if Pro out of Free 1.2.0 |
| Reader journey Vitest 30 | legacy suite | triage in Wave 2; not auto non-blocking |
| check_project TIMEOUT | scripts/check_project.py | **release_blocking** until diagnosed or formal_exception |

## Rules

1. 不得把全部既有失败自动标为 non-blocking。  
2. `formal_exception` 必须有 Owner 签名证据文件。  
3. Wave 2 完成标准：每条失败/错误均有标签 + 处置（fix / exception / delete-obsolete with justification）。  
4. CHG-044 只建立计划，不声称债务已清。
