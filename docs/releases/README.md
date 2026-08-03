# StoryLens 发布说明目录

本目录存放各版本发布说明与基线文档。

## 当前约定

- 源码版本唯一来源：仓库根目录 `VERSION`
- 变更登记与冻结：`release/unreleased.json` + `release/changes/`
- 机制说明：[`docs/change-registration-and-release.md`](../change-registration-and-release.md)
- 版本管理：[`docs/versioning-and-release.md`](../versioning-and-release.md)

## 文件命名

- `docs/releases/<VERSION>.md`：该版本发布说明 / 基线
- 仅在 `prepare-next-release --confirm` 或等效正式流程中生成/定稿目标版本文件
- 日常开发不得提前把 `VERSION` 改成下一版本

## 范围冻结文档

- `docs/releases/storylens-<VERSION>-scope.md`：版本产品/工程范围锁定（STEP 范围门禁产出）
- 范围文档**不等于**正式发布说明；不得因写 scope 而提前 bump `VERSION`

## 现有文档

| 文件 | 说明 |
|------|------|
| `storylens-1.2.0-scope.md` | 1.2.0 Free 四模块范围冻结（CHG-20260803-044） |
| `storylens-1.2.0-checklist.md` | 1.2.0 发布前剩余波次清单（非正式发布说明） |
| `storylens-1.1.0-scope.md` | 1.1.0 Pro 原生全书概览范围锁定（STEP 2.0；`VERSION` 仍为 1.0.5） |
| `1.0.5.md` | 1.0.5 发布说明 / 基线 |
| `1.0.4.md` | 1.0.4 发布说明 |
| `1.0.3.md` | 历史发布说明 |
