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

## 现有文档

| 文件 | 说明 |
|------|------|
| `1.0.3.md` | 下一正式版本规划基线（当前 `VERSION` 仍为 1.0.2，尚未 bump） |
