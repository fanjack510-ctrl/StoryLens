# ADR-001：单一业务数据库

- **Status:** Accepted (STEP 1.3)
- **Change:** CHG-20260725-003
- **Date:** 2026-07-25

## Context

StoryLens Free 与 Pro 需要共享同一用户书库、Snapshot、Run 与叙事资产，避免双库同步与授权分裂。Private Engine 若自建库将破坏本地优先与升级路径。

## Decision

```text
正式业务数据库唯一路径：
%LOCALAPPDATA%\StoryLens\database\storylens.db
```

环境变量：`STORYLENS_DATABASE_URL`（经 runtime path defaults 注入）。

规则：

1. Public 与 Private **不得**分别拥有独立业务数据库  
2. Private Engine **不得**创建 SQLAlchemy Engine / 管理 ORM Session / 运行 Migration / 创建 `pro.db`  
3. Keyring、localStorage、配置 JSON **不是**第二业务事实库  
4. 小说、Snapshot、Run、Entity、Asset、Relation、Evidence、结果投影必须进入统一 SQLite  
5. 正式结果不得仅保存在文件 JSON 或前端 localStorage  
6. 测试必须使用临时目录数据库  
7. 正式运行路径必须统一经过 `apply_runtime_path_defaults`  

## Consequences

- 升级路径单一；Free→Pro 数据连续  
- Private 只返回 Candidate；Public 负责事务与落库  
- 后续检索增强优先在同库内扩展（见 ADR-005）  

## Risks（记录，STEP 1.3 不修复）

- `Settings` 开发默认可能指向 `./data/storylens.db`  
- 正式桌面依赖 `apply_runtime_path_defaults`  
- 仓库本地 `data/storylens.db` 不得视为正式用户库  
- `create_all()` 与自定义 Migration 双轨需后续治理（建议跟踪 Step：STEP 2.1 / 稳定版）  

## Related Steps

STEP 2+ 实现原生 Overview 时继续遵守；禁止引入第二业务库。
