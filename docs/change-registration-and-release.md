# 变更登记与发布汇总

本文说明 StoryLens 的「功能变更登记池 + 发布基线 + 下一版本自动汇总」机制。

## 1. 什么是基础版本

基础版本（baseline）记录当前已确认占用的产品版本，例如 `1.0.2`。

- 源码版本的唯一来源仍是仓库根目录 `VERSION`
- `release/baseline.json` 只记录发布基线元数据，**不替代** `VERSION`
- 字段包括：版本号、对应 Git commit、tag、通道、安装包/updater 哈希、发布时间等
- 不得伪造 tag、安装包哈希或发布时间
- 若无法证明该版本已正式发布，则 `status = unverified`
- `unverified` 时**正式发布门禁必须失败**

## 2. 什么是下一版本待发布池

`release/unreleased.json` 是下一版本的变更收集池：

| 字段 | 日常开发 | 冻结后 | 发布后 |
|------|----------|--------|--------|
| `base_version` | 等于当前 `VERSION` | 不变 | 滚到新基线 |
| `target_version` | 必须为 `null` | 仍可为 null，直到 prepare | 写入新版本 |
| `status` | `collecting` | `frozen` | `released` |
| `changes` | 变更编号列表 | 冻结清单 | 归档后重建空池 |

日常开发只往池中登记，**不升版、不构建、不发布**。

## 3. 每批功能如何登记

```powershell
python scripts/change_registry.py register `
  --title "功能标题" `
  --type improvement `
  --user-summary "面向用户的一句话说明"
```

会生成 `release/changes/CHG-YYYYMMDD-NNN.json`，并加入 `unreleased.changes`。

类型：`feature | improvement | fix | security | performance | database | build | updater | documentation`

不要把无关功能硬塞进同一条登记。

## 4. 一个变更如何关联多个 commit

```powershell
python scripts/change_registry.py attach-commit CHG-20260721-001 <sha>
```

- 一个功能批次可关联多个 commit
- 同一 commit 默认可作为某一变更的主关联；若确需跨多个变更，必须提供 `--multi-change-reason`
- 新提交建议加 trailer：

```text
StoryLens-Change: CHG-20260721-001
```

发布门禁同时读取 trailer 与 registry JSON。不要求改写历史 commit。

## 5. 日常开发为什么不升版

版本号在「生成下一个版本」之前保持稳定，避免：

- 半成品占用正式版本号
- 本机安装包与源码版本漂移
- 未冻结范围被提前写成 `1.0.3` 之类目标

只有用户明确说「生成下一个版本」并执行 `prepare-next-release --confirm` 时才 bump。

## 6. 什么情况下可以 frozen

```powershell
python scripts/change_registry.py freeze
```

前置条件：

- 计划发布项全部 `ready`
- 无未登记源码 commit
- 无未解决 P0/P1 blocker
- 工作区干净
- `VERSION` / `base_version` 一致
- baseline 已 `verified`

冻结后禁止再增加普通功能变更；只允许修本版本阻断问题。

## 7. 什么情况下执行 prepare-next-release

```powershell
python scripts/change_registry.py prepare-next-release --bump patch
python scripts/change_registry.py prepare-next-release --bump patch --confirm
```

无 `--confirm` 只预览，不改 `VERSION`。

有 `--confirm` 时才会：

1. 要求已 `frozen`
2. 再跑 registry / version_manager 检查
3. 调用 `version_manager.py bump patch`
4. 写入 `target_version` 与 `docs/releases/<version>.md`
5. **不**自动构建、上传、发布 stable、升级本机

## 8. 版本号如何自动计算

由当前 `VERSION` 推导：`1.0.2` → patch → `1.0.3`。  
日常不得手写死下一版本。

## 9. 未登记 commit 如何阻止发布

```powershell
python scripts/change_registry.py unregistered
```

比较 `baseline.git_commit..HEAD`。修改 `apps/`、`scripts/`、`packaging/`、`config/`、依赖清单、Tauri 配置等路径的提交默认必须登记。

白名单集中在 `release/registry_config.json`（文档、audits、纯 release 登记文件、`[docs-only]` 提交等）。

任何 `UNREGISTERED` 都会让正式发布失败。

## 10. deferred 代码为什么不能留在发布分支

若登记为 `deferred` 但相关 commit 仍在 HEAD，且没有关闭的 feature flag 证据，发布门禁失败。  
要么移出代码，要么保留并提供明确关闭证据。

## 11. staging 和 stable 的关系

- **staging**：内部验证通道
- **stable**：正式用户通道

正式发布前应完成 staging 验证；客户端默认指向 stable，且不得静默安装。详见 `docs/windows-desktop-updater-channels.md`。

## 12. 用户确认后才能更新

正式策略：

- 可自动检查
- 不自动下载
- 不自动安装
- 用户确认后再下载 / 再安装
- 设置页保留手动检查入口

## 13. 当前 1.0.2 → 未来 1.0.3 示例

1. 基线：`VERSION=1.0.2`，`release/baseline.json` 指向 bump 提交（当前可能为 `unverified`）
2. 日常：在 `feature/*` 上改代码 → 测试 → commit（带 trailer）→ 更新登记状态
3. 汇总：`status` / `release-preview` 查看下一补丁预览 `1.0.3`
4. 用户明确要求生成下一版本 → `freeze` → `prepare-next-release --bump patch --confirm`
5. 再进入构建、staging、用户确认更新流程

## 14. 出现登记错误时如何修复

| 问题 | 处理 |
|------|------|
| 漏登记 | `register` + `attach-commit`，或补 trailer 后 `attach-commit` |
| 状态标高了 | 用 `update`/`mark` 回到合法状态；补齐 tests / evidence |
| 误关联 commit | 编辑对应 `release/changes/*.json` 后跑 `check` |
| 误写 `target_version` | 在 `collecting` 时改回 `null` |
| 误 bump 了 VERSION | 按版本文档恢复，且不得在未确认时发布 |

常用命令：

```powershell
python scripts/change_registry.py status
python scripts/change_registry.py check
python scripts/change_registry.py release-preview
python scripts/change_registry.py baseline show
python scripts/change_registry.py baseline verify
```
